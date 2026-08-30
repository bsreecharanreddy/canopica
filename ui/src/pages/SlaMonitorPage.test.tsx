import { render, screen } from '@testing-library/react';
import { vi } from 'vitest';
import { axe } from 'vitest-axe';
import * as client from '../api/client';
import type { AtRiskCaseItem } from '../api/types';
import SlaMonitorPage from './SlaMonitorPage';

function atRiskCase(overrides: Partial<AtRiskCaseItem> = {}): AtRiskCaseItem {
  return {
    programRequestId: 'pr-1',
    householdHeadName: 'Dana Reyes',
    requestedOn: '2026-08-01',
    isExpedited: false,
    daysRemaining: 5,
    stallReason: 'Awaiting INCOME verification, due in 5 days, last worker action 6 days ago.',
    stallReasonGeneratedAt: '2026-08-30T06:00:00Z',
    ...overrides,
  };
}

test('the queue lists an at-risk case by household head name', async () => {
  vi.spyOn(client, 'getAtRiskQueue').mockResolvedValue([atRiskCase()]);

  render(<SlaMonitorPage />);

  expect(await screen.findByText('Dana Reyes')).toBeInTheDocument();
});

test('an empty queue says so rather than showing a blank page', async () => {
  vi.spyOn(client, 'getAtRiskQueue').mockResolvedValue([]);

  render(<SlaMonitorPage />);

  expect(await screen.findByText(/no cases are currently at risk/i)).toBeInTheDocument();
});

test('a case with a generated stall reason shows it marked advisory', async () => {
  vi.spyOn(client, 'getAtRiskQueue').mockResolvedValue([atRiskCase()]);

  render(<SlaMonitorPage />);

  expect(await screen.findByText(/awaiting income verification/i)).toBeInTheDocument();
});

test('a case with no stall reason yet says so', async () => {
  vi.spyOn(client, 'getAtRiskQueue').mockResolvedValue(
    [atRiskCase({ stallReason: null, stallReasonGeneratedAt: null })],
  );

  render(<SlaMonitorPage />);

  expect(await screen.findByText(/no stall reason generated yet/i)).toBeInTheDocument();
});

test('an overdue case shows a days-overdue label, not a negative days-remaining one', async () => {
  vi.spyOn(client, 'getAtRiskQueue').mockResolvedValue([atRiskCase({ daysRemaining: -3 })]);

  render(<SlaMonitorPage />);

  expect(await screen.findByText(/3 days overdue/i)).toBeInTheDocument();
});

test('an expedited case is labeled as such', async () => {
  vi.spyOn(client, 'getAtRiskQueue').mockResolvedValue([atRiskCase({ isExpedited: true })]);

  render(<SlaMonitorPage />);

  expect(await screen.findByText('Expedited')).toBeInTheDocument();
});

test('a load failure shows an inline error', async () => {
  vi.spyOn(client, 'getAtRiskQueue').mockRejectedValue(new Error('500'));

  render(<SlaMonitorPage />);

  expect(await screen.findByRole('alert')).toHaveTextContent(/could not load/i);
});

test('the page has no accessibility violations', async () => {
  vi.spyOn(client, 'getAtRiskQueue').mockResolvedValue([atRiskCase()]);

  const { container } = render(<SlaMonitorPage />);
  await screen.findByText('Dana Reyes');

  expect(await axe(container)).toHaveNoViolations();
});
