import { describe, expect, it } from 'vitest';
import { cachedRunView } from '../fixtures/cachedRunView';
import { PublicResponseValidationError, validateRunView } from '../api/validateRunView';
import {
  makeAwaitingContractView,
  makeAwaitingFindingsView,
  makeAwaitingRevisionView,
  makeCompletedView,
  makeRunView,
} from './runViewFactory';

describe('public RunView fixtures', () => {
  it('loads the canonical completed fixture unchanged and schema-valid', () => {
    expect(validateRunView(cachedRunView)).toBe(cachedRunView);
    expect(cachedRunView).toMatchObject({
      run_id: 'synthetic-completed-run',
      mode: 'cached',
      stage: 'complete',
      terminal_status: 'complete',
      comparison_metrics: { patch_accepted: false },
    });
  });

  it.each([
    ['contract', makeAwaitingContractView(), 'awaiting_contract'],
    ['findings', makeAwaitingFindingsView(), 'awaiting_finding_review'],
    ['revision', makeAwaitingRevisionView(), 'awaiting_revision_confirmation'],
    ['completed', makeCompletedView(), 'complete'],
    ['active', makeRunView('analyzing'), 'analyzing'],
    ['alternate terminal', makeRunView('completed_no_revision'), 'completed_no_revision'],
  ])('builds an isolated, schema-valid %s snapshot', (_label, snapshot, stage) => {
    expect(validateRunView(snapshot)).toBe(snapshot);
    expect(snapshot.stage).toBe(stage);
    const originalId = snapshot.run_id;
    snapshot.run_id = 'locally-mutated';
    expect(makeRunView(stage as Parameters<typeof makeRunView>[0]).run_id).toBe(originalId);
  });

  it('keeps authored baseline evidence in the findings and revision snapshots', () => {
    for (const snapshot of [makeAwaitingFindingsView(), makeAwaitingRevisionView()]) {
      expect(snapshot.baseline_metrics?.scenario_count).toBe(6);
      expect(snapshot.coverage?.scenario_count).toBe(6);
      expect(snapshot.traces.length).toBeGreaterThan(0);
      expect(snapshot.traces.every((trace) => trace.phase === 'baseline')).toBe(true);
      expect(snapshot.comparison_metrics).toBeNull();
    }
  });

  it('rejects schema-valid wire values missing generated default fields', () => {
    expect(() => validateRunView({ run_id: 'run-incomplete', stage: 'queued', mode: 'live' })).toThrow(
      PublicResponseValidationError,
    );
    const missingNestedDefault = structuredClone(cachedRunView);
    delete (missingNestedDefault.events[0] as Partial<(typeof missingNestedDefault.events)[number]>).schema_version;
    expect(() => validateRunView(missingNestedDefault)).toThrow(PublicResponseValidationError);
  });

  it('rejects false patch success and duplicated count disagreement', () => {
    const falseSuccess = structuredClone(cachedRunView);
    if (!falseSuccess.comparison_metrics) throw new Error('expected canonical comparison');
    falseSuccess.comparison_metrics.patch_accepted = true;
    expect(() => validateRunView(falseSuccess)).toThrow(PublicResponseValidationError);

    const badConjunction = structuredClone(cachedRunView);
    if (!badConjunction.comparison_metrics) throw new Error('expected canonical comparison');
    badConjunction.comparison_metrics.acceptance.patch_accepted = true;
    expect(() => validateRunView(badConjunction)).toThrow(PublicResponseValidationError);

    const badCount = structuredClone(cachedRunView);
    if (!badCount.comparison_metrics) throw new Error('expected canonical comparison');
    badCount.comparison_metrics.protected_regressions += 1;
    expect(() => validateRunView(badCount)).toThrow(PublicResponseValidationError);
  });

  it('requires revision operations to show the matching baseline rule and revision', () => {
    const revision = makeAwaitingRevisionView();
    const pending = revision.pending_confirmation;
    if (pending?.kind !== 'revision') throw new Error('expected revision');
    const summary = pending.operations[0];
    expect(summary.operation.kind).toBe('add_override');
    expect(summary.before).not.toBeNull();
    expect(summary.before?.rule_id).toBe(summary.operation.rule_id);
    expect(revision.findings.find((item) => item.finding_id === 'synthetic-finding-cap')?.review_status).toBe('accepted');
    expect(revision.findings.find((item) => item.finding_id === 'synthetic-finding-gap')?.review_status).toBe('rejected');
    expect(validateRunView(revision)).toBe(revision);

    const missingBefore = structuredClone(revision);
    if (missingBefore.pending_confirmation?.kind !== 'revision') throw new Error('expected revision');
    missingBefore.pending_confirmation.operations[0].before = null;
    expect(() => validateRunView(missingBefore)).toThrow(PublicResponseValidationError);

    const wrongBefore = structuredClone(revision);
    if (wrongBefore.pending_confirmation?.kind !== 'revision') throw new Error('expected revision');
    if (!wrongBefore.pending_confirmation.operations[0].before) throw new Error('expected before');
    wrongBefore.pending_confirmation.operations[0].before.rule_id = 'different-rule';
    expect(() => validateRunView(wrongBefore)).toThrow(PublicResponseValidationError);

    const selfOverride = structuredClone(revision);
    if (selfOverride.pending_confirmation?.kind !== 'revision') throw new Error('expected revision');
    const operation = selfOverride.pending_confirmation.operations[0].operation;
    if (operation.kind !== 'add_override') throw new Error('expected override');
    operation.target_rule_id = operation.rule_id;
    expect(() => validateRunView(selfOverride)).toThrow(PublicResponseValidationError);

    const wrongRevision = structuredClone(revision);
    if (wrongRevision.pending_confirmation?.kind !== 'revision') throw new Error('expected revision');
    const replacement = wrongRevision.pending_confirmation.operations[0];
    if (!replacement.before) throw new Error('expected before');
    replacement.operation = {
      schema_version: '1.0',
      kind: 'replace_rule',
      rule_id: replacement.before.rule_id,
      expected_revision: replacement.before.revision + 1,
      rule: {
        schema_version: '1.0',
        description: replacement.before.description,
        when: replacement.before.when,
        effects: replacement.before.effects,
        overrides: replacement.before.overrides,
      },
      finding_ids: ['synthetic-finding-cap'],
    };
    expect(() => validateRunView(wrongRevision)).toThrow(PublicResponseValidationError);
  });

  it('exposes a deliberate below-minimum contract fixture only for negative UI tests', () => {
    expect(() => validateRunView(makeAwaitingContractView(2))).toThrow(PublicResponseValidationError);
  });
});
