import { useEffect, useState, type FormEvent } from 'react';
import { useParams } from 'react-router-dom';
import { getAuditTrail, getCase, runDetermination } from '../api/client';
import type { AuditEventResponse, CaseDetailResponse } from '../api/types';
import DeterminationPanel from '../components/DeterminationPanel';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { AuditTrail } from '@/components/design-system/AuditTrail';
import { FormField } from '@/components/design-system/FormField';
import { RecordSheet } from '@/components/design-system/RecordSheet';
import { useBreadcrumb } from '@/components/design-system/PageChrome';

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

  const [auditEvents, setAuditEvents] = useState<AuditEventResponse[]>([]);
  const [auditError, setAuditError] = useState<string | null>(null);

  useEffect(() => {
    if (!programRequestId) {
      return;
    }
    // React StrictMode double-invokes effects in dev, and this one can race the
    // access token becoming available (AuthContext sets it asynchronously) -- an
    // early 401 from the first invocation must not clobber a later successful
    // load from the second. Same cancellation-guard pattern as WorkerCasesPage.
    let cancelled = false;
    getCase(programRequestId)
      .then((result) => {
        if (!cancelled) {
          setCaseDetail(result);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setLoadError('Could not load this case.');
        }
      });
    return () => {
      cancelled = true;
    };
  }, [programRequestId]);

  useEffect(() => {
    if (!programRequestId) {
      return;
    }
    let cancelled = false;
    getAuditTrail(programRequestId)
      .then((result) => {
        if (!cancelled) {
          setAuditEvents(result);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setAuditError('Could not load the audit trail for this case.');
        }
      });
    return () => {
      cancelled = true;
    };
  }, [programRequestId]);

  useBreadcrumb(caseDetail ? `${caseDetail.programCode} · ${caseDetail.householdHeadName}` : null);

  async function handleRunDetermination(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!programRequestId || !caseDetail) {
      return;
    }
    // A worker can already see every prior determination in the history below --
    // running a second one for a month that already has a result is almost always
    // an accidental double-click, not the "changed circumstance" the domain model's
    // append-only design exists for. This is a UI guard against that mistake, not a
    // data-layer constraint: a genuine redetermination is still just an API call away.
    const alreadyDecided = caseDetail.determinations.some((d) => d.benefitMonth === benefitMonth);
    if (alreadyDecided) {
      setRunError(`Benefit month ${benefitMonth} already has a determination. Review it below, or choose a different month.`);
      return;
    }
    setRunning(true);
    setRunError(null);
    try {
      const determination = await runDetermination(programRequestId, { asOfDate, benefitMonth });
      setCaseDetail((current) =>
        current ? { ...current, determinations: [determination, ...current.determinations] } : current,
      );
      // A new determination writes its own DETERMINATION_MADE audit event -- refetch rather than
      // fabricate one client-side, since occurredAt/actorId are server-assigned facts.
      getAuditTrail(programRequestId)
        .then(setAuditEvents)
        .catch(() => setAuditError('Could not load the audit trail for this case.'));
    } catch {
      setRunError('Could not run a determination for this case.');
    } finally {
      setRunning(false);
    }
  }

  if (loadError) {
    return (
      <p role="alert" className="text-sm text-destructive">
        {loadError}
      </p>
    );
  }

  if (!caseDetail) {
    return <p className="text-sm text-muted-foreground">Loading case…</p>;
  }

  return (
    <div className="flex flex-col gap-6">
      <RecordSheet>
        <h2 className="font-display text-xl">{caseDetail.householdHeadName}</h2>
        <dl className="mt-3 grid grid-cols-2 gap-x-6 gap-y-1">
          <dt className="text-sm text-muted-foreground">Program</dt>
          <dd className="text-sm text-foreground">{caseDetail.programCode}</dd>
          <dt className="text-sm text-muted-foreground">Status</dt>
          <dd className="text-sm text-foreground">{caseDetail.status}</dd>
          <dt className="text-sm text-muted-foreground">Requested on</dt>
          <dd className="text-sm text-foreground">{caseDetail.requestedOn}</dd>
        </dl>
      </RecordSheet>

      <RecordSheet>
        <form onSubmit={handleRunDetermination} className="flex flex-col gap-4">
          <h3 className="font-display text-lg">Run a determination</h3>
          {runError && (
            <p role="alert" className="text-sm text-destructive">
              {runError}
            </p>
          )}

          <FormField id="asOfDate" label="As-of date">
            <Input id="asOfDate" type="date" value={asOfDate} onChange={(e) => setAsOfDate(e.target.value)} />
          </FormField>

          <FormField id="benefitMonth" label="Benefit month">
            <Input
              id="benefitMonth"
              type="date"
              value={benefitMonth}
              onChange={(e) => setBenefitMonth(e.target.value)}
            />
          </FormField>

          <Button type="submit" disabled={running} className="self-start">
            {running ? 'Running…' : 'Run determination'}
          </Button>
        </form>
      </RecordSheet>

      <div>
        <h3 className="font-display text-lg">Determination history</h3>
        {caseDetail.determinations.length === 0 ? (
          <p className="mt-2 text-sm text-muted-foreground">No determination has been made yet.</p>
        ) : (
          <div className="mt-3 flex flex-col gap-3">
            {caseDetail.determinations.map((determination) => (
              <DeterminationPanel key={determination.determinationId} determination={determination} />
            ))}
          </div>
        )}
      </div>

      <div>
        <h3 className="font-display text-lg">Audit trail</h3>
        {auditError && (
          <p role="alert" className="mt-2 text-sm text-destructive">
            {auditError}
          </p>
        )}
        <div className="mt-3">
          <AuditTrail events={auditEvents} />
        </div>
      </div>
    </div>
  );
}
