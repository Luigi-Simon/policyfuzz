"""Parse source records before projecting text; never reconstruct missing links."""

import asyncio
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import quote

from app.v2.contracts import (
    ENGLISH_TRANSLATION_UNAVAILABLE,
    OriginalRecord,
    Persona,
    SandboxMessage,
    SourceEvidence,
    TranslationStatus,
)

from .quality import discussion_quality
from .translation import checked_projection


@dataclass(frozen=True)
class ParsedRecord:
    identifier: str
    author: int
    content: str
    parent: str | None
    kind: str
    recorded_at: datetime | None
    round_number: int | None
    simulation_step: int | None


def identifier(value):
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise TypeError("Invalid source identifier")
    if not str(value).strip():
        raise ValueError("Empty source identifier")
    return quote(str(value), safe="")


def source_order(value):
    kind, suffix = value.rsplit(":", 1)
    # Native IDs are numeric, but opaque source IDs remain valid. The final
    # suffix makes equal numeric spellings deterministic without merging IDs.
    return (
        (kind, 0, int(suffix), suffix)
        if suffix.isascii() and suffix.isdigit()
        else (kind, 1, 0, suffix)
    )


def parse_records(rows, count, max_rounds, *, clock="unknown"):
    records, seen, notes = [], {}, []
    for kind, key in (
        ("post", "post_id"),
        ("comment", "comment_id"),
        ("action", "action_id"),
    ):
        for row in rows.get(kind + "s", []):
            try:
                if not isinstance(row, dict):
                    raise TypeError("Malformed source row")
                # Most native actions have no stable source ID. Keep them in the
                # raw archive, but do not invent a conversational message ID.
                if kind == "action" and key not in row:
                    notes.append(
                        "action_metadata_only: Actions without stable source IDs remain in the internal archive."
                    )
                    continue
                source_id = kind + ":" + identifier(row[key])
                if source_id in seen:
                    if seen[source_id] != row:
                        notes.append(
                            "duplicate_id_conflict: Conflicting deliveries of one source ID were excluded after the first record."
                        )
                    continue
                seen[source_id] = row
                raw_author = row.get("user_id", row.get("agent_id"))
                if isinstance(raw_author, bool) or not isinstance(
                    raw_author, (str, int)
                ):
                    raise TypeError("Invalid author")
                author = int(raw_author)
                if str(author) != str(raw_author):
                    raise ValueError("Ambiguous author")
                if author not in range(count):
                    notes.append(
                        "unknown_speaker: A source record has no verified roster identity and was excluded."
                    )
                    continue
                parent = None
                if kind == "post" and row.get("original_post_id") is not None:
                    # A native repost carries another author's text. Only quote_content
                    # is evidence of this speaker's own words.
                    content = row.get("quote_content")
                    parent = "post:" + identifier(row["original_post_id"])
                    if not content:
                        continue
                else:
                    content = row.get("content", row.get("text"))
                    if kind == "comment" and row.get("post_id") is not None:
                        parent = "post:" + identifier(row["post_id"])
                    if kind == "comment" and row.get("parent_comment_id") is not None:
                        parent = "comment:" + identifier(row["parent_comment_id"])
                if (
                    not isinstance(content, str)
                    or not content.strip()
                    or len(content) > 20000
                ):
                    raise ValueError("Invalid message content")
                recorded_at = None
                stamp = row.get("created_at", row.get("timestamp"))
                step = None
                if (
                    clock == "oasis_step_v1"
                    and type(stamp) is int
                    and 0 <= stamp <= max_rounds
                ):
                    step = stamp
                elif stamp is not None:
                    try:
                        recorded_at = datetime.fromisoformat(stamp)
                    except (ValueError, TypeError):
                        notes.append(
                            "unknown_timestamp: An unsupported source timestamp was left unknown."
                        )
                round_number = row.get("round_number", step or None)
                if round_number is not None and (
                    type(round_number) is not int or not 1 <= round_number <= max_rounds
                ):
                    notes.append(
                        "unknown_round: An invalid source round was left unknown."
                    )
                    round_number = None
                records.append(
                    ParsedRecord(
                        source_id,
                        author,
                        content,
                        parent,
                        kind,
                        recorded_at,
                        round_number,
                        step,
                    )
                )
            except (ValueError, KeyError, TypeError):
                notes.append(
                    "malformed_record: A source record could not be safely parsed and was excluded."
                )
    # Stable topological order. Missing/cyclic relationships are omitted publicly
    # and retained verbatim in the raw capture archive, never guessed.
    pending = {record.identifier: record for record in records}
    ordered, emitted = [], set()
    while pending:
        eligible = [
            r
            for r in pending.values()
            if r.parent is None or r.parent in emitted or r.parent not in pending
        ]
        if not eligible:
            notes.append(
                "cyclic_replies: Source reply relationships contain a cycle and were omitted."
            )
            eligible = [next(iter(pending.values()))]
        eligible.sort(
            key=lambda r: (
                r.simulation_step if r.simulation_step is not None else -1,
                r.recorded_at.isoformat() if r.recorded_at else "",
                source_order(r.identifier),
            )
        )
        for record in eligible:
            parent = record.parent if record.parent in emitted else None
            if record.parent and parent is None:
                notes.append(
                    "unresolved_reply: A source reply target could not be validated and was omitted."
                )
            ordered.append((record, parent))
            emitted.add(record.identifier)
            del pending[record.identifier]
    return ordered, list(dict.fromkeys(notes))


async def project_capture(
    request, job, rows, language, *, translation_timeout=30, projection_deadline=None
):
    scope = f"mirofish:{job['simulation_id']}:{job['request_fingerprint']}"
    roster = job["personas"]
    personas = tuple(
        Persona(
            persona_id=f"{scope}:participant:{index}",
            display_name=person["display_name"],
            description=person["description"],
        )
        for index, person in enumerate(roster)
    )
    parsed, notes = parse_records(
        rows, len(roster), request.max_rounds, clock=job.get("clock", "unknown")
    )
    notes.extend(discussion_quality(parsed))
    slots = asyncio.Semaphore(4)

    async def display(record):
        try:
            async with (
                asyncio.timeout_at(projection_deadline),
                slots,
                asyncio.timeout(translation_timeout),
            ):
                result = checked_projection(
                    record.content, await language.english(record.content)
                )
            return (
                result.text,
                result.language,
                (
                    TranslationStatus.TRANSLATED
                    if result.translated
                    else TranslationStatus.ORIGINAL_ENGLISH
                ),
            )
        except Exception:  # noqa: BLE001 - failed projection must never expose originals
            return (
                ENGLISH_TRANSLATION_UNAVAILABLE,
                "Unknown",
                TranslationStatus.UNAVAILABLE,
            )

    projections = await asyncio.gather(*(display(record) for record, _ in parsed))
    messages, sources, originals = [], [], []
    cross_authors = set()
    by_id = {r.identifier: r for r, _ in parsed}
    for sequence, ((record, parent), (content, lang, status)) in enumerate(
        zip(parsed, projections, strict=True), 1
    ):
        msg_id, src_id = (
            f"{scope}:{record.identifier}",
            f"{scope}:source:{record.identifier}",
        )
        replies = (f"{scope}:{parent}",) if parent else ()
        persona_id = personas[record.author].persona_id
        if parent and by_id[parent].author != record.author:
            cross_authors.add(record.author)
        if status is TranslationStatus.UNAVAILABLE:
            notes.append(
                "translation_unavailable: Some English display text is unavailable; original evidence remains internal."
            )
        messages.append(
            SandboxMessage(
                message_id=msg_id,
                sequence=sequence,
                persona_id=persona_id,
                content=content,
                translation_status=status,
                source_refs=(src_id,),
                reply_to_message_ids=replies,
                recorded_at=record.recorded_at,
                round_number=record.round_number,
            )
        )
        sources.append(
            SourceEvidence(
                source_id=src_id,
                record_id=msg_id,
                title=f"MiroFish {record.kind}"
                + (" (may include a seeded opening)" if record.kind == "post" else ""),
                excerpt=content,
            )
        )
        originals.append(
            OriginalRecord(
                record_id=msg_id,
                speaker_id=persona_id,
                source_id=src_id,
                content=record.content,
                language=lang,
                reply_to_record_ids=replies,
            )
        )
    if len(roster) > 1 and len(cross_authors) < len(roster):
        notes.append(
            f"interaction_coverage: Verified replies to other participants from {len(cross_authors)} of {len(roster)} configured participants."
        )
    return (
        personas,
        tuple(messages),
        tuple(sources),
        tuple(originals),
        list(dict.fromkeys(notes)),
    )
