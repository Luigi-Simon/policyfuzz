# Live extraction blocker for Person 2

PR #1 is merged at `931e67b0b8f57bbb0180c42213c416d6c6f5a031`; its CI passed.
This packet records an assistant-operated rehearsal using the public synthetic
development policy and `gpt-4.1-mini`. It is not a blind result or human approval.
No specialist implementation, dependency or shared contract was changed.

## Observed result

The API accepted a new bundled-sample run with HTTP 202. The first extraction
response and its one permitted repair both reached OpenAI successfully. The run
stopped after about 52 seconds with `MALFORMED_MODEL_OUTPUT`. No contract,
finding or revision was confirmed; generation, evaluation and retesting were
not reached. Authentication worked for these requests; full live acceptance did not.

The original response bodies were not retained. A separately identified,
single-call diagnostic captured the extraction output for offline reproduction.
Its failure should not be misrepresented as an exact recording of the original
two bodies. It reproduced `SCHEMA_VALIDATION_FAILED` for five citation-hash fields.

The diagnostic returned ten rules and one unsupported clause. All eleven quoted
strings occur exactly once in the source page. All eleven proposed offsets and
all eleven proposed quote hashes are incorrect. Five hashes also fail the
64-character hexadecimal schema constraint, so parsing stops before exact
citation validation can run. Merely fixing their length would still fail the
source checks.

## Root cause and bounded fix

`backend/app/features/policy/prompts.py` requests document-global offsets and
SHA-256 quote hashes, but provides only raw page text and the document hash.
There is no per-citation catalog or hashing tool. The diagnostic shows the model
inventing metadata that Python can compute exactly.

Person 2 owns `prompts.py`, `model_io.py`, extraction normalization and their
tests. Keep the frozen public contracts and exact citation validator intact.

Recommended fix: have Python prepare verified citation entries from the normalized
document, including stable handles, exact quote text, page, global offsets and
hash. Give the model those entries and require selection of existing handles;
resolve handles back to trusted metadata before constructing public rule drafts.
If using the current provider shape as a smaller first change, supply the same
catalog and require exact copying, then retain all existing validation. That
variant still depends on correct model copying and needs live verification.

Do not accept arbitrary generated hashes, silently choose among repeated quotes,
weaken `SourceSpan`, disable validation, or turn a bad citation into confirmed
evidence. A missing, ambiguous or unknown citation must remain rejected or
explicitly unsupported. Preserve the one-repair limit and the override graph.

Acceptance checks for the fix:

- Python computes offsets/hash correctly for normalized text, Unicode, multiple
  pages, repeated quote text and expanded rules that share one source clause.
- Unknown handles and altered/missing quotes do not become trusted citations.
- Existing deterministic citation, override, exclusion and schema tests pass.
- The receipt equality gap and international-hotel conflict remain present in
  baseline extraction; the compiler must not repair them by interpretation.
- A new labelled live rehearsal reaches contract review with complete, exact
  citations before continuing to findings, revision and frozen-suite retest.

## Evidence and reproduction

All files are under `evidence/live-rehearsal-2026-09-06/`:

- `summary.json`: original attempt, request usage, durations and terminal error.
- `run-record.json`: preserved original manifest and public synthetic document.
- `diagnostic-response.json`: raw structured output from the separate diagnostic.
- `diagnostic-summary.json`: safe validation result for that diagnostic call.
- `diagnostic-validation.json`: exact field paths and eleven citation comparisons.
- `integrity.json`: SHA-256 checksums and total reported token usage.

`diagnostic-summary.json` hashes the original response text before the single
newline added on file save. `integrity.json` hashes the complete saved file bytes.
Removing exactly the final added newline reproduces the raw response hash.

For offline reproduction, validate `diagnostic-response.json` using the current
`ModelPolicyExtraction.model_validate_json(..., strict=True)`. It reports five
`quote_sha256` pattern errors. Compute each quote's hash and compare its declared
slice against the document saved in `run-record.json` to reproduce the eleven
metadata mismatches. No API key or additional provider call is required.

The three requests reported 5,603 input tokens and 6,025 output tokens in total.
This is token usage, not an inferred bill or evidence of successful extraction.

An independent code review also identified a separate schema/default issue:
the private provenance discriminator can be omitted under generated JSON Schema
but is required to dispatch the local union. Every diagnostic provenance includes
the discriminator, so that issue did not cause this captured failure.

## Integration follow-up

Person 1 can retest after Person 2 publishes the citation fix. The reviewer should
use the already authored development intent: receipts at SGD 50, international
hotel manager approval and daily meal cap SGD 100, with only `eligibility` as a
globally required dimension. Use this run's baseline ID/hash, never fixture anchors.
Preserve failed attempts and distinguish assistant-operated rehearsal decisions
from independent human benchmark confirmation. Browser, benchmark and release
acceptance remain pending.
