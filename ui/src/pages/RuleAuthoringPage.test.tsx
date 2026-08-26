import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { axe } from 'vitest-axe';
import * as client from '../api/client';
import type { ParameterProposal } from '../api/types';
import RuleAuthoringPage from './RuleAuthoringPage';

function proposal(overrides: Partial<ParameterProposal> = {}): ParameterProposal {
  return {
    id: 'proposal-1',
    currentParameterSetId: 'set-2026',
    currentVersionLabel: 'SNAP-FY2026',
    sourceExcerpt: 'The maximum allotment for a household of one increases from $298 to $305.',
    proposedValues: [
      {
        name: 'MAX_ALLOTMENT',
        householdSize: 1,
        oldValue: '298',
        newValue: '305',
        unit: 'USD_PER_MONTH',
        rationale: 'The memo states the one-person allotment rises to $305.',
      },
    ],
    status: 'PENDING',
    proposedBy: 'admin.alex',
    reviewedBy: null,
    reviewedAt: null,
    publishedParameterSetId: null,
    generationModel: 'llama3.2:3b',
    promptVersion: 'v1',
    createdAt: '2026-08-23T12:00:00Z',
    ...overrides,
  };
}

beforeEach(() => {
  vi.spyOn(client, 'listProposals').mockResolvedValue([]);
});

test('proposals already waiting for review are listed on arrival', async () => {
  // Without this the workflow has a hole: a proposal drafted in one session and
  // not decided on is unreachable from the UI afterwards, even though the row is
  // sitting in the database waiting for exactly this screen.
  vi.spyOn(client, 'listProposals').mockResolvedValue([proposal({ id: 'proposal-waiting' })]);

  render(<RuleAuthoringPage />);

  const waiting = await screen.findByRole('button', { name: /review the draft against SNAP-FY2026/i });
  await userEvent.click(waiting);

  expect(await screen.findByRole('row', { name: /MAX_ALLOTMENT/ })).toBeInTheDocument();
});

test('drafting a proposal shows the diff line by line with the model’s rationale', async () => {
  const propose = vi.spyOn(client, 'proposeParameterChanges').mockResolvedValue(proposal());

  render(<RuleAuthoringPage />);
  await userEvent.type(screen.getByLabelText(/policy document excerpt/i), 'FY2027 COLA memo');
  await userEvent.click(screen.getByRole('button', { name: /draft proposed changes/i }));

  expect(propose).toHaveBeenCalledWith('FY2027 COLA memo');
  const row = await screen.findByRole('row', { name: /MAX_ALLOTMENT/ });
  expect(within(row).getByText('298')).toBeInTheDocument();
  expect(within(row).getByText('305')).toBeInTheDocument();
  expect(within(row).getByText(/one-person allotment rises/i)).toBeInTheDocument();
});

test('the draft is labelled as a draft, naming the model that wrote it', async () => {
  // The governing principle has to be legible on the screen, not just in the
  // code: a reviewer must never be able to mistake this for a decision that
  // has already been made.
  vi.spyOn(client, 'proposeParameterChanges').mockResolvedValue(proposal());

  render(<RuleAuthoringPage />);
  await userEvent.type(screen.getByLabelText(/policy document excerpt/i), 'FY2027 COLA memo');
  await userEvent.click(screen.getByRole('button', { name: /draft proposed changes/i }));

  expect(await screen.findByText(/drafted by llama3\.2:3b/i)).toBeInTheDocument();
  expect(screen.getByText(/nothing is published until you accept/i)).toBeInTheDocument();
});

test('accepting requires the publication details and sends them', async () => {
  vi.spyOn(client, 'proposeParameterChanges').mockResolvedValue(proposal());
  const review = vi
    .spyOn(client, 'reviewProposal')
    .mockResolvedValue(proposal({ status: 'ACCEPTED', reviewedBy: 'admin.alex', publishedParameterSetId: 'set-2027' }));

  render(<RuleAuthoringPage />);
  await userEvent.type(screen.getByLabelText(/policy document excerpt/i), 'FY2027 COLA memo');
  await userEvent.click(screen.getByRole('button', { name: /draft proposed changes/i }));
  await screen.findByRole('row', { name: /MAX_ALLOTMENT/ });

  await userEvent.type(screen.getByLabelText(/version label/i), 'SNAP-FY2027');
  await userEvent.type(screen.getByLabelText(/effective from/i), '2026-10-01');
  await userEvent.type(screen.getByLabelText(/source citation/i), 'FY2027 COLA memo, USDA FNS');
  await userEvent.click(screen.getByRole('button', { name: /accept and publish/i }));

  expect(review).toHaveBeenCalledWith('proposal-1', true, {
    versionLabel: 'SNAP-FY2027',
    effectiveFrom: '2026-10-01',
    sourceCitation: 'FY2027 COLA memo, USDA FNS',
  });
});

test('accept is disabled until every publication detail is filled in', async () => {
  // None of the three can be defaulted -- publishing under a date or label
  // nobody chose is the failure this guards.
  vi.spyOn(client, 'proposeParameterChanges').mockResolvedValue(proposal());

  render(<RuleAuthoringPage />);
  await userEvent.type(screen.getByLabelText(/policy document excerpt/i), 'FY2027 COLA memo');
  await userEvent.click(screen.getByRole('button', { name: /draft proposed changes/i }));
  await screen.findByRole('row', { name: /MAX_ALLOTMENT/ });

  expect(screen.getByRole('button', { name: /accept and publish/i })).toBeDisabled();
  await userEvent.type(screen.getByLabelText(/version label/i), 'SNAP-FY2027');
  expect(screen.getByRole('button', { name: /accept and publish/i })).toBeDisabled();
  await userEvent.type(screen.getByLabelText(/effective from/i), '2026-10-01');
  await userEvent.type(screen.getByLabelText(/source citation/i), 'FY2027 COLA memo, USDA FNS');
  expect(screen.getByRole('button', { name: /accept and publish/i })).toBeEnabled();
});

test('rejecting needs no publication details and publishes nothing', async () => {
  vi.spyOn(client, 'proposeParameterChanges').mockResolvedValue(proposal());
  const review = vi
    .spyOn(client, 'reviewProposal')
    .mockResolvedValue(proposal({ status: 'REJECTED', reviewedBy: 'admin.alex' }));

  render(<RuleAuthoringPage />);
  await userEvent.type(screen.getByLabelText(/policy document excerpt/i), 'FY2027 COLA memo');
  await userEvent.click(screen.getByRole('button', { name: /draft proposed changes/i }));
  await screen.findByRole('row', { name: /MAX_ALLOTMENT/ });

  await userEvent.click(screen.getByRole('button', { name: /^reject$/i }));

  expect(review).toHaveBeenCalledWith('proposal-1', false, undefined);
  expect(await screen.findByText(/rejected/i)).toBeInTheDocument();
});

test('a proposal that changes nothing says so instead of showing an empty table', async () => {
  vi.spyOn(client, 'proposeParameterChanges').mockResolvedValue(proposal({ proposedValues: [] }));

  render(<RuleAuthoringPage />);
  await userEvent.type(screen.getByLabelText(/policy document excerpt/i), 'An unrelated memo');
  await userEvent.click(screen.getByRole('button', { name: /draft proposed changes/i }));

  expect(await screen.findByText(/no parameter changes/i)).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: /accept and publish/i })).not.toBeInTheDocument();
});

test('a failed draft shows an inline error rather than a silent no-op', async () => {
  vi.spyOn(client, 'proposeParameterChanges').mockRejectedValue(new Error('502'));

  render(<RuleAuthoringPage />);
  await userEvent.type(screen.getByLabelText(/policy document excerpt/i), 'FY2027 COLA memo');
  await userEvent.click(screen.getByRole('button', { name: /draft proposed changes/i }));

  expect(await screen.findByRole('alert')).toHaveTextContent(/could not draft/i);
});

test('the page has no accessibility violations', async () => {
  vi.spyOn(client, 'proposeParameterChanges').mockResolvedValue(proposal());

  const { container } = render(<RuleAuthoringPage />);
  await userEvent.type(screen.getByLabelText(/policy document excerpt/i), 'FY2027 COLA memo');
  await userEvent.click(screen.getByRole('button', { name: /draft proposed changes/i }));
  await screen.findByRole('row', { name: /MAX_ALLOTMENT/ });

  expect(await axe(container)).toHaveNoViolations();
});
