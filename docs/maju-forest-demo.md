# Maju Forest semifinal demo

**Show a hypothetical policy rehearsal, not an official redevelopment announcement or an environmental forecast.** The supplied government attribution, site area, housing yield, dates, corridor size, and ecological statements are unverified scenario assumptions. The [source text](../samples/demos/maju-forest/policy.txt) is preserved verbatim for traceability.

## The story

> PolicyFuzz helps reviewers explore how different fictional stakeholders might interpret a proposed framework. In this hypothetical Maju Forest scenario, it can surface candidate questions about housing delivery, construction sequencing, habitat protection, and accountability. Reviewers inspect the source and simulated discussion, then decide what needs evidence or clearer wording.

This demonstration uses the **exploratory simulation** path. The core travel-and-expense evaluator remains a separate, narrower capability. The Maju document does not become a validated environmental model by passing through PolicyFuzz.

## Prepare the laptop

1. Install the core, frontend, and separate engine environments using the [root setup](../README.md) and [engine setup](../engine/README.md).
2. Configure the engine's authorized model and key server-side. The engine uses `LLM_API_KEY` and `LLM_MODEL_NAME`; the core uses different variables. Keep the frontend in HTTP mode for a fresh simulation.
3. Start the separate MiroFish project and configure `MIROFISH_BASE_URL` in the engine environment. From this repository, `npm run dev -- --agents` starts the core, engine, and frontend; it does not install or start MiroFish.
4. Select **Use Maju Forest demo**. It fills **Exploratory stakeholder simulation** with the source text, audience, and a five-agent request; it does not submit or grant permission. Check the hypothetical label, title, policy text, five audience groups, and [seed](../samples/demos/maju-forest/seed.txt). Five synthetic participants is a rehearsal setting, not a claim of statistical representativeness.
5. Acknowledge the non-confidential provider input and separate external-processing/retention notice, then select **Start exploratory simulation**. Save its run ID, commit, selected mode, elapsed time, and actual completion/capture status. This guide contains no completed live-run evidence.

The offline extraction heuristic is explicitly unverified. If live extraction fails, the simulator is unavailable, or conversation capture is incomplete, preserve that status. Do not narrate a successful live swarm over a mock screen or an empty capture. A recorded fallback must show a previously completed run and remain labelled as recorded.

## Demonstration sequence

This is a four-minute narration target, not measured application latency. Start any slow live preparation ahead of the pitch and be clear about when the displayed run was generated.

| Time | Show | Explain |
|---|---|---|
| 0:00–0:30 | Hypothetical label and original framework | A short policy states ambitious goals but leaves some implementation details open. We are testing how it might be interpreted. |
| 0:30–1:00 | Five synthetic audience groups and seed | Home buyers, nearby residents, conservation researchers, planners, and implementers bring different questions. Their views are not prescribed. |
| 1:00–2:00 | Actual provisional extraction and **Agent conversation evidence** | Inspect a source quotation and one or two messages actually produced by this run. Separate what the document says from what a participant assumes. |
| 2:00–3:00 | **Candidate agent observations** and missing evidence | Explore a timing, monitoring, or accountability question that the run actually raised. A missing detail in this excerpt does not establish a failure in a real planning process. |
| 3:00–4:00 | Human review and next draft | Show how a reviewer could turn a candidate question into a more explicit commitment. Explain the evidence and approvals still needed. |

If the actual run does not raise a prepared question, introduce it as **our review question**, not as an AI finding. An absent citation or a failed extraction is a limitation to report, not a reason to invent an executable rule.

## Neutral review prompts

These questions are prepared prompts, not measured findings:

| Topic | Question for reviewers | Possible commitment to consider |
|---|---|---|
| Sequencing | What must be in place before each clearing phase? | Identify a readiness check and the party responsible for documenting it. |
| Displacement | What does “moderate” mean for each affected population? | Name the measures, baseline evidence, and review process used to interpret displacement. |
| Monitoring | Who reports results and acts on them? | Specify publication timing, responsible roles, and follow-up duties. |
| Pause criteria | What new evidence changes the plan? | Define a process for pausing or redesigning work and assigning decision authority. |
| Tradeoffs | What happens if housing timing and mitigation commitments conflict? | State how alternatives and consequences will be compared and reviewed. |

These are **candidate drafting directions for human review**, not agreed solutions or ecological advice. Do not invent numerical thresholds, feasibility conclusions, or expert endorsements. The responsible domain experts would need to supply and validate those details.

An optional reviewer-edited draft can be submitted as a new, independent exploratory run. Keep both source versions and run IDs. Different generated participants, cases, or conversations can produce different observations, so do not call that a controlled before/after improvement. Structured engine revisions cannot authorize a fresh swarm over unchanged original prose.

## Replace the presentation narrative

The existing travel-and-expense pitch deck is a draft for a different demonstration. Replace its screenshots, examples, and result claims before using it for the Maju story; do not reuse its three-defects-to-zero figure here.

| Slide | Main message |
|---|---|
| 1 | PolicyFuzz: rehearse how a proposed policy may be interpreted before implementation. |
| 2 | Hypothetical Maju framework: housing and environmental commitments create implementation questions. Clearly label every supplied quantity and date as an assumption. |
| 3 | User and task: a policy-review team seeking omissions, unclear responsibilities, and questions requiring expert evidence. |
| 4 | Workflow: source text, provisional extraction, balanced synthetic participants, exploratory discussion, human review. |
| 5 | Actual demonstration: show source-linked observations from the selected run with its capture status visible. |
| 6 | Review outcome: questions and candidate wording that humans could investigate; no invented success rate. |
| 7 | Technical distinction: orchestrated simulation and traceable review material; the core deterministic T&E tests are a separate capability. |
| 8 | Pilot and limits: measure useful reviewer-confirmed questions, false alarms, review time, and run cost. These are proposed measurements, not existing customer results. |

Closing line: **“PolicyFuzz turns an abstract framework into concrete questions a reviewer can investigate.”**

## Questions to prepare for

| Judge asks | Answer |
|---|---|
| Is this an announced government plan? | This is user-supplied hypothetical demo text. Its official attribution and quantitative/ecological claims have not been verified. |
| Are these real residents or expert opinions? | No. All participants and messages are synthetic, and the audience is not a representative sample. |
| Does the simulation predict ecological damage or public support? | No. It generates candidate interpretations and questions; real evidence and domain review are required. |
| What does “Not scored” mean? | Exploratory cases lack independent expected answers. We do not turn model-generated expectations into authoritative scores. |
| What is the useful output? | Traceable questions, assumptions, and candidate commitments for a reviewer to investigate. Useful output must be checked against the actual run and source. |
| Does revised wording prove the policy is better? | No. A separate exploratory run may inform review, but does not establish a controlled improvement or environmental outcome. |
| What if MiroFish cannot run? | Report the failure and show a clearly labelled recording only if one exists. Provisional extraction alone is not a completed multi-agent conversation. |

Before presenting, complete one real rehearsal on the presentation laptop and capture its actual screens. This asset package does not claim that rehearsal has happened.
