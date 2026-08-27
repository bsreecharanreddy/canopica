import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { listCases } from '../api/client';
import type { CaseSummaryResponse } from '../api/types';
import { StatusPill } from '@/components/design-system/StatusPill';

export default function WorkerCasesPage() {
  const [cases, setCases] = useState<CaseSummaryResponse[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    listCases()
      .then((result) => {
        if (!cancelled) {
          setCases(result);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setError('Could not load the caseload.');
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (error) {
    return (
      <p role="alert" className="text-sm text-destructive">
        {error}
      </p>
    );
  }

  if (cases === null) {
    return <p className="text-sm text-muted-foreground">Loading cases…</p>;
  }

  return (
    <div className="overflow-x-auto">
      <table aria-label="Cases" className="w-full border-collapse text-sm">
        <thead>
          <tr>
            <th
              scope="col"
              className="border-b border-border px-3 py-2 text-left text-xs uppercase tracking-wide text-muted-foreground"
            >
              Household head
            </th>
            <th
              scope="col"
              className="border-b border-border px-3 py-2 text-left text-xs uppercase tracking-wide text-muted-foreground"
            >
              Status
            </th>
            <th
              scope="col"
              className="border-b border-border px-3 py-2 text-left text-xs uppercase tracking-wide text-muted-foreground"
            >
              Submitted
            </th>
            <th
              scope="col"
              className="border-b border-border px-3 py-2 text-left text-xs uppercase tracking-wide text-muted-foreground"
            >
              Latest determination
            </th>
          </tr>
        </thead>
        <tbody>
          {cases.map((c) => (
            <tr key={c.programRequestId} className="border-b border-border">
              <td className="px-3 py-2">
                <Link to={`/cases/${c.programRequestId}`} className="font-display text-primary hover:underline">
                  {c.householdHeadName}
                </Link>
              </td>
              <td className="px-3 py-2">
                <StatusPill tone={c.status === 'DECIDED' ? 'affirmed' : 'pending'}>{c.status}</StatusPill>
              </td>
              <td className="px-3 py-2 text-muted-foreground">{new Date(c.submittedAt).toLocaleDateString()}</td>
              <td className="px-3 py-2">
                {c.latestDetermination
                  ? `${c.latestDetermination.eligible ? 'Eligible' : 'Not eligible'} — $${c.latestDetermination.benefitAmount}`
                  : 'Not yet determined'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
