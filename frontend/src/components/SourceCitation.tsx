import type { SourceSpan } from '../api/types';
import { HashValue } from './HashValue';

export function SourceCitation({ citation }: { citation: SourceSpan }) {
  return (
    <figure className="citation">
      <figcaption>
        Page {citation.page}
        {citation.section ? ` · Section ${citation.section}` : ''} · characters {citation.start}–{citation.end}
      </figcaption>
      <blockquote>{citation.quote}</blockquote>
      <HashValue label="Exact quote hash" value={citation.quote_sha256} />
    </figure>
  );
}
