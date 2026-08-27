import type { ReactNode } from 'react';
import { cn } from '@/lib/utils';

export type StatusPillTone = 'affirmed' | 'exception' | 'pending' | 'neutral';

const TONE_CLASSES: Record<StatusPillTone, string> = {
  affirmed: 'border-emerald-200 bg-emerald-50 text-emerald-700',
  exception: 'border-amber-200 bg-amber text-amber-foreground',
  pending: 'border-border bg-muted text-muted-foreground',
  neutral: 'border-border bg-secondary text-secondary-foreground',
};

export function StatusPill({ tone, children }: { tone: StatusPillTone; children: ReactNode }) {
  return (
    <span
      className={cn(
        'inline-block rounded-md border px-2 py-0.5 text-xs font-medium uppercase tracking-wide',
        TONE_CLASSES[tone],
      )}
    >
      {children}
    </span>
  );
}
