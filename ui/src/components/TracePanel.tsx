import { useState } from 'react';
import { getTrace } from '../api/client';
import type { TraceResponse } from '../api/types';
import { CalculationMatrix } from './design-system/CalculationMatrix';
import { CustodySpine } from './design-system/CustodySpine';

type Props = {
  determinationId: string;
};

function renderValue(value: unknown): string {
  if (value === null || value === undefined) {
    return '—';
  }
  return typeof value === 'object' ? JSON.stringify(value) : String(value);
}

/**
 * Collapsible, lazily loaded: a worker sees *why* a determination came out the way it did, one DMN
 * decision at a time, in the order the model actually evaluated them -- the whole point of persisting
 * a full trace in Task 5/6, before any AI exists to narrate it.
 */
export default function TracePanel({ determinationId }: Props) {
  const [trace, setTrace] = useState<TraceResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function handleToggle(event: React.SyntheticEvent<HTMLDetailsElement>) {
    if (!event.currentTarget.open || trace || loading) {
      return;
    }
    setLoading(true);
    setError(null);
    getTrace(determinationId)
      .then(setTrace)
      .catch(() => setError('Could not load the determination trace.'))
      .finally(() => setLoading(false));
  }

  return (
    <details onToggle={handleToggle} className="mt-3">
      <summary className="cursor-pointer text-sm font-medium text-primary">DMN evaluation trace</summary>
      {loading && <p className="mt-2 text-sm text-muted-foreground">Loading trace…</p>}
      {error && (
        <p role="alert" className="mt-2 text-sm text-destructive">
          {error}
        </p>
      )}
      {trace && (
        <>
          <p className="mt-2 text-sm text-muted-foreground">
            Model hash <code className="font-mono">{trace.dmnModelHash}</code>, policy parameters{' '}
            <strong className="text-foreground">{trace.policyParameterVersion}</strong>
          </p>
          <CustodySpine
            items={Object.entries(trace.decisionResults).map(([label, value]) => ({
              label,
              value: renderValue(value),
            }))}
          />
          <CalculationMatrix
            items={Object.entries(trace.decisionResults).map(([label, value]) => ({
              label,
              value: renderValue(value),
            }))}
          />
        </>
      )}
    </details>
  );
}
