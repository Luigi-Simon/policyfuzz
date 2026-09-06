import hashlib
import json
import subprocess
import sys
import textwrap
from pathlib import Path

from app.domain.models import (
    CompilePolicyRequest,
    Effect,
    PolicyExtraction,
    RuleDraft,
    SourceSpan,
    TextRuleProvenance,
)
from app.features.policy.compiler import compile_baseline_policy
from app.features.policy.ingest import ingest_policy_text


TEXT = "Meals require receipts."


def _request() -> CompilePolicyRequest:
    document = ingest_policy_text(
        title="Synthetic policy", text=TEXT, source_type="pasted_text"
    )
    span = SourceSpan(
        page=1,
        start=0,
        end=len(TEXT),
        quote=TEXT,
        quote_sha256=hashlib.sha256(TEXT.encode()).hexdigest(),
    )
    extraction = PolicyExtraction(
        document_sha256=document.document_sha256,
        rules=(
            RuleDraft(
                description="Meal receipt rule",
                when=(),
                effects=(
                    Effect(dimension="receipt_requirement", value="required"),
                ),
                provenance=TextRuleProvenance(citation_id="c1", span=span),
            ),
        ),
    )
    return CompilePolicyRequest(document=document, extraction=extraction)


def test_end_to_end_deterministic_pipeline_produces_person_3_policy_ir() -> None:
    result = compile_baseline_policy(_request())

    assert result.policy.document_sha256 == _request().document.document_sha256
    assert result.policy.rules[0].provenance.kind == "text_citation"
    assert result.policy.review_status == "provisional"
    assert result.excluded_rule_count == 0


def test_document_rule_and_policy_ids_are_stable_across_processes() -> None:
    backend = Path(__file__).parents[3]
    script = textwrap.dedent(
        """
        import hashlib, json
        from app.domain.models import (
            CompilePolicyRequest, Effect, PolicyExtraction, RuleDraft,
            SourceSpan, TextRuleProvenance,
        )
        from app.features.policy.compiler import compile_baseline_policy
        from app.features.policy.ingest import ingest_policy_text
        text = "Meals require receipts."
        document = ingest_policy_text(
            title="Synthetic", text=text, source_type="pasted_text"
        )
        span = SourceSpan(
            page=1, start=0, end=len(text), quote=text,
            quote_sha256=hashlib.sha256(text.encode()).hexdigest(),
        )
        draft = RuleDraft(
            description="Receipt", when=(),
            effects=(Effect(
                dimension="receipt_requirement", value="required"
            ),),
            provenance=TextRuleProvenance(citation_id="c", span=span),
        )
        request = CompilePolicyRequest(
            document=document,
            extraction=PolicyExtraction(
                document_sha256=document.document_sha256, rules=(draft,)
            ),
        )
        result = compile_baseline_policy(request)
        print(json.dumps([
            document.document_id,
            result.policy.rules[0].rule_id,
            result.policy.policy_id,
        ]))
        """
    )
    outputs = [
        subprocess.run(
            [sys.executable, "-c", script],
            cwd=backend,
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        for _ in range(2)
    ]

    assert outputs[0] == outputs[1]
    assert len(json.loads(outputs[0])) == 3
