import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { axe } from 'vitest-axe';
import * as client from '../api/client';
import type { FraudRiskScoreItem } from '../api/types';
import FraudReviewPage from './FraudReviewPage';

function reviewItem(overrides: Partial<FraudRiskScoreItem> = {}): FraudRiskScoreItem {
  return {
    id: 'score-1',
    programRequestId: 'pr-1',
    determinationId: 'det-1',
    score: 0.9,
    topContributingFeatures: [{ feature: 'income_volatility', value: 4.5, z_score: 3.2 }],
    modelVersion: 'isolation-forest-v1',
    scoredAt: '2026-08-30T12:00:00Z',
    reviewOutcome: null,
    reviewedBy: null,
    reviewedAt: null,
    ...overrides,
  };
}

function decidedResponse(overrides: Partial<FraudRiskScoreItem> = {}): FraudRiskScoreItem {
  return reviewItem({
    reviewOutcome: 'CONFIRMED_RISK',
    reviewedBy: 'supervisor.robin',
    reviewedAt: '2026-08-30T12:05:00Z',
    ...overrides,
  });
}

beforeEach(() => {
  vi.spyOn(client, 'getFraudReviewQueue').mockResolvedValue([]);
});

test('the review queue lists flagged cases by model', async () => {
  vi.spyOn(client, 'getFraudReviewQueue').mockResolvedValue([reviewItem()]);

  render(<FraudReviewPage />);

  expect(await screen.findByText('isolation-forest-v1')).toBeInTheDocument();
});

test('an empty queue says so rather than showing a blank page', async () => {
  render(<FraudReviewPage />);

  expect(await screen.findByText(/no flags are waiting for review/i)).toBeInTheDocument();
});

test('selecting a flag shows its score and top contributing features', async () => {
  vi.spyOn(client, 'getFraudReviewQueue').mockResolvedValue([reviewItem()]);

  render(<FraudReviewPage />);
  await userEvent.click(await screen.findByRole('button', { name: /isolation-forest-v1/i }));

  expect(await screen.findByText(/income_volatility/i)).toBeInTheDocument();
  expect(screen.getByText(/3\.20 standard deviations/i)).toBeInTheDocument();
});

test('confirm calls the confirm endpoint and removes the flag from the queue', async () => {
  vi.spyOn(client, 'getFraudReviewQueue').mockResolvedValue([reviewItem()]);
  const confirm = vi.spyOn(client, 'confirmFraudRisk').mockResolvedValue(decidedResponse());

  render(<FraudReviewPage />);
  await userEvent.click(await screen.findByRole('button', { name: /isolation-forest-v1/i }));
  await userEvent.click(screen.getByRole('button', { name: /confirm risk/i }));

  expect(confirm).toHaveBeenCalledWith('score-1');
  expect(await screen.findByText(/no flags are waiting for review/i)).toBeInTheDocument();
});

test('clear calls the clear endpoint and removes the flag from the queue', async () => {
  vi.spyOn(client, 'getFraudReviewQueue').mockResolvedValue([reviewItem()]);
  const clear = vi
    .spyOn(client, 'clearFraudRisk')
    .mockResolvedValue(decidedResponse({ reviewOutcome: 'CLEARED' }));

  render(<FraudReviewPage />);
  await userEvent.click(await screen.findByRole('button', { name: /isolation-forest-v1/i }));
  await userEvent.click(screen.getByRole('button', { name: /^clear$/i }));

  expect(clear).toHaveBeenCalledWith('score-1');
  expect(await screen.findByText(/no flags are waiting for review/i)).toBeInTheDocument();
});

test('a failed confirm shows an inline error and keeps the flag in the queue', async () => {
  vi.spyOn(client, 'getFraudReviewQueue').mockResolvedValue([reviewItem()]);
  vi.spyOn(client, 'confirmFraudRisk').mockRejectedValue(new Error('500'));

  render(<FraudReviewPage />);
  await userEvent.click(await screen.findByRole('button', { name: /isolation-forest-v1/i }));
  await userEvent.click(screen.getByRole('button', { name: /confirm risk/i }));

  expect(await screen.findByRole('alert')).toHaveTextContent(/could not confirm/i);
  expect(screen.getByText('isolation-forest-v1')).toBeInTheDocument();
});

test('the page has no accessibility violations', async () => {
  vi.spyOn(client, 'getFraudReviewQueue').mockResolvedValue([reviewItem()]);

  const { container } = render(<FraudReviewPage />);
  await userEvent.click(await screen.findByRole('button', { name: /isolation-forest-v1/i }));
  await screen.findByText(/income_volatility/i);

  expect(await axe(container)).toHaveNoViolations();
});
