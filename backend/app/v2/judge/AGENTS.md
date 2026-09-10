# Friend's Judge implementation scope

You own this folder and backend/tests/v2/judge/**. Read team/v2-judge/HANDOFF.md.
Implement app.v2.judge.service.JudgeAgentService with async run(JudgeRequest)
returning JudgeResult. Import shared types from app.v2.judge_contracts and protocol
from app.v2.judge_protocols. Simon owns all shared models and integration files.

Do not change deterministic Metric verdicts, counts, scores or assertions. Return
English advice with resolving citations; report incomplete evidence explicitly.
Use fake model clients in tests. Live credentials stay in environment variables.
Do not edit the Sandbox implementation from the Judge feature branch; work on its
separate branch/worktree. Exactly four top-level agent roles remain.
