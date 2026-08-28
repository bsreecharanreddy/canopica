import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { axe } from 'vitest-axe';
import * as client from '../api/client';
import type { DocumentReviewItem, DocumentResponse } from '../api/types';
import DocumentReviewPage from './DocumentReviewPage';

function reviewItem(overrides: Partial<DocumentReviewItem> = {}): DocumentReviewItem {
  return {
    documentId: 'doc-1',
    programRequestId: 'pr-1',
    contentType: 'application/pdf',
    extractionConfidence: '0.400',
    extraction: {
      document_type: 'INCOME_REPORT',
      fields: [{ name: 'monthly_amount', value: '1500.00', confidence: 0.4 }],
      matched_verification_ids: ['verification-1'],
      generation_model: 'llama3.2:3b',
      prompt_version: 'v1',
    },
    uploadedAt: '2026-08-28T12:00:00Z',
    headPersonId: 'person-1',
    householdHeadName: 'Dana Reyes',
    ...overrides,
  };
}

function confirmedResponse(overrides: Partial<DocumentResponse> = {}): DocumentResponse {
  return {
    id: 'doc-1',
    programRequestId: 'pr-1',
    contentType: 'application/pdf',
    classificationStatus: 'CONFIRMED',
    uploadedAt: '2026-08-28T12:00:00Z',
    ...overrides,
  };
}

beforeEach(() => {
  vi.spyOn(client, 'getDocumentReviewQueue').mockResolvedValue([]);
});

test('the review queue lists documents with their household and confidence', async () => {
  vi.spyOn(client, 'getDocumentReviewQueue').mockResolvedValue([reviewItem()]);

  render(<DocumentReviewPage />);

  expect(await screen.findByText('Dana Reyes')).toBeInTheDocument();
  expect(screen.getByText(/low confidence/i)).toBeInTheDocument();
});

test('an empty queue says so rather than showing a blank page', async () => {
  render(<DocumentReviewPage />);

  expect(await screen.findByText(/no documents are waiting for review/i)).toBeInTheDocument();
});

test('selecting a document shows its extracted fields and marked-as-advisory', async () => {
  vi.spyOn(client, 'getDocumentReviewQueue').mockResolvedValue([reviewItem()]);

  render(<DocumentReviewPage />);
  await userEvent.click(await screen.findByRole('button', { name: /dana reyes/i }));

  expect(await screen.findByText('monthly_amount')).toBeInTheDocument();
  expect(screen.getByText('1500.00')).toBeInTheDocument();
  expect(screen.getByText(/ai-generated · advisory only/i)).toBeInTheDocument();
});

test('an edit-then-confirm flow sends the edited value, not the original extraction', async () => {
  vi.spyOn(client, 'getDocumentReviewQueue').mockResolvedValue([reviewItem()]);
  const confirm = vi.spyOn(client, 'confirmDocument').mockResolvedValue(confirmedResponse());

  render(<DocumentReviewPage />);
  await userEvent.click(await screen.findByRole('button', { name: /dana reyes/i }));

  const amountField = await screen.findByLabelText(/monthly amount/i);
  await userEvent.clear(amountField);
  await userEvent.type(amountField, '1650.00');
  await userEvent.click(screen.getByRole('button', { name: /^confirm$/i }));

  expect(confirm).toHaveBeenCalledWith(
    'doc-1',
    expect.objectContaining({
      satisfiedVerificationIds: ['verification-1'],
      incomeRecords: [expect.objectContaining({ personId: 'person-1', monthlyAmount: '1650.00' })],
    }),
  );
  // Never the extraction's own original figure -- confirming must apply the worker's edit, not the AI's guess.
  expect(confirm).not.toHaveBeenCalledWith(
    'doc-1',
    expect.objectContaining({ incomeRecords: [expect.objectContaining({ monthlyAmount: '1500.00' })] }),
  );
});

test('unchecking a matched verification excludes it from the confirm request', async () => {
  vi.spyOn(client, 'getDocumentReviewQueue').mockResolvedValue([reviewItem()]);
  const confirm = vi.spyOn(client, 'confirmDocument').mockResolvedValue(confirmedResponse());

  render(<DocumentReviewPage />);
  await userEvent.click(await screen.findByRole('button', { name: /dana reyes/i }));
  await userEvent.click(await screen.findByLabelText(/satisfies outstanding verification/i));
  await userEvent.click(screen.getByRole('button', { name: /^confirm$/i }));

  expect(confirm).toHaveBeenCalledWith('doc-1', expect.objectContaining({ satisfiedVerificationIds: [] }));
});

test('a confirmed document leaves the queue', async () => {
  vi.spyOn(client, 'getDocumentReviewQueue').mockResolvedValue([reviewItem()]);
  vi.spyOn(client, 'confirmDocument').mockResolvedValue(confirmedResponse());

  render(<DocumentReviewPage />);
  await userEvent.click(await screen.findByRole('button', { name: /dana reyes/i }));
  await userEvent.click(screen.getByRole('button', { name: /^confirm$/i }));

  expect(await screen.findByText(/no documents are waiting for review/i)).toBeInTheDocument();
});

test('a failed confirm shows an inline error and keeps the document in the queue', async () => {
  vi.spyOn(client, 'getDocumentReviewQueue').mockResolvedValue([reviewItem()]);
  vi.spyOn(client, 'confirmDocument').mockRejectedValue(new Error('500'));

  render(<DocumentReviewPage />);
  await userEvent.click(await screen.findByRole('button', { name: /dana reyes/i }));
  await userEvent.click(screen.getByRole('button', { name: /^confirm$/i }));

  expect(await screen.findByRole('alert')).toHaveTextContent(/could not confirm/i);
  expect(screen.getByText('Dana Reyes')).toBeInTheDocument();
});

test('the page has no accessibility violations', async () => {
  vi.spyOn(client, 'getDocumentReviewQueue').mockResolvedValue([reviewItem()]);

  const { container } = render(<DocumentReviewPage />);
  await userEvent.click(await screen.findByRole('button', { name: /dana reyes/i }));
  await screen.findByText('monthly_amount');

  expect(await axe(container)).toHaveNoViolations();
});
