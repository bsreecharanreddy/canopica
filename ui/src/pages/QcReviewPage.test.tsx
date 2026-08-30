import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { axe } from 'vitest-axe';
import * as client from '../api/client';
import type { PaymentErrorReviewItem } from '../api/types';
import QcReviewPage from './QcReviewPage';

function reviewItem(overrides: Partial<PaymentErrorReviewItem> = {}): PaymentErrorReviewItem {
  return {
    id: 'review-1',
    determinationId: 'det-1',
    originalAmount: 649.0,
    reproducedAmount: 749.0,
    errorAmount: 100.0,
    aiSummary: 'The parameter set changed between the original decision and re-derivation.',
    sampledAt: '2026-08-30T12:00:00Z',
    reviewOutcome: null,
    reviewedBy: null,
    reviewedAt: null,
    ...overrides,
  };
}

function decidedResponse(overrides: Partial<PaymentErrorReviewItem> = {}): PaymentErrorReviewItem {
  return reviewItem({
    reviewOutcome: 'CONFIRMED_ERROR',
    reviewedBy: 'supervisor.robin',
    reviewedAt: '2026-08-30T12:05:00Z',
    ...overrides,
  });
}

beforeEach(() => {
  vi.spyOn(client, 'getQcReviewQueue').mockResolvedValue([]);
});

test('the review queue lists flagged discrepancies by original amount', async () => {
  vi.spyOn(client, 'getQcReviewQueue').mockResolvedValue([reviewItem()]);

  render(<QcReviewPage />);

  expect(await screen.findByText('$649.00')).toBeInTheDocument();
});

test('an empty queue says so rather than showing a blank page', async () => {
  render(<QcReviewPage />);

  expect(await screen.findByText(/no discrepancies are waiting for review/i)).toBeInTheDocument();
});

test('selecting a discrepancy shows the amounts and the AI-drafted summary', async () => {
  vi.spyOn(client, 'getQcReviewQueue').mockResolvedValue([reviewItem()]);

  render(<QcReviewPage />);
  await userEvent.click(await screen.findByRole('button', { name: /649\.00/i }));

  expect(await screen.findByText(/parameter set changed/i)).toBeInTheDocument();
  expect(screen.getByText(/\$649\.00.*\$749\.00.*\$100\.00/)).toBeInTheDocument();
});

test('confirm calls the confirm endpoint and removes the discrepancy from the queue', async () => {
  vi.spyOn(client, 'getQcReviewQueue').mockResolvedValue([reviewItem()]);
  const confirm = vi.spyOn(client, 'confirmQcReview').mockResolvedValue(decidedResponse());

  render(<QcReviewPage />);
  await userEvent.click(await screen.findByRole('button', { name: /649\.00/i }));
  await userEvent.click(screen.getByRole('button', { name: /confirm error/i }));

  expect(confirm).toHaveBeenCalledWith('review-1');
  expect(await screen.findByText(/no discrepancies are waiting for review/i)).toBeInTheDocument();
});

test('dismiss calls the dismiss endpoint and removes the discrepancy from the queue', async () => {
  vi.spyOn(client, 'getQcReviewQueue').mockResolvedValue([reviewItem()]);
  const dismiss = vi
    .spyOn(client, 'dismissQcReview')
    .mockResolvedValue(decidedResponse({ reviewOutcome: 'DISMISSED' }));

  render(<QcReviewPage />);
  await userEvent.click(await screen.findByRole('button', { name: /649\.00/i }));
  await userEvent.click(screen.getByRole('button', { name: /^dismiss$/i }));

  expect(dismiss).toHaveBeenCalledWith('review-1');
  expect(await screen.findByText(/no discrepancies are waiting for review/i)).toBeInTheDocument();
});

test('a failed confirm shows an inline error and keeps the discrepancy in the queue', async () => {
  vi.spyOn(client, 'getQcReviewQueue').mockResolvedValue([reviewItem()]);
  vi.spyOn(client, 'confirmQcReview').mockRejectedValue(new Error('500'));

  render(<QcReviewPage />);
  await userEvent.click(await screen.findByRole('button', { name: /649\.00/i }));
  await userEvent.click(screen.getByRole('button', { name: /confirm error/i }));

  expect(await screen.findByRole('alert')).toHaveTextContent(/could not confirm/i);
  expect(screen.getByText('$649.00')).toBeInTheDocument();
});

test('a pending discrepancy with no AI summary yet says so', async () => {
  vi.spyOn(client, 'getQcReviewQueue').mockResolvedValue([reviewItem({ aiSummary: null })]);

  render(<QcReviewPage />);
  await userEvent.click(await screen.findByRole('button', { name: /649\.00/i }));

  expect(await screen.findByText(/no summary yet/i)).toBeInTheDocument();
});

test('the page has no accessibility violations', async () => {
  vi.spyOn(client, 'getQcReviewQueue').mockResolvedValue([reviewItem()]);

  const { container } = render(<QcReviewPage />);
  await userEvent.click(await screen.findByRole('button', { name: /649\.00/i }));
  await screen.findByText(/parameter set changed/i);

  expect(await axe(container)).toHaveNoViolations();
});
