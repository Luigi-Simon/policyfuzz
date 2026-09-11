"""Live async SandboxService with version-bound resume and bounded cleanup."""

import asyncio
import json
from collections import OrderedDict

from app.v2.contracts import (
    Persona,
    SandboxRequest,
    SandboxResult,
    SandboxStatus,
    request_fingerprint,
    validate_sandbox_result,
)
from app.v2.diagnostics import record

from .capture import project_capture
from .language import LanguageError
from .personas import SeedPersona
from .translation import checked_projection, latin_display


class UnsupportedPolicyTitle(ValueError):
    """The shared boundary cannot preserve and translate a non-English title."""


class MiroFishSandboxService:
    def __init__(
        self,
        client,
        language,
        *,
        poll_seconds=2,
        cleanup_seconds=20,
        translation_seconds=30,
        max_agents=50,
    ):
        self.client, self.language = client, language
        self.poll_seconds = max(0.001, poll_seconds)
        self.cleanup_seconds = cleanup_seconds
        self.translation_seconds = translation_seconds
        self.max_agents = min(max_agents, client.max_agents)
        if self.max_agents < 1 or cleanup_seconds <= 0 or translation_seconds <= 0:
            raise ValueError("Sandbox bounds must be positive")
        # Diagnostic snapshots are immutable JSON strings, bounded and backend-only.
        # Durable source files and the job journal live in the MiroFish service.
        self._archives = OrderedDict()

    def internal_capture(self, fingerprint):
        return self._archives.get(fingerprint)

    @staticmethod
    def _validate_job(request, job):
        if not isinstance(job, dict):
            raise TypeError("Malformed job")
        original = SandboxRequest.model_validate(job["request"])
        if request_fingerprint(original) != request_fingerprint(request) or job[
            "request_fingerprint"
        ] != request_fingerprint(request):
            raise ValueError("Job identity mismatch")
        if not isinstance(job["simulation_id"], str) or not job["simulation_id"]:
            raise ValueError("Missing simulation ID")
        roster = tuple(SeedPersona.model_validate(p) for p in job["personas"])
        if type(job["profiles_count"]) is not int or job["profiles_count"] != len(
            roster
        ):
            raise ValueError("Profile count mismatch")
        if not 1 <= len(roster) <= request.stakeholder_count:
            raise ValueError("Roster count mismatch")
        if len({p.display_name.casefold() for p in roster}) != len(roster):
            raise ValueError("Duplicate personas")
        for p in roster:
            Persona(
                persona_id="validate",
                display_name=p.display_name,
                description=p.description,
            )

    async def run(self, request: SandboxRequest) -> SandboxResult:
        request = SandboxRequest.model_validate(request.model_dump(warnings=False))
        deadline = asyncio.get_running_loop().time() + request.timeout_seconds
        # The shared contract currently requires the exact title AND English.
        if not latin_display(request.policy_title):
            raise UnsupportedPolicyTitle(
                "The shared v2 contract currently requires an English policy title."
            )
        try:
            record("title", "started")
            async with asyncio.timeout(min(30, request.timeout_seconds * 0.2)):
                title = checked_projection(
                    request.policy_title,
                    await self.language.english(request.policy_title),
                )
        except Exception:  # noqa: BLE001 - no valid public title exists on this failure
            record("title", "failed", code="title_unverified")
            raise UnsupportedPolicyTitle(
                "The policy title could not be verified as English; no simulation was started."
            ) from None
        if title.translated:
            raise UnsupportedPolicyTitle(
                "Provide an English policy title until the shared title contract supports translation."
            )
        fingerprint = request_fingerprint(request)
        job, rows, notes, errors = None, {}, [], []
        prepare_attempted = False
        status = SandboxStatus.COMPLETED
        projected = None
        phase = "lookup"
        # Reserve part of the request deadline for capture/translation. Cleanup has
        # its own explicit bound so a stuck engine cannot strand the API task.
        execution_budget = max(
            0.001,
            deadline
            - asyncio.get_running_loop().time()
            - request.timeout_seconds * 0.2,
        )
        try:
            async with asyncio.timeout(execution_budget):
                candidate = await self.client.lookup(fingerprint)
                if candidate is None:
                    phase = "roster"
                    count = min(request.stakeholder_count, self.max_agents)
                    people = tuple(await self.language.personas(request, count))
                    if len(people) != count:
                        raise ValueError("Persona count differs from requested cap")
                    prepare_attempted = True
                    phase = "prepare"
                    record(phase, "started", count=len(people))
                    candidate = await self.client.prepare(request, people)
                self._validate_job(request, candidate)
                job = candidate  # Only a fully bound job may be captured or stopped.
                if job["status"] == "ready":
                    phase = "start"
                    record(phase, "started")
                    await self.client.start(fingerprint)
                phase = "simulation"
                record(phase, "started")
                while True:
                    candidate = await self.client.status(fingerprint)
                    self._validate_job(request, candidate)
                    if (
                        candidate["simulation_id"] != job["simulation_id"]
                        or candidate["personas"] != job["personas"]
                        or candidate.get("clock") != job.get("clock")
                    ):
                        raise ValueError("Job changed during execution")
                    job = candidate
                    state = candidate["status"]
                    if state in {"completed", "failed", "cancelled", "stopped"}:
                        if state == "failed":
                            status = SandboxStatus.FAILED
                            errors.append(
                                "simulation_failed: MiroFish reported an unsuccessful run."
                            )
                        elif state in {"cancelled", "stopped"}:
                            status = SandboxStatus.CANCELLED
                            notes.append(
                                "simulation_cancelled: MiroFish stopped before normal completion."
                            )
                        break
                    if state not in {
                        "ready",
                        "starting",
                        "running",
                        "preparing",
                        "stopping",
                    }:
                        raise ValueError("Unrecognized job status")
                    await asyncio.sleep(self.poll_seconds)
        except asyncio.CancelledError:
            status = SandboxStatus.CANCELLED
            notes.append("cancelled: The caller cancelled this Sandbox request.")
            await self._stop(fingerprint, bool(job) or prepare_attempted, errors)
        except TimeoutError:
            record(phase, "failed", code="sandbox_deadline")
            status = SandboxStatus.PARTIAL
            errors.append("timeout: The bounded simulation deadline expired.")
            await self._stop(fingerprint, bool(job) or prepare_attempted, errors)
        except Exception as error:  # noqa: BLE001 - sanitize the injected provider boundary
            status = SandboxStatus.FAILED
            code = (
                error.code
                if isinstance(error, LanguageError)
                else "provider_or_binding_invalid"
            )
            record(phase, "failed", code=code)
            errors.append(
                f"sandbox_execution_failed: stage={phase}; code={code}. "
                + (
                    "Participant setup failed before MiroFish preparation; no simulation was started."
                    if phase == "roster"
                    else "The stage could not return validated evidence."
                )
            )
            await self._stop(fingerprint, bool(job) or prepare_attempted, errors)

        if job:
            try:
                remaining = max(0.001, deadline - asyncio.get_running_loop().time())
                async with asyncio.timeout(min(remaining, self.cleanup_seconds)):
                    rows, capture_notes = await self.client.capture(
                        job["simulation_id"]
                    )
                    notes.extend(capture_notes)
                    self._archives[fingerprint] = json.dumps(
                        {"job": job, "capture": rows},
                        ensure_ascii=False,
                        sort_keys=True,
                    )
                    while len(self._archives) > 16:
                        self._archives.popitem(last=False)
                # Each record handles the shared projection deadline itself, so
                # unfinished translations become placeholders without discarding
                # the records that already completed successfully.
                projected = await project_capture(
                    request,
                    job,
                    rows,
                    self.language,
                    translation_timeout=self.translation_seconds,
                    projection_deadline=min(
                        deadline,
                        asyncio.get_running_loop().time() + self.translation_seconds,
                    ),
                )
            except asyncio.CancelledError:
                status = SandboxStatus.CANCELLED
                notes.append(
                    "cancelled: Capture was cancelled; source data remains in MiroFish."
                )
                await self._stop(fingerprint, True, errors)
            except Exception:  # noqa: BLE001 - retain independent partial evidence
                notes.append(
                    "capture_incomplete: Capture or English projection did not finish within its bound."
                )
                if status == SandboxStatus.COMPLETED:
                    status = SandboxStatus.PARTIAL

        personas, messages, sources, originals = (), (), (), ()
        if projected:
            personas, messages, sources, originals, projection_notes = projected
            notes.extend(projection_notes)
        elif job:
            scope = f"mirofish:{job['simulation_id']}:{fingerprint}"
            personas = tuple(
                Persona(
                    persona_id=f"{scope}:participant:{i}",
                    display_name=p["display_name"],
                    description=p["description"],
                )
                for i, p in enumerate(job["personas"])
            )
        observed = len({message.persona_id for message in messages})
        if job and len(personas) != request.stakeholder_count:
            notes.append(
                f"population_cap: Requested {request.stakeholder_count}; MiroFish configured {len(personas)} participants."
            )
        if observed != request.stakeholder_count:
            notes.append(
                f"observed_population: Captured messages from {observed} of {request.stakeholder_count} requested participants."
            )
        # The foundation requires unavailable translations to use PARTIAL even
        # after cancellation/failure. Preserve the cause in machine-prefixed notes.
        unavailable = any(m.translation_status == "unavailable" for m in messages)
        # Native action logs are metadata for the already captured posts/comments.
        # Keeping records without message IDs in the archive is informational;
        # it must neither duplicate messages nor downgrade a completed capture.
        incomplete_notes = [
            note
            for note in notes
            if not note.startswith(("action_metadata_only:", "discussion_quality:"))
        ]
        if unavailable or (
            status == SandboxStatus.COMPLETED and (incomplete_notes or errors)
        ):
            status = SandboxStatus.PARTIAL
        if status == SandboxStatus.FAILED and messages:
            status = SandboxStatus.PARTIAL
        result = SandboxResult(
            request_id=request.request_id,
            run_id=request.run_id,
            policy_version=request.policy_version,
            policy_title=request.policy_title,
            policy_text_sha256=request.policy_text_sha256,
            request_fingerprint=fingerprint,
            execution_mode="live",
            status=status,
            requested_stakeholder_count=request.stakeholder_count,
            configured_stakeholder_count=len(personas),
            observed_stakeholder_count=observed,
            personas=personas,
            messages=messages,
            sources=sources,
            original_records=originals,
            limitations=tuple(dict.fromkeys(notes))
            + (
                "Simulated stakeholder reactions are qualitative evidence, not a representative survey or authoritative policy verdict.",
                "Opening posts are seeded; only validated replies demonstrate interaction. Sequence is presentation order; missing timing stays unknown.",
                "Participants may speculate or invent provisions. Verify their statements against the exact policy before treating them as facts.",
            ),
            errors=tuple(dict.fromkeys(errors)),
        )
        validate_sandbox_result(request, result)
        return result

    async def _stop(self, fingerprint, needed, errors):
        if not needed:
            return
        # A prepare response may have been lost. Cancellation by fingerprint
        # is supported server-side and cannot launch another simulation.
        try:
            async with asyncio.timeout(self.cleanup_seconds):
                await self.client.stop(fingerprint)
        except Exception:  # noqa: BLE001 - cleanup failures must not discard evidence
            # A lost response or native shutdown may outlast the HTTP deadline.
            # Confirm this exact job before warning that stopping is unknown.
            try:
                async with asyncio.timeout(self.cleanup_seconds):
                    job = await self.client.status(fingerprint)
                if job.get("request_fingerprint") == fingerprint and job.get(
                    "status"
                ) in {"stopped", "cancelled", "completed", "failed"}:
                    return
            except Exception:  # noqa: BLE001, S110 - the public warning below reports uncertainty
                pass
            errors.append(
                "stop_unacknowledged: MiroFish did not confirm stopping; inspect this job before retrying."
            )
