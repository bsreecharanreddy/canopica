import type { DeterminationResponse } from '../api/types';
import TracePanel from './TracePanel';

type Props = {
  determination: DeterminationResponse;
};

export default function DeterminationPanel({ determination }: Props) {
  return (
    <article aria-label={`Determination decided ${determination.decidedAt}`}>
      <p>
        <strong>{determination.eligible ? 'Eligible' : 'Not eligible'}</strong>
        {' — '}
        <span>${determination.benefitAmount}/month</span>
      </p>
      <dl>
        <dt>Reason code</dt>
        <dd>{determination.reasonCode}</dd>
        <dt>Policy parameter version in force</dt>
        <dd>{determination.policyParameterVersion}</dd>
        <dt>Benefit month</dt>
        <dd>{determination.benefitMonth}</dd>
        <dt>As-of date</dt>
        <dd>{determination.asOfDate}</dd>
        <dt>Decided at</dt>
        <dd>{determination.decidedAt}</dd>
      </dl>
      <TracePanel determinationId={determination.determinationId} />
    </article>
  );
}
