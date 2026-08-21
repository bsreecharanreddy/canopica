import { useEffect, useState, type FormEvent } from 'react';
import { useParams } from 'react-router-dom';
import { getCase, runDetermination } from '../api/client';
import type { CaseDetailResponse } from '../api/types';
import DeterminationPanel from '../components/DeterminationPanel';

function todayIso(): string {
  return new Date().toISOString().slice(0, 10);
}

function firstOfCurrentMonthIso(): string {
  const now = new Date();
  return new Date(now.getFullYear(), now.getMonth(), 1).toISOString().slice(0, 10);
}

export default function CaseDetailPage() {
  const { programRequestId } = useParams<{ programRequestId: string }>();
  const [caseDetail, setCaseDetail] = useState<CaseDetailResponse | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [asOfDate, setAsOfDate] = useState(todayIso());
  const [benefitMonth, setBenefitMonth] = useState(firstOfCurrentMonthIso());
  const [running, setRunning] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);

  useEffect(() => {
    if (!programRequestId) {
      return;
    }
    getCase(programRequestId)
      .then(setCaseDetail)
      .catch(() => setLoadError('Could not load this case.'));
  }, [programRequestId]);

  async function handleRunDetermination(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!programRequestId) {
      return;
    }
    setRunning(true);
    setRunError(null);
    try {
      const determination = await runDetermination(programRequestId, { asOfDate, benefitMonth });
      setCaseDetail((current) =>
        current ? { ...current, determinations: [determination, ...current.determinations] } : current,
      );
    } catch {
      setRunError('Could not run a determination for this case.');
    } finally {
      setRunning(false);
    }
  }

  if (loadError) {
    return <p role="alert">{loadError}</p>;
  }

  if (!caseDetail) {
    return <p>Loading case…</p>;
  }

  return (
    <section>
      <h2>{caseDetail.householdHeadName}</h2>
      <dl>
        <dt>Program</dt>
        <dd>{caseDetail.programCode}</dd>
        <dt>Status</dt>
        <dd>{caseDetail.status}</dd>
        <dt>Requested on</dt>
        <dd>{caseDetail.requestedOn}</dd>
      </dl>

      <form onSubmit={handleRunDetermination}>
        <h3>Run a determination</h3>
        {runError && <p role="alert">{runError}</p>}

        <label htmlFor="asOfDate">As-of date</label>
        <input id="asOfDate" type="date" value={asOfDate} onChange={(e) => setAsOfDate(e.target.value)} />

        <label htmlFor="benefitMonth">Benefit month</label>
        <input
          id="benefitMonth"
          type="date"
          value={benefitMonth}
          onChange={(e) => setBenefitMonth(e.target.value)}
        />

        <button type="submit" disabled={running}>
          Run determination
        </button>
      </form>

      <h3>Determination history</h3>
      {caseDetail.determinations.length === 0 ? (
        <p>No determination has been made yet.</p>
      ) : (
        caseDetail.determinations.map((determination) => (
          <DeterminationPanel key={determination.determinationId} determination={determination} />
        ))
      )}
    </section>
  );
}
