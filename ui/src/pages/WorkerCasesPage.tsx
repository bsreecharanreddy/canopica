import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { listCases } from '../api/client';
import type { CaseSummaryResponse } from '../api/types';
import { StatusPill } from '@/components/design-system/StatusPill';

export default function WorkerCasesPage() {
  const { t } = useTranslation('workerCases');
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
          setError(t('loadError'));
        }
      });
    return () => {
      cancelled = true;
    };
  }, [t]);

  if (error) {
    return (
      <p role="alert" className="text-sm text-destructive">
        {error}
      </p>
    );
  }

  if (cases === null) {
    return <p className="text-sm text-muted-foreground">{t('loading')}</p>;
  }

  return (
    <div className="overflow-x-auto">
      <table aria-label={t('tableLabel')} className="w-full border-collapse text-sm">
        <thead>
          <tr>
            <th
              scope="col"
              className="border-b border-border px-3 py-2 text-left text-xs uppercase tracking-wide text-muted-foreground"
            >
              {t('columns.householdHead')}
            </th>
            <th
              scope="col"
              className="border-b border-border px-3 py-2 text-left text-xs uppercase tracking-wide text-muted-foreground"
            >
              {t('columns.status')}
            </th>
            <th
              scope="col"
              className="border-b border-border px-3 py-2 text-left text-xs uppercase tracking-wide text-muted-foreground"
            >
              {t('columns.submitted')}
            </th>
            <th
              scope="col"
              className="border-b border-border px-3 py-2 text-left text-xs uppercase tracking-wide text-muted-foreground"
            >
              {t('columns.latestDetermination')}
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
                  ? t('determinationValue', {
                      status: t(c.latestDetermination.eligible ? 'eligible' : 'notEligible'),
                      amount: c.latestDetermination.benefitAmount,
                    })
                  : t('notYetDetermined')}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
