import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { axe } from 'vitest-axe';
import * as client from '../api/client';
import type { NoticeReviewItem, NoticeResponse } from '../api/types';
import NoticeReviewPage from './NoticeReviewPage';

function reviewItem(overrides: Partial<NoticeReviewItem> = {}): NoticeReviewItem {
  return {
    noticeId: 'notice-1',
    programRequestId: 'pr-1',
    noticeType: 'APPROVAL',
    status: 'DRAFT',
    content: 'Dear Sam Applicant, your household is ELIGIBLE. Monthly benefit: $170.00.',
    validationResult: { passed: true, errors: [] },
    generationModel: 'llama3.2:3b',
    promptVersion: 'v1',
    createdAt: '2026-08-28T12:00:00Z',
    ...overrides,
  };
}

function decidedResponse(overrides: Partial<NoticeResponse> = {}): NoticeResponse {
  return {
    id: 'notice-1',
    programRequestId: 'pr-1',
    noticeType: 'APPROVAL',
    status: 'SENT',
    approvedAt: '2026-08-28T12:05:00Z',
    sentAt: '2026-08-28T12:05:00Z',
    ...overrides,
  };
}

beforeEach(() => {
  vi.spyOn(client, 'getNoticeReviewQueue').mockResolvedValue([]);
});

test('the review queue lists notices by type', async () => {
  vi.spyOn(client, 'getNoticeReviewQueue').mockResolvedValue([reviewItem()]);

  render(<NoticeReviewPage />);

  expect(await screen.findByText('Approval')).toBeInTheDocument();
});

test('an empty queue says so rather than showing a blank page', async () => {
  render(<NoticeReviewPage />);

  expect(await screen.findByText(/no notices are waiting for review/i)).toBeInTheDocument();
});

test('selecting a notice shows its content and a passed pre-check', async () => {
  vi.spyOn(client, 'getNoticeReviewQueue').mockResolvedValue([reviewItem()]);

  render(<NoticeReviewPage />);
  await userEvent.click(await screen.findByRole('button', { name: /approval/i }));

  expect(await screen.findByText(/monthly benefit: \$170\.00/i)).toBeInTheDocument();
  expect(screen.getByText(/pre-check passed/i)).toBeInTheDocument();
});

test('a failed pre-check renders visibly, not hidden', async () => {
  vi.spyOn(client, 'getNoticeReviewQueue').mockResolvedValue([
    reviewItem({ validationResult: { passed: false, errors: ['$999.00 is not a known figure'] } }),
  ]);

  render(<NoticeReviewPage />);

  // Visible on the queue row itself, before a reviewer even opens the notice.
  expect(await screen.findByText(/pre-check failed/i)).toBeInTheDocument();

  await userEvent.click(screen.getByRole('button', { name: /approval/i }));

  expect(await screen.findByText(/\$999\.00 is not a known figure/i)).toBeInTheDocument();
});

test('approve calls the approve endpoint and removes the notice from the queue', async () => {
  vi.spyOn(client, 'getNoticeReviewQueue').mockResolvedValue([reviewItem()]);
  const approve = vi.spyOn(client, 'approveNotice').mockResolvedValue(decidedResponse());

  render(<NoticeReviewPage />);
  await userEvent.click(await screen.findByRole('button', { name: /approval/i }));
  await userEvent.click(screen.getByRole('button', { name: /approve & send/i }));

  expect(approve).toHaveBeenCalledWith('notice-1');
  expect(await screen.findByText(/no notices are waiting for review/i)).toBeInTheDocument();
});

test('reject calls the reject endpoint and removes the notice from the queue', async () => {
  vi.spyOn(client, 'getNoticeReviewQueue').mockResolvedValue([reviewItem()]);
  const reject = vi.spyOn(client, 'rejectNotice').mockResolvedValue(decidedResponse({ status: 'REJECTED', sentAt: null }));

  render(<NoticeReviewPage />);
  await userEvent.click(await screen.findByRole('button', { name: /approval/i }));
  await userEvent.click(screen.getByRole('button', { name: /^reject$/i }));

  expect(reject).toHaveBeenCalledWith('notice-1');
  expect(await screen.findByText(/no notices are waiting for review/i)).toBeInTheDocument();
});

test('a failed approve shows an inline error and keeps the notice in the queue', async () => {
  vi.spyOn(client, 'getNoticeReviewQueue').mockResolvedValue([reviewItem()]);
  vi.spyOn(client, 'approveNotice').mockRejectedValue(new Error('500'));

  render(<NoticeReviewPage />);
  await userEvent.click(await screen.findByRole('button', { name: /approval/i }));
  await userEvent.click(screen.getByRole('button', { name: /approve & send/i }));

  expect(await screen.findByRole('alert')).toHaveTextContent(/could not approve/i);
  expect(screen.getByText('Approval')).toBeInTheDocument();
});

test('the page has no accessibility violations', async () => {
  vi.spyOn(client, 'getNoticeReviewQueue').mockResolvedValue([reviewItem()]);

  const { container } = render(<NoticeReviewPage />);
  await userEvent.click(await screen.findByRole('button', { name: /approval/i }));
  await screen.findByText(/monthly benefit/i);

  expect(await axe(container)).toHaveNoViolations();
});
