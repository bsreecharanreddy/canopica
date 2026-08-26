import { useState } from 'react';
import { getTrace } from '../api/client';
import type { TraceResponse } from '../api/types';

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
    <details onToggle={handleToggle}>
      <summary>DMN evaluation trace</summary>
      {loading && <p>Loading trace…</p>}
      {error && (
        <p role="alert">{error}</p>
      )}
      {trace && (
        <>
          <p>
            Model hash <code>{trace.dmnModelHash}</code>, policy parameters{' '}
            <strong>{trace.policyParameterVersion}</strong>
          </p>
          <ol aria-label="DMN decisions in evaluation order">
            {Object.entries(trace.decisionResults).map(([name, value]) => (
              <li key={name}>
                <strong>{name}:</strong> {renderValue(value)}
              </li>
            ))}
          </ol>
        </>
      )}
    </details>
  );
}
