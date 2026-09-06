import { ShieldCheck, Trash2 } from 'lucide-react';
import type { RunView } from '../api/types';
import { ModeBadge } from './ModeBadge';

export function AppHeader({
  run,
  onReset,
  onDelete,
  deleteArmed = false,
  busy = false,
}: {
  run?: RunView | null;
  onReset?: () => void;
  onDelete?: () => void;
  deleteArmed?: boolean;
  busy?: boolean;
}) {
  return (
    <header>
      <a className="skip" href="#main-content">Skip to main content</a>
      <div className="topbar">
        <div className="brand">
          <ShieldCheck aria-hidden="true" />
          <h1>PolicyFuzz</h1>
          <span className="badge neutral">Decision-policy QA</span>
          {run ? <ModeBadge mode={run.mode} /> : null}
        </div>
        {run ? <code className="run-id">Run {run.run_id}</code> : null}
        {onReset ? (
          <button type="button" className="secondary" disabled={busy} onClick={onReset}>New run</button>
        ) : null}
        {run && onDelete ? (
          <button type="button" className="danger" disabled={busy} onClick={onDelete}>
            <Trash2 aria-hidden="true" size={17} /> {deleteArmed ? 'Confirm delete' : 'Delete run'}
          </button>
        ) : null}
      </div>
    </header>
  );
}
