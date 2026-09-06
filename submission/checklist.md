# Submission readiness checklist

**Status: DRAFT / NOT READY FOR GOLD SCORING OR RECORDING.**

Use only `PASS` when the cited public artifact or direct final observation proves the row. All other rows remain `PENDING`. Do not add a reviewer name, date, hash, metric, screenshot, caption, validation result, or repository URL before it exists.

## Official constraints and final artifacts

| Status | Requirement | Evidence required |
| --- | --- | --- |
| PENDING | One project/workflow submission | Person 1 final package manifest |
| PENDING | Complete selected candidate directory below 5,000,000,000 bytes after only the documented exclusions | Final verifier/package output, selected root, exclusion record, and manifest byte count |
| PENDING | Deck PDF contains 1–10 pages | `pdfinfo` output from final `submission/deck/PolicyFuzz-Pitch.pdf` |
| PENDING | Digital-solution video duration is at most 300.0 seconds | `ffprobe` output from final `submission/video/PolicyFuzz-Demo.mp4` |
| PENDING | Video contains a supported real video stream and fully decodes | Stream metadata and successful full `ffmpeg` decode |
| PENDING | Final deliverable basenames are unique and no artifact was overwritten; repeated ordinary source basenames are permitted | Final candidate manifest |
| PENDING | Nine-slide narrative follows the approved slide map | Final deck review; separate deck author owns deck files |
| PENDING | Video follows all nine approved segments totaling 4:40 | Final edit timeline and recording checklist |

## Evidence and claims

| Status | Requirement | Evidence required |
| --- | --- | --- |
| PASS | Public benchmark-v2 archive/schema integrity checks are recorded | `submission/evidence/benchmark-v2/README.md` and public metadata |
| PASS | Public benchmark-v2 limitations are recorded: agent-authored, sealed after development, human review pending, no engine/provider run, headline scoring ineligible | `submission/evidence/benchmark-v2/provenance.json` |
| PENDING | Active blind candidate is approved by Person 1 and independently reviewed | Active-candidate record and signed review evidence |
| PENDING | `verified-metrics.json` contains all required metrics with consistent arithmetic and actual source hashes | Final evidence manifest plus verifier output |
| PENDING | Every displayed measured value uses the canonical `[[metric:key|display|data|mode|verification|blind-eligibility]]` token; no `{{metric:*}}` remains | Extracted non-empty deck text, mandatory final script, and verifier output |
| PENDING | Structured submission, metric, source, and per-claim provenance agree on synthetic data, actual live/cached mode, verified status, and eligible blind evidence | Final evidence manifest and verifier output; boilerplate labels are insufficient |
| PENDING | Any reported first-run blind discovery recall is independently measured and reconciled | A post-run gold-assisted assessment must not be relabelled as first-run discovery recall; retain N/A/unmeasured until separate valid evidence exists |
| PENDING | No legal-compliance, exhaustive-discovery, market-validation, invented-ROI, customer, or automatic-publication claim appears | Final two-person claim review |

## Current rehearsal evidence — not final submission acceptance

| Status | Observation | Evidence |
| --- | --- | --- |
| PASS | Public cached synthetic record currently contains 10 scenarios, 3 baseline findings, and 0 remaining findings | `samples/cached-demo/summary.json`; `submission/evidence/demo-run.json` |
| PASS | Current cached comparison has all seven patch-acceptance gates true and 12 assertions move from inconclusive to passing | `samples/cached-demo/run-record.json`; `submission/evidence/demo-run.json` |
| PASS | Current run uses four scripted model responses and zero actual provider calls | `samples/cached-demo/summary.json` |
| PASS | Current minimum coverage is satisfied without a targeted cycle | `samples/cached-demo/run-record.json`: 10/10 rules, 3/3 invariants, 23/26 predicate branches, `targeted_cycles: 0` |
| PASS | Draft caption timing can be regenerated from the timed narration | `node --test submission/video/build-captions.test.mjs`; `node submission/video/build-captions.mjs` |
| PENDING | Automated browser rehearsal at 375 px and 1440 px, keyboard-only | `submission/evidence/browser-rehearsal.md` records the failed capability attempts; rerun in an environment with a local browser binary |

## Persons 1–4 handoff dependencies

| Status | Owner | Required handoff evidence |
| --- | --- | --- |
| PENDING | Person 1 integration | Clean Gate B report, frozen commit/tag, run modes, end-to-end/replay results, candidate activation decision, final package inputs |
| PENDING | Person 2 policy | Public interface summary, tests, compile/citation evidence, limitations, and exact source artifact paths/hashes |
| PENDING | Person 3 fuzzing | Public interface summary, generation-bound evidence, tests, scenario/coverage artifacts, limitations, and hashes |
| PENDING | Person 4 evaluation | Deterministic engine/version evidence, frozen suite, development/control/blind reports, metric arithmetic, seven-gate results, limitations, and hashes |

## Freeze and capture

| Status | Requirement | Evidence required |
| --- | --- | --- |
| PENDING | `demo-core-v1` exists at the Gate B verified commit | Annotated tag and Gate B report |
| PENDING | Six-hour application freeze completed before first capture | Tag timestamp, first-capture timestamp, elapsed-time calculation |
| PENDING | Captures use only the exact frozen build | Capture log with commit and mode for every take |
| PENDING | No application-affecting change invalidated the freeze | Clean diff and Person 1 freeze review |
| PENDING | Captioned final video and final PDF exist | Final artifact paths and SHA-256 values |

## Independent reviews

| Status | Review | Reviewer | Commit | Evidence |
| --- | --- | --- | --- | --- |
| PENDING | Claim-by-claim evidence review by a teammate other than Person 5 | Unassigned | Unrecorded | Review log required |
| PENDING | Clean-checkout demo plus caption/audio review by a different teammate | Unassigned | Unrecorded | Review log required |

## Final command

Run only after all dependencies above exist:

```bash
python scripts/verify_submission.py \
  --deck submission/deck/PolicyFuzz-Pitch.pdf \
  --video submission/video/PolicyFuzz-Demo.mp4 \
  --evidence submission/evidence/verified-metrics.json \
  --candidate-root .
```

`--candidate-root` (alias `--package-root`) selects the complete directory scanned for Task 25 alignment. `scripts.verify_submission.enumerate_candidate_files(candidate_root)` returns the deterministic root-relative list used by the verifier's byte-count and final-deliverable-name checks; Task 25 must package that exact list and record a matching manifest. The fixed exclusions are `.git`, `.superpowers`, actual environment files (`.env` and `.env.*` except the exact safe `.env.example` basename), dependency/virtual-environment directories, cache/coverage/build/dist output, bytecode, purpose-specific raw/backup-video directories, and raw/backup video files. Root and nested `.env.example` setup templates are included. Generic directories named `raw`, `backup`, or `backups` are included, as are all other arbitrary unlisted files; symlinks and private paths are rejected. Repeated ordinary source basenames are allowed, while final deliverable basenames must be unique. Final packaging acceptance remains pending until Person 1 provides the matching Task 25 manifest. `submission/video/script.md` is mandatory through the evidence manifest and is audited without a `--source` flag. Record the actual command output here only after execution. A nonzero result is a blocker; there is no bypass flag.
