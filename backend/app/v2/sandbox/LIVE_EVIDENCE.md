# Sandbox verification and handoff

This is a historical record of a real synthetic run on 2026-09-10 (Asia/Singapore).
It is not a fixture substitute for future live requests. No credentials, raw
provider diagnostics, full persona prompts, or backend-only originals are included.

## Successful live run

- Mode: `live`; status: `completed`.
- Request/run ID: `sandbox-v2-live-20260910-03`.
- Simulation ID: `sim_f8440f07b2a5`.
- Full request fingerprint:
  `e0d498cd3b9694a6a89bd217b16c52a75bb0aa7cabb317ed6db14fd4c43581f9`.
- Policy: the shared synthetic late-night transit pilot, exact input in
  [evidence/request.json](evidence/request.json).
- Seed: three night-shift hospital workers, with practical/cost-conscious,
  personal-safety, and wheelchair-accessibility perspectives; riders, not officials.
- Requested/configured/observed participants: **3 / 3 / 3**.
- Native rounds: **2**. Every participant was scheduled in each round.
- Messages: **9**, consisting of three seeded openings and six native comments.
- Verified cross-participant reply authors: **3 / 3**.
- Returned rounds: openings have null; comments have 1 or 2. Wall-clock message
  timestamps remain null because the source clock records simulation steps.
- Errors: none. Qualitative-evidence, seeded-opening, and unsupported-claim
  limitations remain visible in the result.

The generated roster contains Anna Rodriguez, Marcus White and Lila Thompson.
These are simulated identities, not real participants or a public survey.
Their descriptions follow the worker, safety and accessibility constraints.

Example actual comment by Lila Thompson:

> Ensuring affordability for late-night services is critical, especially for those of us with disabilities who rely on accessible transport options. How will cost structures support this need? #AccessibleTransport

Its exact citeable message ID is:

```text
mirofish:sim_f8440f07b2a5:e0d498cd3b9694a6a89bd217b16c52a75bb0aa7cabb317ed6db14fd4c43581f9:comment:2
```

The message links to another participant's recorded opening, not a reconstructed
conversation. The complete allowlisted result is
[evidence/public-result.json](evidence/public-result.json). The Judge can consume
that shape directly and cite any actual returned message ID. Simon's Judge was
not run in this work packet; the combined Judge-citation milestone still needs
his integration.

## Setup used

- Foundation commit: `786b6d70817064cc9ad1967475606a671c0e604e`.
- Implementation branch: `p3/feat-v2-sandbox`; intended integration base:
  `p1/feat-policyfuzz-v2`.
- Worktree: `/Users/a123/Desktop/policyfuzz/policyfuzz-sandbox`.
- The existing `/Users/a123/Desktop/policyfuzz/policyfuzzCode` checkout and its
  uncommitted backend/frontend work were preserved.
- MiroFish installation: `/Users/a123/Desktop/mirofish/MiroFish`, local checkout
  HEAD `39d849138ef254f6c737ab4c4705e5545dbe31d4`. This is an existing local
  installation, not a clean-install compatibility claim for every upstream version.
- MiroFish's existing Python 3.12 environment and configured provider were used.
  The PolicyFuzz environment reported OpenAI SDK 3.8.0, httpx 0.28.1 and Pydantic
  2.13.5. No root dependencies were changed.
- Sandbox extension served on `http://127.0.0.1:5002`; existing port 5001 was not
  reused. Credentials came from local configuration and were not printed.
- Native job journal and source evidence stay in MiroFish's uploads directory.
  Development-only internal smoke outputs are in
  `/private/tmp/policyfuzz-sandbox-v2-live-peers`.

From the repository root, the server command was:

```bash
/Users/a123/Desktop/mirofish/MiroFish/backend/.venv/bin/python \
  backend/app/v2/sandbox/serve_mirofish.py \
  --root /Users/a123/Desktop/mirofish/MiroFish --port 5002
```

With matching provider settings in the environment, the synthetic smoke command
from `backend` was equivalent to:

```bash
python -m app.v2.sandbox.smoke --live \
  --request-id sandbox-v2-live-20260910-03 --count 3 --rounds 2 \
  --seed 'Three night-shift hospital workers: one practical and cost-conscious, one cautious about personal safety, and one wheelchair user focused on accessible journeys. They are riders, not officials.' \
  --output /private/tmp/policyfuzz-sandbox-v2-live-peers
```

Reusing these exact settings attaches to the existing job; use a new request ID
for a fresh experiment. Do not overwrite the historical evidence with a new run.

## Earlier checks and practical limits

An earlier two-person run produced seven English messages, with both participants
replying to others. It was marked partial while the simulation-step clock was
still treated as unsupported timestamp data. A three-person run using the default
feed produced nine messages but only two verified cross-participant reply authors;
it was also marked partial. These checks established why the final wrapper needs
explicit clock provenance and peer-feed controls. They were not relabelled as
successful runs.

An earlier participant also asserted safety measures not stated in the policy.
The final prompt explicitly distinguishes proposals and uncertainty from announced
provisions, and the returned limitations warn the Judge to verify participant
claims. The successful run verifies integration and evidence identity, not broad
policy-analysis accuracy or freedom from model hallucination.

Automated Sandbox tests use fake transports/providers and local SQLite only.
Foundation checks passed: 21 contract/fixture tests, schema drift checks and the
labelled offline fixture smoke. The full backend regression run passed **1,615
tests and two subtests**, with one unchanged packaging failure:
`test_script_entry_point_runs_from_outside_repository` cannot import
`scripts.verify_submission`. The packaging file's blob hash matches the foundation
exactly: `4a121cb47ca1aba47f04181fc944571fa03c0091`. Its fix belongs to Simon.
The recorded HTTP smoke passes when the environment permits its local test port.

Final Sandbox-only test counts and the exact implementation commit are included
in the delivery message. No PR was opened or message sent to Simon. The code,
public interface, setup commands, shared-contract requests and limitations are
ready for review through the [integration guide](README.md).
