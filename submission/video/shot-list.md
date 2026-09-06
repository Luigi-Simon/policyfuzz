# PolicyFuzz demo shot list

**DRAFT — NO FOOTAGE OR SCREENSHOT IS CLAIMED TO EXIST.**

All application footage must come from the exact `demo-core-v1` build after Gate B and the six-hour application freeze. Use 1920×1080 capture. Keep the synthetic-data label visible. Show either **LIVE** or **CACHED** continuously when a run result is visible; never splice cached output as live. The nine rows below are the approved 4:40 sequence.

| Time | Duration | Shot and action | Required on-screen evidence | Capture blocker |
| --- | ---: | --- | --- | --- |
| 0:00–0:20 | 0:20 | Opening slide, then verified landing view | Narrow T&E claim; synthetic label | Final deck frame and frozen landing view |
| 0:20–0:45 | 0:25 | User/problem visual with bounded manual-review comparison | Hypothesis label; “small internal benchmark” wording | Two completed manual-review records and approved wording |
| 0:45–1:10 | 0:25 | Upload synthetic policy, inspect cited rules, confirm contract | Citation anchors; unsupported-language state; explicit confirmation event | Clean `demo-core-v1` run and capture-safe synthetic input |
| 1:10–2:25 | 1:15 | Open threshold, hotel-conflict, and split-claim findings in turn | Exact witness, trace, citations, deterministic state for each | Verified development report and matching UI views |
| 2:25–2:50 | 0:25 | Move from measured missing coverage through one targeted cycle | Before/after coverage; at most one targeted event; mode badge | Event log, metric evidence key, and continuous run capture |
| 2:50–3:25 | 0:35 | Decide supported findings, inspect structured revision, confirm apply | Candidate restriction; reviewer severity; proposal; session confirmation | Verified finding set and one-session confirmation trace |
| 3:25–3:55 | 0:30 | Compare identical frozen-suite runs and reveal gate results | Same suite hash; all seven acceptance gates; evidence-linked result | Complete comparison artifact from frozen run |
| 3:55–4:20 | 0:25 | Architecture/trust-boundary visual over selected UI proof | Model tasks, deterministic authorities, three human gates, redaction note | Diagram checked against frozen code and Gate B evidence |
| 4:20–4:40 | 0:20 | Evidence card, limits, repository close | Referenced verified metrics; blind eligibility; limits; repository URL | Final metrics, independent review, link, and closing wording approval |

Total planned duration: **4:40 (280 seconds)**.

## Capture log to complete during recording

For every application shot, record take filename, UTC capture time, source commit, mode, source artifact IDs, and whether any cut bridges different runs. Reject a take if the mode badge disappears, a citation is unreadable, a notification exposes local data, or the run identity changes without a visible transition.
