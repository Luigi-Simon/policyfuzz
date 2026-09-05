# PolicyFuzz interface preview

React/Vite implementation of the supplied Stitch screens. All data is explicitly illustrative. No API calls, model calls, policy execution, storage, or authoritative metrics are implemented.

Updated for the second Stitch export: owner goals, affected groups, sourced assumptions, optional simulated discussion, behavioral hypotheses vs conditional consequences, clarification decisions, and separate fixed-action/behavioral comparisons. Read [INTEGRATION.md](INTEGRATION.md) for the teammate-by-teammate connection requirements.

## Run

From this directory:

```powershell
npm ci
npm run dev
```

Open the local URL printed by Vite. Choose **Use sample policy**, review and confirm the interpretation, inspect scenarios, decide each finding, prepare a revision, and open the comparison.

```powershell
npm run typecheck
npm run test:run
npm run build
```

## Integration boundary

`src/preview.ts` contains UI-only illustrative content, not a manually defined RunView. Person 1's OpenAPI, RunView schema, and canonical completed fixture are absent in this checkout. Once frozen, generate the public client types, add runtime validation, and replace the preview state with a transport consuming RunView. This preview is not completion of Tasks 22 or 23.

Custom pasted policy text is never sent or evaluated. Edited intent is retained for design review but does not change the sample results. Mock timers represent preview playback, not real progress. Full hashes, engine versions, and effect-state counts remain unavailable rather than fabricated. The downloaded preview is explicitly labelled as non-evidence.

Visual source: supplied Stitch `screen_1_input_contract`, `screen_2_run_evidence`, `screen_3_findings_revision`, and `screen_4_comparison`. Colors and panel hierarchy are retained; unsupported Z3, solver, audit-certification, and large benchmark claims are removed. The logo is a local typographic mark; no exported third-party script is executed. Google Fonts is optional and falls back to system fonts.
