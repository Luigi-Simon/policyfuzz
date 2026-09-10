# Frontend ownership

For the user-approved v2 split, Simon owns `src/v2/**`, v2 tests and generated
type checks, plus the minimal v2 entry/proxy integration. Preserve the existing
v1 UI and generated contracts. The allocation below continues to apply to v1.

Person 5 is the sole dependency and UI writer under this directory. The frontend consumes only the generated API types and public `RunView`; it must not import backend internals. Preserve synthetic-data, live/cached, unverified-wording, and public-error labels in every applicable view.
