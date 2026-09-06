import type { ReactNode } from 'react';

export type OutcomeTone = 'neutral' | 'success' | 'warning' | 'danger' | 'info';

export function OutcomeBadge({ label, tone = 'neutral' }: { label: ReactNode; tone?: OutcomeTone }) {
  return (
    <span className={`badge ${tone}`} data-tone={tone}>
      {label}
    </span>
  );
}
