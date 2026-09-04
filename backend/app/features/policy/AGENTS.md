# Policy feature ownership

Read the matching [Person 2 charter](../../../../team/person-2-policy/AGENTS.md) before working in this directory.

Person 2 is the sole writer for this directory and its matching tests. Consume models from `app.domain.models`, protocols from `app.domain.protocols`, and the provider through the public LLM boundary. Preserve exact citations, treat policy text as untrusted data, permit at most one output-repair call, and never manufacture authoritative verdicts, severity, metrics, or citations.
