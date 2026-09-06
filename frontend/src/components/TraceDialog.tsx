import { useEffect, useRef, type RefObject } from 'react';
import type { VisibleTraceSummary } from '../api/types';
import { HashValue } from './HashValue';
import { OutcomeBadge } from './OutcomeBadge';
import { SourceCitation } from './SourceCitation';

export function TraceDialog({
  trace,
  open,
  onClose,
  returnFocusRef,
}: {
  trace: VisibleTraceSummary;
  open: boolean;
  onClose: () => void;
  returnFocusRef?: RefObject<HTMLElement | null>;
}) {
  const dialogRef = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog || !open) return;
    if (!dialog.open) dialog.showModal();
    const closeButton = dialog.querySelector<HTMLButtonElement>('[data-close-trace]');
    closeButton?.focus();
    return () => {
      if (dialog.open) dialog.close();
    };
  }, [open]);

  if (!open) return null;

  const close = () => {
    onClose();
    window.setTimeout(() => returnFocusRef?.current?.focus(), 0);
  };

  const keepFocusInside = (event: React.KeyboardEvent<HTMLDialogElement>) => {
    if (event.key !== 'Tab') return;
    const controls = Array.from(dialogRef.current?.querySelectorAll<HTMLElement>('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])') ?? []);
    if (controls.length === 0) return;
    const first = controls[0];
    const last = controls[controls.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  };

  return (
    <dialog
      ref={dialogRef}
      aria-labelledby="trace-dialog-title"
      onCancel={(event) => { event.preventDefault(); close(); }}
      onKeyDown={keepFocusInside}
    >
      <div className="drawer-header">
        <div>
          <span className="eyebrow">{trace.phase.replaceAll('_', ' ')}</span>
          <h2 id="trace-dialog-title">Trace {trace.scenario_id}</h2>
        </div>
        <button type="button" className="secondary" data-close-trace onClick={close}>Close trace</button>
      </div>
      <div className="drawer-content">
        <section aria-labelledby="trace-rules">
          <h3 id="trace-rules">Fired rules</h3>
          <div className="badge-row">{trace.fired_rule_ids.map((id) => <OutcomeBadge key={id} label={id} tone="info" />)}</div>
        </section>
        <section aria-labelledby="trace-predicates">
          <h3 id="trace-predicates">Predicate results</h3>
          <ul className="trace-list">
            {trace.predicate_results.map((result) => (
              <li key={`${result.rule_id}-${result.predicate_index}`}>
                <code>{result.rule_id}</code> · predicate {result.predicate_index + 1} · {result.matched ? 'matched' : 'did not match'}
              </li>
            ))}
          </ul>
        </section>
        <section aria-labelledby="trace-effects">
          <h3 id="trace-effects">Resolved effects</h3>
          <div className="table-scroll" role="region" aria-label="Resolved effect dimensions" tabIndex={0}>
            <table>
              <thead><tr><th>Dimension</th><th>Status</th><th>Value</th><th>Applicable rules</th><th>Overridden rules</th></tr></thead>
              <tbody>{trace.resolved_effects.map((effect) => (
                <tr key={effect.dimension}>
                  <td>{effect.dimension.replaceAll('_', ' ')}</td><td>{effect.status}</td><td>{effect.value ?? 'N/A'}</td>
                  <td>{(effect.applicable_rule_ids ?? []).join(', ') || 'None'}</td><td>{(effect.overridden_rule_ids ?? []).join(', ') || 'None'}</td>
                </tr>
              ))}</tbody>
            </table>
          </div>
        </section>
        <section aria-labelledby="trace-compliance">
          <h3 id="trace-compliance">Compliance values</h3>
          <div className="badge-row">{trace.compliance_values.map((item) => <OutcomeBadge key={item.dimension} label={`${item.dimension.replaceAll('_', ' ')} · ${item.status}`} tone={item.status === 'COMPLIANT' ? 'success' : item.status === 'NONCOMPLIANT' ? 'danger' : 'warning'} />)}</div>
        </section>
        <section aria-labelledby="trace-citations">
          <h3 id="trace-citations">Source citations</h3>
          {trace.source_citations.map((citation) => <SourceCitation key={citation.quote_sha256} citation={citation} />)}
        </section>
        <div className="notice neutral">
          <p>Scenario facts are unavailable in this public view.</p>
          <p>Individual assertion details are unavailable in this public view.</p>
        </div>
        <HashValue label="Full trace hash" value={trace.trace_sha256} />
      </div>
    </dialog>
  );
}
