import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { listCases } from '../api/client';
import type { CaseSummaryResponse } from '../api/types';

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
    return <p role="alert">{error}</p>;
  }

  if (cases === null) {
    return <p>Loading cases…</p>;
  }

  return (
    <table aria-label="Cases">
      <thead>
        <tr>
          <th scope="col">Household head</th>
          <th scope="col">Status</th>
          <th scope="col">Submitted</th>
          <th scope="col">Latest determination</th>
        </tr>
      </thead>
      <tbody>
        {cases.map((c) => (
          <tr key={c.programRequestId}>
            <td>
              <Link to={`/cases/${c.programRequestId}`}>{c.householdHeadName}</Link>
            </td>
            <td>{c.status}</td>
            <td>{new Date(c.submittedAt).toLocaleDateString()}</td>
            <td>
              {c.latestDetermination
                ? `${c.latestDetermination.eligible ? 'Eligible' : 'Not eligible'} — $${c.latestDetermination.benefitAmount}`
                : 'Not yet determined'}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
