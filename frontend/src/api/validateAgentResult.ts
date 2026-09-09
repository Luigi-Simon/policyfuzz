import { safePublicError, type AgentSimulationResult } from './transport';

type Check = (value: unknown) => boolean;
const string: Check = (value) => typeof value === 'string';
const boolean: Check = (value) => typeof value === 'boolean';
const number: Check = (value) => typeof value === 'number' && Number.isFinite(value);
const nullable = (check: Check): Check => (value) => value === null || check(value);
const record = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value);
const arrayOf = (check: Check): Check => (value) => Array.isArray(value) && value.every(check);
const objectWith = (fields: Record<string, Check>): Check => (value) =>
  record(value) && Object.entries(fields).every(([key, check]) => value[key] === undefined || check(value[key]));

// Validate every declared optional field that the UI may render. Unknown extension
// fields remain opaque; this is a shape check, not proof of simulation correctness.
const turn = objectWith({ agent: string, user_name: string, text: string, content: string });
const resultShape = objectWith({
  compatibility_mode: string,
  policy_title: string,
  policy_source_text: string,
  message: string,
  error: (value) => value === null || string(value),
  document: nullable(objectWith({ filename: string, text: string })),
  ir: nullable(objectWith({
    title: string,
    source: objectWith({ text: string }),
    rules: arrayOf(objectWith({ id: string, statement: string })),
  })),
  effectiveness: nullable(objectWith({
    score: number,
    swarm_used: boolean,
    interaction_verified: boolean,
    justification: string,
    metrics: record,
    highlights: arrayOf(objectWith({ agent: string, platform: string, kind: string, text: string, why_significant: string })),
  })),
  evaluation: nullable(objectWith({ findings: arrayOf(objectWith({ scenario_id: string, verdict: string, summary: string, rule_ids: arrayOf(string) })) })),
  extra: objectWith({
    swarm: objectWith({
      interaction_verified: boolean,
      duplicate_messages_rejected: number,
      error: string,
      posts: arrayOf(turn),
      comments: arrayOf(turn),
      actions: arrayOf(objectWith({ agent: string, agent_name: string, text: string, content: string })),
    }),
  }),
});

export function validateAgentSimulationResult(value: unknown): AgentSimulationResult {
  if (
    !record(value) ||
    typeof value.run_id !== 'string' || !value.run_id.trim() ||
    typeof value.status !== 'string' || !value.status.trim() ||
    !resultShape(value)
  ) {
    // Never echo provider payloads or nested validation details into the UI.
    throw safePublicError('INTERNAL_ERROR', 'Agent simulation returned an invalid response.');
  }
  return value as AgentSimulationResult;
}

export const validateAgentResult = validateAgentSimulationResult;
