# Browser rehearsal status

Status: **BLOCKED BY LOCAL BROWSER AVAILABILITY — NO ACCEPTANCE CLAIM**

Date: 2026-09-06 UTC.

The planned automated rehearsal was the real cached FastAPI API plus Vite in HTTP mode, exercised keyboard-only at 375×812 and 1440×900. No browser page was loaded and no screenshot was captured, so neither responsive layout nor keyboard acceptance is recorded as passing.

## Attempts

1. The controlled cloud Chrome session was available, but its persistent runtime could not start workspace processes and did not share the workspace localhost namespace. Process launch failed before either server could be reached.
2. The local runtime included the Playwright JavaScript package but no Chromium, Chrome, Firefox, or WebKit executable.
3. Installing Chromium into shared scratch failed on the shared-directory lock. Installing into the same command's local `/tmp` namespace reached the browser mirror, but repeated downloads returned an invalid zero-byte archive.

The empty rehearsal screenshot directory therefore contains no evidence and must not be packaged as a capture set.

## What was verified separately

`backend/.venv/bin/python -m pytest backend/tests/integration/test_http_smoke.py -q` passed its same-process real-TCP create/get/complete-cached/patch-accepted/delete flow. The frontend's 108 automated tests and production build also pass. These checks establish HTTP and component behavior but do not substitute for the two browser widths or keyboard-only visual acceptance.

## Next environment contract

- Provide a Chromium-compatible executable in the same network namespace as the shell that launches FastAPI and Vite.
- Start FastAPI with cached mode and `POLICYFUZZ_ALLOWED_ORIGIN=http://127.0.0.1:5173`.
- Start Vite with `VITE_DATA_MODE=http` and `VITE_API_BASE_URL=http://127.0.0.1:8000`, bound to `127.0.0.1`.
- Run the complete workflow twice, at 375×812 and 1440×900, using Tab, Space, Enter, arrow keys, and Escape only.
- Record actual inner width, horizontal overflow, focus visibility, public mode badges, run identity, console/page/request errors, and screenshots from the frozen build.
- Label any pre-freeze capture as rehearsal; final submission capture still waits for Gate B and the six-hour freeze.
