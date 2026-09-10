from __future__ import annotations

import asyncio
import hashlib
import importlib
import json
import tempfile
import unittest
from pathlib import Path

from pydantic import ValidationError


def load(name: str):
    try:
        return importlib.import_module(f"app.v2.{name}")
    except ModuleNotFoundError as error:
        raise AssertionError("the app.v2 sandbox boundary has not been implemented") from error


class SandboxContractTests(unittest.TestCase):
    def test_completed_english_messages_must_cite_their_own_source(self) -> None:
        contracts = load("contracts")
        request = contracts.make_example_request()
        result = asyncio.run(load("fixtures").FixtureSandboxService().run(request))
        messages = tuple(
            message.model_copy(
                update={
                    "translation_status": contracts.TranslationStatus.ORIGINAL_ENGLISH,
                    "source_refs": result.messages[(index + 1) % len(result.messages)].source_refs,
                }
            )
            for index, message in enumerate(result.messages)
        )
        with self.assertRaisesRegex(ValueError, "own source"):
            contracts.validate_sandbox_result(
                request,
                result.model_copy(update={"messages": messages, "original_records": ()}),
            )

    def test_agent_roles_are_exactly_the_four_public_labels(self) -> None:
        contracts = load("contracts")

        self.assertEqual(
            {role.value for role in contracts.AgentRole},
            {
                "Orchestrator Agent",
                "Metric Agent",
                "Sandbox Agent",
                "Judge Agent",
            },
        )

    def test_policy_input_requires_the_four_core_fields(self) -> None:
        contracts = load("contracts")

        with self.assertRaises(ValidationError):
            contracts.PolicyInput(title="A", description="B", agent_seed="C")

        item = contracts.PolicyInput(
            title="Transit policy",
            description="Test stakeholder responses.",
            agent_seed="commuters and operators",
            agent_count=3,
        )
        self.assertEqual(item.agent_count, 3)
        self.assertEqual(item.supporting_documents, ())

    def test_request_rejects_a_policy_hash_that_does_not_match_exact_text(self) -> None:
        contracts = load("contracts")
        request = contracts.make_example_request()

        with self.assertRaises(ValidationError):
            request.model_copy(update={"policy_text_sha256": "0" * 64}, deep=True).__class__(
                **{
                    **request.model_dump(),
                    "policy_text_sha256": "0" * 64,
                }
            )

        self.assertEqual(
            request.policy_text_sha256,
            hashlib.sha256(request.policy_text.encode("utf-8")).hexdigest(),
        )

    def test_request_keeps_budget_counts_and_seeds_independent(self) -> None:
        contracts = load("contracts")
        request = contracts.make_example_request()

        self.assertEqual(request.stakeholder_count, 3)
        self.assertEqual(request.test_budget, 8)
        self.assertEqual(
            request.personality_seed,
            "Include practical, safety-focused, and accessibility-focused voices.",
        )
        self.assertNotEqual(request.random_seed, request.personality_seed)

    def test_scenario_and_context_forbid_outcome_or_verdict_invention(self) -> None:
        contracts = load("contracts")

        with self.assertRaises(ValidationError):
            contracts.ScenarioSetup(
                scenario_id="scenario-1",
                title="Rush hour",
                circumstances="A busy station.",
                stakeholder_actions=("Ask for details.",),
                expected_outcome="Policy succeeds.",
            )
        with self.assertRaises(ValidationError):
            contracts.ContextSource(
                source_id="context-1",
                title="Survey",
                text="Riders describe crowding.",
                policy_verdict="Reject policy.",
            )

    def test_validation_binds_result_to_the_complete_request(self) -> None:
        contracts = load("contracts")
        request = contracts.make_example_request()
        result = asyncio.run(load("fixtures").FixtureSandboxService().run(request))

        contracts.validate_sandbox_result(request, result)
        with self.assertRaisesRegex(ValueError, "run_id"):
            contracts.validate_sandbox_result(
                request,
                result.model_copy(update={"run_id": "another-run"}),
            )
        with self.assertRaisesRegex(ValueError, "fingerprint"):
            contracts.validate_sandbox_result(
                request.model_copy(update={"max_rounds": request.max_rounds + 1}),
                result,
            )

    def test_validation_rejects_unknown_and_duplicate_references(self) -> None:
        contracts = load("contracts")
        request = contracts.make_example_request()
        result = asyncio.run(load("fixtures").FixtureSandboxService().run(request))

        bad_author = result.messages[0].model_copy(update={"persona_id": "missing-persona"})
        with self.assertRaisesRegex(ValueError, "unknown persona"):
            contracts.validate_sandbox_result(
                request,
                result.model_copy(update={"messages": (bad_author, *result.messages[1:])}),
            )

        bad_source = result.messages[0].model_copy(update={"source_refs": ("missing-source",)})
        with self.assertRaisesRegex(ValueError, "unknown source"):
            contracts.validate_sandbox_result(
                request,
                result.model_copy(update={"messages": (bad_source, *result.messages[1:])}),
            )

        with self.assertRaisesRegex(ValueError, "duplicate persona"):
            contracts.validate_sandbox_result(
                request,
                result.model_copy(update={"personas": (*result.personas, result.personas[0])}),
            )
        with self.assertRaisesRegex(ValueError, "duplicate message"):
            contracts.validate_sandbox_result(
                request,
                result.model_copy(update={"messages": (*result.messages, result.messages[0])}),
            )

        fake_record = result.sources[0].model_copy(update={"record_id": "message-999"})
        with self.assertRaisesRegex(ValueError, "unknown record"):
            contracts.validate_sandbox_result(
                request,
                result.model_copy(update={"sources": (fake_record, *result.sources[1:])}),
            )

    def test_boundaries_revalidate_models_after_model_copy(self) -> None:
        contracts = load("contracts")
        request = contracts.make_example_request()
        result = asyncio.run(load("fixtures").FixtureSandboxService().run(request))
        unsafe = result.messages[0].model_copy(update={"content": "残留 text"})
        copied = result.model_copy(
            update={
                "status": "completed",
                "messages": (unsafe, *result.messages[1:]),
            }
        )

        with self.assertRaises(ValidationError):
            contracts.validate_sandbox_result(request, copied)
        with self.assertRaises(ValidationError):
            contracts.public_sandbox_result(copied)

    def test_translation_status_and_round_metadata_cannot_invent_provenance(self) -> None:
        contracts = load("contracts")
        request = contracts.make_example_request()
        result = asyncio.run(load("fixtures").FixtureSandboxService().run(request))

        unavailable = result.messages[0].model_copy(
            update={"translation_status": contracts.TranslationStatus.UNAVAILABLE}
        )
        with self.assertRaisesRegex(ValueError, "unavailable translation"):
            contracts.validate_sandbox_result(
                request,
                result.model_copy(
                    update={"messages": (unavailable, *result.messages[1:])}
                ),
            )
        with self.assertRaisesRegex(ValueError, "retain original"):
            contracts.validate_sandbox_result(
                request,
                result.model_copy(update={"original_records": ()}),
            )
        wrong_original_status = result.messages[0].model_copy(
            update={"translation_status": contracts.TranslationStatus.ORIGINAL_ENGLISH}
        )
        with self.assertRaisesRegex(ValueError, "original-English"):
            contracts.validate_sandbox_result(
                request,
                result.model_copy(
                    update={
                        "messages": (wrong_original_status, *result.messages[1:])
                    }
                ),
            )
        late_round = result.messages[0].model_copy(
            update={"round_number": request.max_rounds + 1}
        )
        with self.assertRaisesRegex(ValueError, "max_rounds"):
            contracts.validate_sandbox_result(
                request,
                result.model_copy(
                    update={"messages": (late_round, *result.messages[1:])}
                ),
            )

    def test_unavailable_translation_requires_exact_public_placeholders(self) -> None:
        contracts = load("contracts")
        request = contracts.make_example_request()
        result = asyncio.run(
            load("fixtures").FixtureSandboxService(
                "partial_translation_unavailable"
            ).run(request)
        )
        invented = result.messages[1].model_copy(
            update={"content": "The policy has full stakeholder support."}
        )
        with self.assertRaisesRegex(ValueError, "placeholder"):
            contracts.validate_sandbox_result(
                request,
                result.model_copy(
                    update={"messages": (result.messages[0], invented, result.messages[2])}
                ),
            )

    def test_validation_rejects_missing_or_duplicate_reply_references(self) -> None:
        contracts = load("contracts")
        request = contracts.make_example_request()
        result = asyncio.run(load("fixtures").FixtureSandboxService().run(request))

        missing = result.messages[1].model_copy(update={"reply_to_message_ids": ("missing",)})
        with self.assertRaisesRegex(ValueError, "unknown reply"):
            contracts.validate_sandbox_result(
                request,
                result.model_copy(update={"messages": (result.messages[0], missing, *result.messages[2:])}),
            )
        duplicate = result.messages[1].model_copy(
            update={"reply_to_message_ids": (result.messages[0].message_id,) * 2}
        )
        with self.assertRaisesRegex(ValueError, "duplicate reply"):
            contracts.validate_sandbox_result(
                request,
                result.model_copy(update={"messages": (result.messages[0], duplicate, *result.messages[2:])}),
            )

    def test_validation_rejects_count_and_completed_status_contradictions(self) -> None:
        contracts = load("contracts")
        request = contracts.make_example_request()
        result = asyncio.run(load("fixtures").FixtureSandboxService().run(request))

        with self.assertRaisesRegex(ValueError, "requested_stakeholder_count"):
            contracts.validate_sandbox_result(
                request,
                result.model_copy(update={"requested_stakeholder_count": 99}),
            )
        with self.assertRaisesRegex(ValueError, "configured_stakeholder_count"):
            contracts.validate_sandbox_result(
                request,
                result.model_copy(update={"configured_stakeholder_count": 1}),
            )
        with self.assertRaisesRegex(ValueError, "completed"):
            contracts.validate_sandbox_result(
                request,
                result.model_copy(
                    update={
                        "messages": (),
                        "sources": (),
                        "original_records": (),
                        "observed_stakeholder_count": 0,
                    }
                ),
            )

    def test_english_display_guard_rejects_remaining_han_text(self) -> None:
        contracts = load("contracts")

        with self.assertRaisesRegex(ValidationError, "Han-script"):
            contracts.SandboxMessage(
                message_id="message-1",
                sequence=1,
                persona_id="persona-1",
                content="English prefix with 残留 text",
                translation_status=contracts.TranslationStatus.TRANSLATED,
            )

    def test_public_projection_is_allowlisted_and_never_contains_original_records(self) -> None:
        contracts = load("contracts")
        request = contracts.make_example_request()
        result = asyncio.run(load("fixtures").FixtureSandboxService().run(request))

        public = contracts.public_sandbox_result(result)
        serialized = json.dumps(public, ensure_ascii=False)
        self.assertNotIn("original_records", public)
        self.assertNotIn("乘客要求保留夜间服务。", serialized)
        self.assertEqual(public["execution_mode"], "fixture")

    def test_original_identity_is_stable_across_english_projection(self) -> None:
        contracts = load("contracts")
        request = contracts.make_example_request()
        result = asyncio.run(load("fixtures").FixtureSandboxService().run(request))

        messages = {message.message_id: message for message in result.messages}
        for original in result.original_records:
            translated = messages[original.record_id]
            self.assertEqual(translated.persona_id, original.speaker_id)
            self.assertEqual(translated.reply_to_message_ids, original.reply_to_record_ids)


class FixtureSandboxServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_default_fixture_is_completed_and_labelled(self) -> None:
        contracts = load("contracts")
        protocols = load("protocols")
        service = load("fixtures").FixtureSandboxService()

        self.assertIsInstance(service, protocols.SandboxService)
        result = await service.run(contracts.make_example_request())
        contracts.validate_sandbox_result(contracts.make_example_request(), result)
        self.assertEqual(result.execution_mode, contracts.ExecutionMode.FIXTURE)
        self.assertEqual(result.status, contracts.SandboxStatus.COMPLETED)
        self.assertTrue(result.messages)
        self.assertTrue(result.sources)

    async def test_translation_unavailable_fixture_is_explicit_and_partial(self) -> None:
        contracts = load("contracts")
        service = load("fixtures").FixtureSandboxService("partial_translation_unavailable")
        request = contracts.make_example_request()

        result = await service.run(request)
        contracts.validate_sandbox_result(request, result)
        self.assertEqual(result.status, contracts.SandboxStatus.PARTIAL)
        self.assertEqual(
            result.messages[1].translation_status,
            contracts.TranslationStatus.UNAVAILABLE,
        )
        self.assertIn("English translation unavailable", result.messages[1].content)
        self.assertIn("夜间服务", result.original_records[1].content)
        self.assertNotIn("夜间服务", json.dumps(contracts.public_sandbox_result(result)))

    async def test_unknown_fixture_name_is_rejected(self) -> None:
        fixtures = load("fixtures")

        with self.assertRaisesRegex(ValueError, "unknown fixture"):
            fixtures.FixtureSandboxService("live")

    async def test_fixture_matches_supported_requested_stakeholder_counts(self) -> None:
        contracts = load("contracts")
        service = load("fixtures").FixtureSandboxService()

        for count in (1, 5):
            with self.subTest(count=count):
                base = contracts.make_example_request()
                request = contracts.SandboxRequest.model_validate(
                    {**base.model_dump(), "stakeholder_count": count}
                )
                result = await service.run(request)
                contracts.validate_sandbox_result(request, result)
                self.assertEqual(result.configured_stakeholder_count, count)
                self.assertEqual(result.observed_stakeholder_count, count)
                self.assertIn("does not analyze", " ".join(result.limitations))


class ContractExportTests(unittest.TestCase):
    def test_export_is_deterministic_and_check_detects_drift(self) -> None:
        export = load("export_contracts")

        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory)
            self.assertEqual(export.main(["--output", str(destination)]), 0)
            self.assertEqual(export.main(["--output", str(destination), "--check"]), 0)
            schema = destination / "sandbox-request.schema.json"
            schema.write_text("{}\n", encoding="utf-8")
            self.assertEqual(export.main(["--output", str(destination), "--check"]), 1)

            expected = {
                "policy-input.schema.json",
                "roles.json",
                "sandbox-request.schema.json",
                "sandbox-result.schema.json",
                "fixtures/completed-public-result.json",
                "fixtures/completed-result.json",
                "fixtures/example-request.json",
                "fixtures/partial-translation-unavailable-public-result.json",
                "fixtures/partial-translation-unavailable-result.json",
            }
            actual = {
                path.relative_to(destination).as_posix()
                for path in destination.rglob("*")
                if path.is_file()
            }
            self.assertEqual(actual, expected)


if __name__ == "__main__":
    unittest.main()
