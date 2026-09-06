# Recording and export checklist

**DRAFT — RECORDING HAS NOT STARTED. Every item remains pending until supported by the named artifact or observation.**

## Evidence gate

- [ ] Person 1 provides a clean `demo-core-v1` commit and `team/person-1-integration/evidence/gate-b-verification.json`.
- [ ] Six clock hours have elapsed since the `demo-core-v1` tag; record tag timestamp, planned capture timestamp, and elapsed duration.
- [ ] No backend/frontend application code, prompt, provider configuration, fixture, benchmark, or generated contract changed during the freeze.
- [ ] The final evidence file is `submission/evidence/verified-metrics.json`, is scoring-eligible, and every required metric points to a hash-verified artifact from the frozen commit/suite/engine.
- [ ] Independent human review makes any used blind score eligible; otherwise remove the blind numeric claim and retain the limitation.
- [ ] Final script and deck contain no unresolved `{{metric:*}}` tokens. Every measured value uses `[[metric:key|display|data|mode|verification|blind-eligibility]]`, with all fields matching structured evidence provenance.

## Capture preparation

- [ ] Use the exact shot list: nine segments, target 4:40, hard maximum 5:00.
- [ ] Set capture to 1920×1080 and confirm readable browser zoom, focus indicators, cursor, and notifications disabled.
- [ ] Use only the capture-safe synthetic policy and public display-safe `RunView`; inspect frames for prompts, credentials, full pasted documents, private labels, or local paths.
- [ ] Start one clean verified session and preserve its run identity across the workflow.
- [ ] Keep a visible LIVE or CACHED badge whenever results are shown. If cached, keep the badge visible through every related cut.
- [ ] Capture exact witnesses, traces, citations, confirmation events, suite hashes, and the complete seven-gate report before narration.
- [ ] Record a take log with filenames, commit, mode, UTC times, and evidence artifact IDs.

## Narration and captions

- [ ] Rehearse against evidence-backed wording; do not improvise legal compliance, exhaustive discovery, market validation, ROI, publication, or customer claims.
- [ ] Call the data synthetic and the comparison a small internal benchmark, never user research.
- [ ] Describe model outputs as proposals and deterministic results as verdicts only where the captured evidence supports that distinction.
- [ ] Record clear narration without clipped starts, long silence, or claims that outrun the displayed evidence.
- [ ] Create captions from the final audio, proofread technical terms and numbers against the evidence manifest, and check timing through the full video.
- [x] Generate a draft timing rehearsal from the current narration with `node submission/video/build-captions.mjs`; this does not satisfy final caption or audio review.

## Export and mechanical validation

- [ ] Export the selected final take as 1080p H.264 to `submission/video/PolicyFuzz-Demo.mp4`; keep it below 100 MB where practical and below the official package limit.
- [ ] Package only the final MP4. Keep backup/raw takes outside the candidate package.
- [ ] Confirm duration is at most 300.0 seconds and a full `ffmpeg` decode completes without error.
- [ ] Confirm the deck PDF has 1–10 pages, final deliverable basenames are unique, and the complete selected candidate directory is below 5,000,000,000 bytes after only the verifier's documented exclusions.
- [ ] Confirm extracted deck text is non-empty and the evidence manifest declares `submission/video/script.md` with exact structured provenance.
- [ ] Run `python scripts/verify_submission.py --deck submission/deck/PolicyFuzz-Pitch.pdf --video submission/video/PolicyFuzz-Demo.mp4 --evidence submission/evidence/verified-metrics.json --candidate-root .` and attach its actual output.

## Human review and package handoff

- [ ] A teammate other than Person 5 verifies every claim against the evidence; record their name only after review occurs.
- [ ] A different teammate runs the demo from a clean checkout and verifies captions/audio; record their name only after review occurs.
- [ ] Address review findings, rerun mechanical verification, and recompute final artifact hashes.
- [ ] Hand Person 1 the verified source paths and actual command output for Task 25 packaging. Require the packager to use `scripts.verify_submission.enumerate_candidate_files(candidate_root)` as its exact member list and attach the matching manifest; packaging acceptance remains pending until that evidence exists.
