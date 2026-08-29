import { useEffect, useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import type { TFunction } from 'i18next';
import { listProposals, proposeParameterChanges, reviewProposal } from '../api/client';
import type { ParameterProposal, ProposedParameterValue, PublicationDetails } from '../api/types';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { FormField } from '@/components/design-system/FormField';
import { RecordSheet } from '@/components/design-system/RecordSheet';
import { StatusPill } from '@/components/design-system/StatusPill';
import { AiAdvisoryBadge } from '@/components/design-system/AiAdvisoryBadge';

function scopeLabel(t: TFunction<'ruleAuthoring'>, householdSize: number | null): string {
  return householdSize === null ? t('diffTable.allSizes') : t('diffTable.size', { size: householdSize });
}

function DiffTable({ changes }: { changes: ProposedParameterValue[] }) {
  const { t } = useTranslation('ruleAuthoring');
  return (
    <table className="w-full border-collapse text-sm">
      <caption className="mb-2 text-left text-sm text-muted-foreground">{t('diffTable.caption')}</caption>
      <thead>
        <tr>
          <th
            scope="col"
            className="border-b border-border px-3 py-2 text-left text-xs uppercase tracking-wide text-muted-foreground"
          >
            {t('diffTable.parameter')}
          </th>
          <th
            scope="col"
            className="border-b border-border px-3 py-2 text-left text-xs uppercase tracking-wide text-muted-foreground"
          >
            {t('diffTable.household')}
          </th>
          <th
            scope="col"
            className="border-b border-border px-3 py-2 text-left text-xs uppercase tracking-wide text-muted-foreground"
          >
            {t('diffTable.current')}
          </th>
          <th
            scope="col"
            className="border-b border-border px-3 py-2 text-left text-xs uppercase tracking-wide text-muted-foreground"
          >
            {t('diffTable.proposed')}
          </th>
          <th
            scope="col"
            className="border-b border-border px-3 py-2 text-left text-xs uppercase tracking-wide text-muted-foreground"
          >
            {t('diffTable.unit')}
          </th>
          <th
            scope="col"
            className="border-b border-border px-3 py-2 text-left text-xs uppercase tracking-wide text-muted-foreground"
          >
            {t('diffTable.why')}
          </th>
        </tr>
      </thead>
      <tbody>
        {changes.map((change) => (
          <tr key={`${change.name}/${change.householdSize}`} className="border-b border-border">
            <th scope="row" className="px-3 py-2 text-left font-normal text-foreground">
              {change.name}
            </th>
            <td className="px-3 py-2 text-muted-foreground">{scopeLabel(t, change.householdSize)}</td>
            <td className="px-3 py-2 text-muted-foreground">{change.oldValue}</td>
            <td className="px-3 py-2 font-medium text-foreground">{change.newValue}</td>
            <td className="px-3 py-2 text-muted-foreground">{change.unit}</td>
            <td className="px-3 py-2 text-muted-foreground">{change.rationale}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

/**
 * Publication details, collected only on the accept path. Deliberately not
 * pre-filled: an effective date is a policy fact the memo states, and a version
 * label is unique by database constraint -- a default would publish a parameter
 * version under a date or a name nobody chose.
 */
function PublicationFields({
  details,
  onChange,
}: {
  details: PublicationDetails;
  onChange: (next: PublicationDetails) => void;
}) {
  const { t } = useTranslation('ruleAuthoring');
  return (
    <RecordSheet className="mt-4 flex flex-col gap-4">
      <h4 className="font-display text-base">{t('publicationDetails.heading')}</h4>
      <FormField id="versionLabel" label={t('publicationDetails.versionLabel')}>
        <Input
          id="versionLabel"
          value={details.versionLabel}
          onChange={(e) => onChange({ ...details, versionLabel: e.target.value })}
        />
      </FormField>
      <FormField id="effectiveFrom" label={t('publicationDetails.effectiveFrom')}>
        <Input
          id="effectiveFrom"
          type="date"
          value={details.effectiveFrom}
          onChange={(e) => onChange({ ...details, effectiveFrom: e.target.value })}
        />
      </FormField>
      <FormField id="sourceCitation" label={t('publicationDetails.sourceCitation')}>
        <Input
          id="sourceCitation"
          value={details.sourceCitation}
          onChange={(e) => onChange({ ...details, sourceCitation: e.target.value })}
        />
      </FormField>
    </RecordSheet>
  );
}

const EMPTY_DETAILS: PublicationDetails = { versionLabel: '', effectiveFrom: '', sourceCitation: '' };

function PendingProposalsList({
  waiting,
  onReview,
}: {
  waiting: ParameterProposal[];
  onReview: (proposal: ParameterProposal) => void;
}) {
  const { t } = useTranslation('ruleAuthoring');
  if (waiting.length === 0) return null;
  return (
    <>
      <h3 className="font-display text-lg">{t('waitingForReview')}</h3>
      <ul className="mt-2 flex flex-col gap-3">
        {waiting.map((each) => (
          <li key={each.id}>
            <RecordSheet>
              <Button variant="outline" type="button" onClick={() => onReview(each)}>
                {t('reviewDraftAgainst', { versionLabel: each.currentVersionLabel, proposedBy: each.proposedBy })}
              </Button>
            </RecordSheet>
          </li>
        ))}
      </ul>
    </>
  );
}

function ReviewedStatusBanner({ proposal }: { proposal: ParameterProposal }) {
  const { t } = useTranslation('ruleAuthoring');
  if (proposal.status === 'PENDING') return null;
  return (
    <p className="mt-2 text-sm text-muted-foreground">
      <StatusPill tone={proposal.status === 'ACCEPTED' ? 'affirmed' : 'exception'}>
        {proposal.status === 'ACCEPTED' ? t('accepted') : t('rejected')}
      </StatusPill>{' '}
      {t('reviewedByStatus', { reviewedBy: proposal.reviewedBy })}
      {proposal.publishedParameterSetId && t('published', { id: proposal.publishedParameterSetId })}
    </p>
  );
}

function ProposalReview({
  proposal,
  details,
  onDetailsChange,
  reviewing,
  onAccept,
  onReject,
}: {
  proposal: ParameterProposal;
  details: PublicationDetails;
  onDetailsChange: (next: PublicationDetails) => void;
  reviewing: boolean;
  onAccept: () => void;
  onReject: () => void;
}) {
  const { t } = useTranslation('ruleAuthoring');
  const hasChanges = proposal.proposedValues.length > 0;
  const pending = proposal.status === 'PENDING';
  const complete = Boolean(details.versionLabel && details.effectiveFrom && details.sourceCitation);

  return (
    <RecordSheet>
      <AiAdvisoryBadge />
      <h3 className="mt-2 font-display text-lg">
        {t('draftAgainst', { versionLabel: proposal.currentVersionLabel })}
      </h3>
      <p className="mt-1 text-sm text-muted-foreground">
        {t('draftedBy', { model: proposal.generationModel, promptVersion: proposal.promptVersion })}
      </p>

      {hasChanges ? (
        <div className="mt-4">
          <DiffTable changes={proposal.proposedValues} />
        </div>
      ) : (
        <p className="mt-4 text-sm text-muted-foreground">{t('noChanges')}</p>
      )}

      <ReviewedStatusBanner proposal={proposal} />

      {pending && hasChanges && (
        <>
          <PublicationFields details={details} onChange={onDetailsChange} />
          <div className="mt-4 flex gap-3">
            <Button type="button" disabled={reviewing || !complete} onClick={onAccept}>
              {reviewing ? t('reviewing') : t('acceptAndPublish')}
            </Button>
            <Button variant="outline" type="button" disabled={reviewing} onClick={onReject}>
              {reviewing ? t('reviewing') : t('reject')}
            </Button>
          </div>
        </>
      )}
    </RecordSheet>
  );
}

export default function RuleAuthoringPage() {
  const { t } = useTranslation('ruleAuthoring');
  const [excerpt, setExcerpt] = useState('');
  const [proposal, setProposal] = useState<ParameterProposal | null>(null);
  const [details, setDetails] = useState<PublicationDetails>(EMPTY_DETAILS);
  const [waiting, setWaiting] = useState<ParameterProposal[]>([]);
  const [drafting, setDrafting] = useState(false);
  const [reviewing, setReviewing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // A proposal drafted in an earlier session is still pending in the database.
  // Loading it here is what stops it from being unreachable -- and a pending
  // parameter change nobody can find is worse than one nobody drafted.
  useEffect(() => {
    listProposals('PENDING')
      .then(setWaiting)
      .catch(() => setWaiting([]));
  }, []);

  function review(chosen: ParameterProposal) {
    setProposal(chosen);
    setDetails(EMPTY_DETAILS);
    setError(null);
  }

  async function handleDraft(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setDrafting(true);
    setError(null);
    try {
      setProposal(await proposeParameterChanges(excerpt));
      setDetails(EMPTY_DETAILS);
    } catch {
      setError(t('draftError'));
    } finally {
      setDrafting(false);
    }
  }

  async function handleReview(accept: boolean) {
    if (!proposal) return;
    setReviewing(true);
    setError(null);
    try {
      setProposal(await reviewProposal(proposal.id, accept, accept ? details : undefined));
    } catch {
      setError(accept ? t('acceptError') : t('rejectError'));
    } finally {
      setReviewing(false);
    }
  }

  return (
    <section className="flex flex-col gap-6">
      <div>
        <h2 className="font-display text-xl">{t('heading')}</h2>
        <p className="mt-1 text-sm text-muted-foreground">{t('description')}</p>
      </div>

      <form onSubmit={handleDraft} className="flex flex-col gap-4">
        {error && (
          <p role="alert" className="text-sm text-destructive">
            {error}
          </p>
        )}
        <FormField id="excerpt" label={t('excerptLabel')}>
          <Textarea id="excerpt" rows={6} value={excerpt} onChange={(e) => setExcerpt(e.target.value)} />
        </FormField>
        <Button type="submit" disabled={drafting || !excerpt.trim()} className="self-start">
          {drafting ? t('drafting') : t('draft')}
        </Button>
      </form>

      <PendingProposalsList waiting={waiting} onReview={review} />

      {proposal && (
        <ProposalReview
          proposal={proposal}
          details={details}
          onDetailsChange={setDetails}
          reviewing={reviewing}
          onAccept={() => handleReview(true)}
          onReject={() => handleReview(false)}
        />
      )}
    </section>
  );
}
