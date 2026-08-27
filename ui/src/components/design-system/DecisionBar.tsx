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
    <div className="flex items-baseline justify-between border-y border-border bg-card px-4 py-3">
      <span className="font-display text-2xl tabular-nums text-foreground">${amount}/month</span>
      <span className="text-xs text-muted-foreground">
        Policy <strong className="font-medium text-foreground">{policyVersion}</strong>
      </span>
      <span className="text-xs text-muted-foreground">{note}</span>
    </div>
  );
}
