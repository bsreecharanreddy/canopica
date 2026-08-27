import type { ReactNode } from 'react';

export function DecisionBar({
  amount,
  policyVersion,
  note,
}: {
  amount: string;
  policyVersion: string;
  note: ReactNode;
}) {
  return (
    <div className="flex items-center justify-between rounded-lg border border-border bg-muted/60 px-4 py-4">
      <span className="font-display text-3xl font-bold tabular-nums text-foreground">${amount}/month</span>
      <div className="flex flex-col items-end gap-0.5 text-xs text-muted-foreground">
        <span>
          Policy <strong className="font-semibold text-foreground">{policyVersion}</strong>
        </span>
        <span>{note}</span>
      </div>
    </div>
  );
}
