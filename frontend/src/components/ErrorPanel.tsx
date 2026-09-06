import { AlertTriangle } from 'lucide-react';
import type { PublicError } from '../api/types';

export function ErrorPanel({ error }: { error: PublicError | null | undefined }) {
  if (!error) return null;
  return (
    <section className="notice danger" role="alert" aria-labelledby="public-error-heading">
      <AlertTriangle aria-hidden="true" size={20} />
      <div>
        <h2 id="public-error-heading">Run error</h2>
        <p>{error.message}</p>
        <div className="badge-row">
          <span className="badge danger">{error.code}</span>
          <span className="badge neutral">{error.retryable ? 'Retry may succeed' : 'Retry not advised'}</span>
          {error.error_id ? <code>{error.error_id}</code> : null}
        </div>
      </div>
    </section>
  );
}
