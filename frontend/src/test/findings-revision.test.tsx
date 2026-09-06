import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { FindingsRevisionView } from '../views/FindingsRevisionView';
import { makeAwaitingFindingsView, makeAwaitingRevisionView } from './runViewFactory';

describe('FindingsRevisionView', () => {
  it('submits decisions for each and only pending finding ID', async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();
    const run = makeAwaitingFindingsView();
    const pending = run.pending_confirmation;
    if (!pending || pending.kind !== 'findings') throw new Error('Expected findings fixture');

    render(<FindingsRevisionView run={run} busy={false} onSelect={onSelect} onConfirm={vi.fn()} />);
    for (const findingId of pending.finding_ids) {
      const row = screen.getByRole('group', { name: `Review ${findingId}` });
      await user.click(within(row).getByLabelText('Reject'));
    }
    await user.click(screen.getByRole('button', { name: 'Submit finding decisions' }));

    expect(onSelect).toHaveBeenCalledWith({
      schema_version: '1.0',
      decisions: pending.finding_ids.map((finding_id) => ({ schema_version: '1.0', finding_id, decision: 'reject', reviewer_severity: null })),
    });
  });

  it('keeps findings outside the pending confirmation read-only', () => {
    const run = makeAwaitingFindingsView();
    const pending = run.pending_confirmation;
    if (!pending || pending.kind !== 'findings') throw new Error('Expected findings fixture');
    const readOnly = { ...(run.findings ?? [])[0], finding_id: 'synthetic-candidate', review_status: 'pending' as const };
    run.findings = [...(run.findings ?? []), readOnly];

    render(<FindingsRevisionView run={run} busy={false} onSelect={vi.fn()} onConfirm={vi.fn()} />);

    expect(screen.getByRole('group', { name: `Review ${readOnly.finding_id}` })).toHaveAttribute('aria-disabled', 'true');
  });

  it('requires reviewer severity when accepting an unscored structural gap or conflict', async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();
    const base = makeAwaitingFindingsView();
    const pending = base.pending_confirmation;
    if (!pending || pending.kind !== 'findings') throw new Error('Expected findings fixture');
    const findingId = pending.finding_ids[0];
    const run = {
      ...base,
      pending_confirmation: { ...pending, finding_ids: [findingId] },
      findings: (base.findings ?? []).map((finding) =>
        finding.finding_id === findingId
          ? { ...finding, finding_type: 'structural_gap' as const, severity: null }
          : finding,
      ),
    };

    render(<FindingsRevisionView run={run} busy={false} onSelect={onSelect} onConfirm={vi.fn()} />);
    await user.click(within(screen.getByRole('group', { name: `Review ${findingId}` })).getByLabelText('Accept'));
    await user.click(screen.getByRole('button', { name: 'Submit finding decisions' }));

    expect(screen.getByRole('alert')).toHaveTextContent(`Choose reviewer severity for ${findingId}.`);
    expect(onSelect).not.toHaveBeenCalled();
  });

  it('clears reviewer severity from a rejected finding decision', async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();
    const run = makeAwaitingFindingsView();
    const pending = run.pending_confirmation;
    if (!pending || pending.kind !== 'findings') throw new Error('Expected findings fixture');
    const findingId = pending.finding_ids[0];
    run.pending_confirmation = { ...pending, finding_ids: [findingId] };

    render(<FindingsRevisionView run={run} busy={false} onSelect={onSelect} onConfirm={vi.fn()} />);
    const review = screen.getByRole('group', { name: `Review ${findingId}` });
    await user.click(within(review).getByLabelText('Accept'));
    await user.selectOptions(within(review).getByLabelText(`Reviewer severity for ${findingId}`), 'critical');
    await user.click(within(review).getByLabelText('Reject'));
    await user.click(screen.getByRole('button', { name: 'Submit finding decisions' }));

    expect(onSelect).toHaveBeenCalledWith({
      schema_version: '1.0',
      decisions: [{ schema_version: '1.0', finding_id: findingId, decision: 'reject', reviewer_severity: null }],
    });
  });

  it('shows typed operations and submits only proposal identity and decision', async () => {
    const user = userEvent.setup();
    const onConfirm = vi.fn();
    const run = makeAwaitingRevisionView();
    const pending = run.pending_confirmation;
    if (!pending || pending.kind !== 'revision') throw new Error('Expected revision fixture');

    render(<FindingsRevisionView run={run} busy={false} onSelect={vi.fn()} onConfirm={onConfirm} />);

    expect(screen.getByText('Unverified wording suggestion — not what was tested.')).toBeVisible();
    for (const summary of pending.operations) {
      expect(screen.getByText(summary.operation.kind.replaceAll('_', ' '))).toBeVisible();
    }
    await user.click(screen.getByRole('button', { name: 'Confirm revision' }));
    expect(onConfirm).toHaveBeenCalledWith({ schema_version: '1.0', proposal_id: pending.proposal_id, decision: 'confirm' });
  });

  it('shows complete add, replace, and merged add-override semantics', () => {
    const run = makeAwaitingRevisionView();
    const pending = run.pending_confirmation;
    if (!pending || pending.kind !== 'revision') throw new Error('Expected revision fixture');
    const before = {
      schema_version: '1.0' as const,
      rule_id: 'synthetic-rule-base', revision: 3, description: 'Existing baseline rule.', when: [],
      effects: [{ schema_version: '1.0' as const, dimension: 'approval_requirement' as const, value: 'manager' as const }],
      overrides: [{ schema_version: '1.0' as const, dimension: 'eligibility' as const, target_rule_id: 'synthetic-rule-legacy' }],
      citations: [], confidence_percent: 88,
    };
    pending.operations = [
      {
        schema_version: '1.0',
        before: null,
        operation: {
          schema_version: '1.0',
          kind: 'add_rule', rule_id: 'synthetic-rule-new', finding_ids: ['synthetic-finding-gap'],
          rule: { schema_version: '1.0', description: 'New unconditional rule.', when: [], effects: [{ schema_version: '1.0', dimension: 'eligibility', value: 'deny' }], overrides: [] },
        },
      },
      {
        schema_version: '1.0',
        before,
        operation: {
          schema_version: '1.0',
          kind: 'replace_rule', rule_id: before.rule_id, expected_revision: 3, finding_ids: ['synthetic-finding-gap'],
          rule: { schema_version: '1.0', description: 'Replacement rule.', when: [], effects: [{ schema_version: '1.0', dimension: 'approval_requirement', value: 'director' }], overrides: [{ schema_version: '1.0', dimension: 'approval_requirement', target_rule_id: 'synthetic-rule-general' }] },
        },
      },
      {
        schema_version: '1.0',
        before,
        operation: { schema_version: '1.0', kind: 'add_override', rule_id: before.rule_id, dimension: 'approval_requirement', target_rule_id: 'synthetic-rule-exception', finding_ids: ['synthetic-finding-gap'] },
      },
    ];

    render(<FindingsRevisionView run={run} busy={false} onSelect={vi.fn()} onConfirm={vi.fn()} />);

    expect(screen.getAllByText('Always')).toHaveLength(5);
    expect(screen.getByText('Expected baseline revision: 3')).toBeVisible();
    const replacement = screen.getByRole('group', { name: 'replace rule synthetic-rule-base' });
    expect(within(replacement).getByText(/approval requirement → synthetic-rule-general/i)).toBeVisible();
    const override = screen.getByRole('group', { name: 'add override synthetic-rule-base' });
    expect(within(override).getAllByText(/eligibility → synthetic-rule-legacy/i)).toHaveLength(2);
    expect(within(override).getByText(/approval requirement → synthetic-rule-exception/i)).toBeVisible();
    expect(within(override).getAllByText('Extraction confidence: 88% · display only')).toHaveLength(2);
  });
});
