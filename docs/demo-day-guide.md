# PolicyFuzz rehearsal guide

**Using the Maju Forest semifinal demo?** Start with the [Maju demo guide](maju-forest-demo.md). It covers the new exploratory preset, separate simulation setup and revised presentation story. The expense walkthrough and recorded results below apply to the original demo.

Use this to prepare tonight and start tomorrow. This is a rehearsal guide, not a completed browser test or final submission approval.

## What you can do from your phone tonight

1. Read the [nine-slide pitch draft](../submission/deck/PolicyFuzz-Pitch-Draft.pdf) and practise the 30-second explanation below.
2. Choose who presents, who operates the laptop, and who answers architecture/evaluation questions. Person 1 can explain integration; Person 4 can explain verdicts; Person 5 can operate and narrate the interface.
3. Ask the person running the backend to configure their own authorized API project. A key entered on their laptop configures that backend. Never send the key to teammates or commit it.
4. Agree on a labelled fallback: interactive mock for explaining screens, cached API for the recorded result. Neither is a live-model demonstration.

### A 30-second explanation

PolicyFuzz helps a policy owner test a travel-and-expense policy before employees hit its edge cases. It turns supported clauses into cited rules, asks the owner to confirm the intended behaviour, then tests boundaries and combinations. When a problem is confirmed, the owner can approve a structured revision and rerun the same frozen tests. AI proposes interpretations and scenarios; Python produces the verdicts and regression evidence.

## Know which mode you are showing

| Mode | Backend | Frontend | What it establishes |
|---|---|---|---|
| Interactive mock | Not needed | `VITE_DATA_MODE=mock` | Authored synthetic screens and confirmation interactions; entered policy text is not evaluated |
| Recorded API demo | `APP_MODE=cached` | `VITE_DATA_MODE=http` | Real local HTTP transport serving a completed synthetic recording; no provider calls |
| Live run | `APP_MODE=live`, model and key | `VITE_DATA_MODE=http` | A fresh run using the configured provider; result and latency must be observed |

The recorded API demo can go straight to Comparison. It cannot reconstruct the earlier confirmation screens from a completed public snapshot. Use mock mode to rehearse those screens. Do not combine captures from separate modes into an apparently continuous live run.

## First laptop setup: Windows PowerShell

For these commands, install Git, Python 3.12, and Node.js 20 or newer first. Open PowerShell and clone once:

```powershell
git clone https://github.com/Luigi-Simon/policyfuzz.git
cd policyfuzz
py -3.12 -m venv backend/.venv
backend\.venv\Scripts\python.exe -m pip install -e './backend[dev]'
npm --prefix frontend ci
backend\.venv\Scripts\python.exe scripts/check_setup.py --mode cached
```

If you already have a clone, use that folder and update your clean checkout with `git pull --ff-only`; do not clone into the existing folder. If Git reports local changes or divergence, preserve them and resolve the update before recording.

The checker does not contact OpenAI, start servers or change files. It checks local prerequisites and configuration, validates the cached run's evidence links in cached mode, and constructs/closes the SDK with a dummy key in live mode. A passing check does not verify a key, account credits, model access, ports or browser behaviour. The backend does not automatically load `.env`.

### Start the recorded API demo

Terminal 1, from the repository root:

```powershell
$env:APP_MODE='cached'
$env:POLICYFUZZ_ALLOWED_ORIGIN='http://127.0.0.1:5173'
backend\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
```

Terminal 2, also from the repository root:

```powershell
$env:VITE_DATA_MODE='http'
$env:VITE_API_BASE_URL=''
npm --prefix frontend run dev -- --host 127.0.0.1 --port 5173 --strictPort
```

Open <http://127.0.0.1:5173>. Select **Bundled sample**, enter a policy title, choose **Development reimbursement policy**, acknowledge non-confidential input and select **Analyze policy**. Keep the cached badge visible.

Stop each server with Ctrl+C in its terminal. The commands use a fixed port and omit auto-reload to avoid an incidental file save restarting the backend during a run. A server restart loses in-memory runs.

### Rehearse all four screens offline

Stop Vite in Terminal 2 and run:

```powershell
$env:VITE_DATA_MODE='mock'
npm --prefix frontend run dev -- --host 127.0.0.1 --port 5173 --strictPort
```

Reload the page. Start with the bundled sample and a title. At the contract screen, inspect and acknowledge each rule, confirm every required dimension and select three to five intent invariants. In the authored finding screen, accepting the daily-cap finding `synthetic-finding-cap` leads to the prepared revision. Review the proposed change, confirm it, then inspect Comparison. Other finding decisions may correctly end with no revision. These are rehearsal decisions on authored fixtures, not human approval evidence for the benchmark.

### Enable live AI when the backend operator is ready

Stop the backend. In Terminal 1, from the repository root:

```powershell
$env:APP_MODE='live'
$env:LLM_PROVIDER='openai'
$env:LLM_MODEL='gpt-4.1-mini'
$policyFuzzKey = Read-Host 'OpenAI API key' -AsSecureString
$env:OPENAI_API_KEY = [System.Net.NetworkCredential]::new('', $policyFuzzKey).Password
Remove-Variable policyFuzzKey
backend\.venv\Scripts\python.exe scripts/check_setup.py --mode live
```

Use an authorized project with access to the chosen model. `gpt-4.1-mini` is the documented setup example, not a claim that this project's live run has passed. The current adapter uses Chat Completions, JSON-schema output and sampling parameters; another model must support that request format. A model name from ChatGPT is not automatically a compatible API model ID.

Resolve any failed local checks, then start the backend with the same Uvicorn command above. Restart Terminal 2's Vite process with `VITE_DATA_MODE=http`, then reload the browser and start a new run. Review each actual contract, finding and revision rather than applying the mock script mechanically. Live analysis can return different results.

If the client cannot initialize, check the backend installation and configured proxy. A SOCKS proxy also needs `socksio` in that environment: `backend\.venv\Scripts\python.exe -m pip install socksio`. This dependency is only needed when using SOCKS; keep any required network proxy configured. If cached evidence validation fails, restore `samples/cached-demo` from the same repository version and run `backend\.venv\Scripts\python.exe scripts/replay_check.py` before rehearsing.

The secret exists in that terminal's environment until removed or the terminal closes. It is not written to a file by these commands. Re-enter it when opening a new backend terminal. Do not put it in any `VITE_*` variable or `.env.example`. Share only redacted errors and run results.

## Five-minute rehearsal sequence

This timing is a rehearsal target, not measured application latency. Allow a separate complete live run to establish actual timing.

| Time | Show or explain | Point to make |
|---|---|---|
| 0:00–0:30 | Problem and intended reviewer | Edge cases need reusable tests, not just a prose review |
| 0:30–1:15 | Input & contract | Source citations and owner-confirmed intent anchor the test |
| 1:15–2:00 | Run evidence | Scenarios have traces; coverage determines whether one targeted cycle is needed |
| 2:00–3:15 | Findings & revision | Show a witness and the specific structured change it motivates |
| 3:15–4:15 | Comparison | The suite hash stays the same; inspect fixes and regression gates |
| 4:15–5:00 | Architecture, evidence and limits | Explain what is measured and what still needs validation |

The current scripted development recording has **10 scenarios, 3 baseline defects, 0 remaining defects and all 7 acceptance checks passing**. It uses **4 scripted model responses and 0 actual provider calls**. Source: [recorded summary](../samples/cached-demo/summary.json). Its initial coverage was sufficient; do not narrate an adaptive call that did not happen. These figures are not blind recall or live-provider performance.

## Questions to practise

| Question | Answer |
|---|---|
| Why not ask a chatbot to review the policy? | We preserve cited executable rules, independent confirmed expectations and a frozen regression suite, so a proposed change can be checked reproducibly. |
| Who decides what the policy should mean? | The policy owner confirms the extracted interpretation and three to five intended invariants before scored tests run. |
| What makes it agentic? | The coordinator invokes specialist stages, observes coverage, can request one targeted generation cycle, then manages revision and retesting around human confirmations. |
| Is the AI grading itself? | Model-generated exploratory scenarios cannot supply authoritative scored answers. Deterministic evaluation uses confirmed intent or independent mechanical/gold assertions. |
| What happens when a clause is unsupported? | It remains visible and limits conclusions. The system must not silently turn unsupported wording into a supported rule. |
| Does a successful patch prove legal compliance? | No. It establishes the stated acceptance conditions on the frozen supported suite. Generated wording remains unverified. |
| How much money or review time does this save? | That is a hypothesis to measure. We have not established customer savings or a manual-review advantage. |
| Can it handle any policy or PDF? | This MVP is bounded to English travel-and-expense text, SGD amounts, up to 12 rules and 15 scenarios. PDF/OCR and arbitrary policy domains are outside the core build. |
| What did Person 1 own? | Shared models/protocols, safe provider integration, coordinator/state, FastAPI, fixtures, CI and integration evidence. Specialist ownership is documented in the five work packets. |

## If tomorrow's run fails

| Symptom | Next action |
|---|---|
| Python or Node not found | Install the required runtime, reopen PowerShell, rerun the setup checker |
| `npm.ps1` is blocked | Use `npm.cmd` in the shown commands if available; do not change a managed machine's execution policy |
| Port 5173 or 8000 is occupied | Stop your earlier PolicyFuzz server; do not kill an unidentified process |
| UI cannot connect | Keep both terminals open; confirm backend port 8000 and HTTP frontend mode; restart Vite after environment changes |
| Live badge appears but analysis fails | Mode selection is not authentication proof. Check key/project/model access and the redacted error; preserve the failed attempt |
| Provider unavailable | This public error can cover authentication, quota, timeout or request rejection. Do not assume buying credits or making a new key solves it |
| Confirm button refuses to advance | Read the inline message; acknowledge every rule/dimension and select the required number of invariants |
| No revision is proposed | Check accepted findings and the displayed terminal reason; a revision is not guaranteed |
| Run disappears | Runs are in memory and expire within one hour; deletion or server restart removes them |
| Network/provider is unavailable | Announce the switch to cached or mock mode; retain the visible label |

## What to collect tomorrow

- Record the Git commit, selected mode, model ID for live runs, run ID, elapsed time and pass/failure outcome. Do not include keys, full private policies or prompts.
- Complete browser checks at 1440×900 and 375×812: keyboard navigation, focus, readable errors, no horizontal clipping, trace drawer open/close, all confirmations, comparison and deletion.
- Capture actual screens and preserve failed attempts. The local checker and automated tests do not replace this browser evidence.
- Follow the [remaining release gates](implementation-status.md#remaining-release-gates) for independent reviews, blind measurement, Gate B, the six-hour freeze and final media. This guide does not grant those approvals or start a freeze timer.
