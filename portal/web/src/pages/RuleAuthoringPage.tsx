import { useEffect, useState, type FormEvent } from 'react';
import { listProposals, proposeParameterChanges, reviewProposal } from '../api/client';
import type { ParameterProposal, ProposedParameterValue, PublicationDetails } from '../api/types';

function scopeLabel(householdSize: number | null): string {
  return householdSize === null ? 'All sizes' : `Size ${householdSize}`;
}

function DiffTable({ changes }: { changes: ProposedParameterValue[] }) {
  return (
    <table>
      <caption>Proposed parameter changes</caption>
      <thead>
        <tr>
          <th scope="col">Parameter</th>
          <th scope="col">Household</th>
          <th scope="col">Current</th>
          <th scope="col">Proposed</th>
          <th scope="col">Unit</th>
          <th scope="col">Why</th>
        </tr>
      </thead>
      <tbody>
        {changes.map((change) => (
          <tr key={`${change.name}/${change.householdSize}`}>
            <th scope="row">{change.name}</th>
            <td>{scopeLabel(change.householdSize)}</td>
            <td>{change.oldValue}</td>
            <td>{change.newValue}</td>
            <td>{change.unit}</td>
            <td>{change.rationale}</td>
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
  return (
    <fieldset>
      <legend>Publication details</legend>
      <label htmlFor="versionLabel">Version label</label>
      <input
        id="versionLabel"
        value={details.versionLabel}
        onChange={(e) => onChange({ ...details, versionLabel: e.target.value })}
      />
      <label htmlFor="effectiveFrom">Effective from</label>
      <input
        id="effectiveFrom"
        type="date"
        value={details.effectiveFrom}
        onChange={(e) => onChange({ ...details, effectiveFrom: e.target.value })}
      />
      <label htmlFor="sourceCitation">Source citation</label>
      <input
        id="sourceCitation"
        value={details.sourceCitation}
        onChange={(e) => onChange({ ...details, sourceCitation: e.target.value })}
      />
    </fieldset>
  );
}

const EMPTY_DETAILS: PublicationDetails = { versionLabel: '', effectiveFrom: '', sourceCitation: '' };

export default function RuleAuthoringPage() {
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

  const complete = Boolean(details.versionLabel && details.effectiveFrom && details.sourceCitation);
  const pending = proposal?.status === 'PENDING';
  const hasChanges = (proposal?.proposedValues.length ?? 0) > 0;

  async function handleDraft(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setDrafting(true);
    setError(null);
    try {
      setProposal(await proposeParameterChanges(excerpt));
      setDetails(EMPTY_DETAILS);
    } catch {
      setError('Could not draft a proposal from this excerpt. Please try again, or paste a clearer excerpt.');
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
      setError(
        accept
          ? 'Could not publish these changes. Nothing was published; please check the version label and try again.'
          : 'Could not record the rejection. Please try again.',
      );
    } finally {
      setReviewing(false);
    }
  }

  return (
    <section>
      <h2>Rule authoring</h2>
      <p>
        Paste an excerpt from a published policy document. The copilot drafts the parameter changes it
        states, and you review every one of them before deciding.
      </p>

      <form onSubmit={handleDraft}>
        {error && <p role="alert">{error}</p>}
        <label htmlFor="excerpt">Policy document excerpt</label>
        <textarea id="excerpt" rows={6} value={excerpt} onChange={(e) => setExcerpt(e.target.value)} />
        <button type="submit" disabled={drafting || !excerpt.trim()}>
          Draft proposed changes
        </button>
      </form>

      {waiting.length > 0 && (
        <>
          <h3>Waiting for review</h3>
          <ul>
            {waiting.map((each) => (
              <li key={each.id}>
                <button type="button" onClick={() => review(each)}>
                  Review the draft against {each.currentVersionLabel}, proposed by {each.proposedBy}
                </button>
              </li>
            ))}
          </ul>
        </>
      )}

      {proposal && (
        <article>
          <h3>Draft against {proposal.currentVersionLabel}</h3>
          <p>
            Drafted by {proposal.generationModel} (prompt {proposal.promptVersion}). A draft, not a decision
            — nothing is published until you accept it.
          </p>

          {hasChanges ? (
            <DiffTable changes={proposal.proposedValues} />
          ) : (
            <p>No parameter changes were found in this excerpt.</p>
          )}

          {proposal.status !== 'PENDING' && (
            <p>
              {proposal.status === 'ACCEPTED' ? 'Accepted' : 'Rejected'} by {proposal.reviewedBy}.
              {proposal.publishedParameterSetId &&
                ` Published as parameter set ${proposal.publishedParameterSetId}.`}
            </p>
          )}

          {pending && hasChanges && (
            <>
              <PublicationFields details={details} onChange={setDetails} />
              <button type="button" disabled={reviewing || !complete} onClick={() => handleReview(true)}>
                Accept and publish
              </button>
              <button type="button" disabled={reviewing} onClick={() => handleReview(false)}>
                Reject
              </button>
            </>
          )}
        </article>
      )}
    </section>
  );
}
