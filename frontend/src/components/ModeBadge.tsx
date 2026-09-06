import type { RunView } from '../api/types';
import { OutcomeBadge } from './OutcomeBadge';

export function ModeBadge({ mode, fixture = false }: { mode: RunView['mode']; fixture?: boolean }) {
  const label = fixture && mode === 'cached' ? 'Cached synthetic fixture — authored display data' : `${mode === 'cached' ? 'Cached' : 'Live'} run`;
  return <OutcomeBadge label={label} tone={mode === 'cached' ? 'warning' : 'info'} />;
}
