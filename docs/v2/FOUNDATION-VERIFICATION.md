# Foundation verification record

Scope: the shared v2 Sandbox boundary and two-person development handoffs.
This is not evidence of a live MiroFish run or a completed v2 application.

## Source and preservation

Reviewed remote base: `899959e626b050af6e0ab96d3ea01f3433f210fd`.
The existing [baseline verification run](https://github.com/Luigi-Simon/policyfuzz/actions/runs/34462312097)
completed successfully. Foundation changes are additive under v2 namespaces,
with root README/ownership guidance updated. V1 schemas, runtime and archived
evidence are preserved.

## Executed checks

- Python 3.12.14 / Pydantic 2.13.5: `python scripts/check_v2_foundation.py`
  completed successfully: **21 tests**, deterministic schema/fixture comparison,
  and a three-participant synthetic Sandbox smoke run. No live provider calls.
- The initial missing-implementation run produced 16 expected failing tests.
  Review regression cases reproduced their failures before fixes.
- Independent review confirmed request/result binding, source/speaker/reply
  consistency, count and completion checks, translation-unavailable placeholders,
  public exclusion of original records, and the Windows path comparison fix.
- Completed and partial fixture adapters were also checked at 1 and 100
  participants. Authored fixture dialogue does not analyse the supplied policy.
- The new workflow YAML parses and the smoke script compiles. GitHub Actions
  performs authoritative Ruff formatting/lint checks and the existing repository
  verification after publication; consult the foundation PR's checks for status.

The local review checkout contained the files needed for this foundation. The full
v1 application was not executed locally; its baseline CI result must not be
misrepresented as a local full-app test of v2.

## Publication record

The foundation PR records the final commit used for integration, core and Sandbox
branches. Their initial tips must match; remote main must remain at the reviewed
base. New feature work will naturally make those branch tips diverge afterward.

## Still to implement

The friend's live MiroFish adapter, parser and translator; Simon's three core
agents, stateful policy runner, v2 UI/API, persistence and revision flow; and their
joint real-provider integration demonstration. A Han-script guard is not a full
English detector or a guarantee of faithful translation.
