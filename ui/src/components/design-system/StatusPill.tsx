import type { ReactNode } from 'react';
import { cn } from '@/lib/utils';

export type StatusPillTone = 'affirmed' | 'exception' | 'pending' | 'neutral';

const TONE_CLASSES: Record<StatusPillTone, string> = {
  affirmed: 'bg-primary/10 text-primary',
  exception: 'bg-amber text-amber-foreground',
  pending: 'bg-muted text-muted-foreground',
  neutral: 'bg-secondary text-secondary-foreground',
};

export function StatusPill({ tone, children }: { tone: StatusPillTone; children: ReactNode }) {
  return (
    <span
      className={cn(
        'inline-block rounded-sm px-2 py-0.5 text-xs font-medium uppercase tracking-wide',
        TONE_CLASSES[tone],
      )}
    >
      {children}
    </span>
  );
}
