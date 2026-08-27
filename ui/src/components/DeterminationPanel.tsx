import type { DeterminationResponse } from '../api/types';
import { DecisionBar } from './design-system/DecisionBar';
import { RecordSheet } from './design-system/RecordSheet';
import { StatusPill } from './design-system/StatusPill';
import TracePanel from './TracePanel';

type Props = {
  determination: DeterminationResponse;
};

export default function DeterminationPanel({ determination }: Props) {
  return (
    <RecordSheet aria-label={`Determination decided ${determination.decidedAt}`}>
      <StatusPill tone={determination.eligible ? 'affirmed' : 'exception'}>
        {determination.eligible ? 'Eligible' : 'Not eligible'}
      </StatusPill>
      <DecisionBar
        amount={determination.benefitAmount}
        policyVersion={determination.policyParameterVersion}
        note={`Decided ${determination.decidedAt}`}
      />
      <dl className="mt-3 grid grid-cols-2 gap-x-6 gap-y-1">
        <dt className="text-sm text-muted-foreground">Reason code</dt>
        <dd className="text-sm text-foreground">{determination.reasonCode}</dd>
        <dt className="text-sm text-muted-foreground">Benefit month</dt>
        <dd className="text-sm text-foreground">{determination.benefitMonth}</dd>
        <dt className="text-sm text-muted-foreground">As-of date</dt>
        <dd className="text-sm text-foreground">{determination.asOfDate}</dd>
      </dl>
      <TracePanel determinationId={determination.determinationId} />
    </RecordSheet>
  );
}
