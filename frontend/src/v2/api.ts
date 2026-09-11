import Ajv2020 from 'ajv/dist/2020';
import addFormats from 'ajv-formats';
import schema from '../../../contracts/v2-app/public-sandbox-result.schema.json';
import type { components } from './api.generated';

export type RunRequest = components['schemas']['CreateRunRequest'];
export type PublicResult = components['schemas']['PublicSandboxResult'];
export type CreateRun = (request: RunRequest, signal: AbortSignal) => Promise<PublicResult>;

export class FixtureError extends Error {}

// The wire always includes defaults. Require all declared fields in this public
// response so generated types cannot promise fields absent from a valid payload.
export function requiredWireFields(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(requiredWireFields);
  if (value === null || typeof value !== 'object') return value;
  const result = Object.fromEntries(Object.entries(value).map(([key, item]) => [key, requiredWireFields(item)]));
  if (result.properties && typeof result.properties === 'object') {
    result.required = Object.keys(result.properties);
  }
  return result;
}

const ajv = new Ajv2020({ strict: false, allErrors: true });
addFormats(ajv);
const check = ajv.compile<PublicResult>(requiredWireFields(schema) as object);
const han = /[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\u{20000}-\u{3134f}]/u;
const unavailable = '[English translation unavailable for this record.]';

export function validateResult(value: unknown, expectedMode: PublicResult['execution_mode'] = 'fixture'): PublicResult {
  const invalid = () => { throw new FixtureError('The fixture response could not be verified.'); };
  if (!check(value)) return invalid();
  const personaIds = value.personas.map(persona => persona.persona_id);
  const messageIds = value.messages.map(message => message.message_id);
  const sourceIds = value.sources.map(source => source.source_id);
  const sourceRecordIds = value.sources.map(source => source.record_id);
  const hasDuplicates = (ids: string[]) => ids.length !== new Set(ids).size;
  const personaIdSet = new Set(personaIds);
  const messageIdSet = new Set(messageIds);
  const sourceIdSet = new Set(sourceIds);
  const sourceById = new Map(value.sources.map(source => [source.source_id, source]));
  const sourceByRecord = new Map(value.sources.map(source => [source.record_id, source]));
  const seenMessages = new Set<string>();
  const invalidReferences = value.messages.some((message, index) => {
    const ownSource = sourceByRecord.get(message.message_id);
    const invalidMessage = message.sequence !== index + 1 ||
      !personaIdSet.has(message.persona_id) ||
      hasDuplicates(message.source_refs) ||
      message.source_refs.some(sourceId => !sourceIdSet.has(sourceId)) ||
      hasDuplicates(message.reply_to_message_ids) ||
      message.reply_to_message_ids.some(messageId => !seenMessages.has(messageId)) ||
      (value.status === 'completed' && (!ownSource || !message.source_refs.includes(ownSource.source_id))) ||
      (message.translation_status === 'unavailable' && message.source_refs.some(
        sourceId => sourceById.get(sourceId)?.excerpt !== unavailable,
      ));
    seenMessages.add(message.message_id);
    return invalidMessage;
  });
  const display = [value.policy_title, ...value.limitations, ...value.errors,
    ...value.personas.flatMap(persona => [persona.display_name, persona.description]),
    ...value.messages.map(message => message.content),
    ...value.sources.flatMap(source => [source.title, source.excerpt])];
  if (value.execution_mode !== expectedMode || display.some(text => han.test(text)) ||
      hasDuplicates(personaIds) || hasDuplicates(messageIds) || hasDuplicates(sourceIds) ||
      hasDuplicates(sourceRecordIds) || value.sources.some(source => !messageIdSet.has(source.record_id)) ||
      invalidReferences ||
      value.configured_stakeholder_count !== value.personas.length ||
      value.observed_stakeholder_count !== new Set(value.messages.map(message => message.persona_id)).size ||
      value.observed_stakeholder_count > value.configured_stakeholder_count ||
      value.configured_stakeholder_count > value.requested_stakeholder_count ||
      (value.status === 'completed' && (value.errors.length > 0 || value.messages.length === 0 ||
        value.observed_stakeholder_count !== value.requested_stakeholder_count)) ||
      (value.status === 'failed' && value.errors.length === 0) ||
      ((value.status === 'partial' || value.status === 'cancelled') &&
        value.limitations.length === 0 && value.errors.length === 0) ||
      value.messages.some(message => message.translation_status === 'unavailable' &&
        (value.status !== 'partial' || message.content !== unavailable))) return invalid();
  return value;
}

export const createFixtureRun: CreateRun = async (request, signal) => {
  const response = await fetch('/api/v2/runs', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request), signal,
  });
  if (!response.ok) {
    const message = response.status === 422
      ? 'Check the four policy fields. Use an English title and a stakeholder count from 1 to 100.'
      : response.status === 504
        ? 'The Sandbox fixture timed out. Please retry.'
        : 'The Sandbox fixture could not complete. Please retry.';
    throw new FixtureError(message);
  }
  let value: unknown;
  try { value = await response.json(); }
  catch { throw new FixtureError('The fixture response could not be verified.'); }
  return validateResult(value);
};
