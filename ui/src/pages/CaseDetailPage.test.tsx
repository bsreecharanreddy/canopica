import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { vi } from 'vitest';
import { axe } from 'vitest-axe';
import * as client from '../api/client';
import type { AuditEventResponse, CaseDetailResponse, DeterminationResponse } from '../api/types';
import CaseDetailPage from './CaseDetailPage';

const firstDetermination: DeterminationResponse = {
  determinationId: 'det-1',
  eligible: true,
  benefitAmount: '649.00',
  reasonCode: 'ELIGIBLE',
  policyParameterVersion: 'SNAP-FY2025',
  benefitMonth: '2025-06-01',
  asOfDate: '2025-06-15',
  decidedAt: '2025-06-15T12:00:00Z',
};

const caseDetail: CaseDetailResponse = {
  programRequestId: 'pr-1',
  applicationId: 'app-1',
  householdId: 'hh-1',
  householdHeadName: 'Dana Reyes',
  programCode: 'SNAP',
  status: 'SUBMITTED',
  requestedOn: '2025-06-01',
  determinations: [firstDetermination],
};

function renderAtCase() {
  return render(
    <MemoryRouter initialEntries={['/cases/pr-1']}>
      <Routes>
        <Route path="/cases/:programRequestId" element={<CaseDetailPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

test('shows the determination outcome, benefit amount, reason code, and policy parameter version', async () => {
  vi.spyOn(client, 'getCase').mockResolvedValue(caseDetail);
  vi.spyOn(client, 'getAuditTrail').mockResolvedValue([]);

  const { container } = renderAtCase();

  expect(await screen.findByText('Eligible')).toBeInTheDocument();
  expect(screen.getByText(/649\.00/)).toBeInTheDocument();
  expect(screen.getByText('ELIGIBLE')).toBeInTheDocument();
  expect(screen.getByText('SNAP-FY2025')).toBeInTheDocument();
  expect(await axe(container)).toHaveNoViolations();
});

test('running a determination calls the API and re-renders with the new result', async () => {
  vi.spyOn(client, 'getCase').mockResolvedValue(caseDetail);
  vi.spyOn(client, 'getAuditTrail').mockResolvedValue([]);
  const run = vi.spyOn(client, 'runDetermination').mockResolvedValue({
    ...firstDetermination,
    determinationId: 'det-2',
    benefitAmount: '700.00',
  });

  const { container } = renderAtCase();
  await screen.findByText('Eligible');

  await userEvent.click(screen.getByRole('button', { name: /run determination/i }));

  await waitFor(() => expect(run).toHaveBeenCalledWith('pr-1', expect.any(Object)));
  expect(await screen.findByText(/700\.00/)).toBeInTheDocument();
  // The original determination is still there -- history is appended to, not replaced.
  expect(screen.getByText(/649\.00/)).toBeInTheDocument();
  expect(await axe(container)).toHaveNoViolations();
});

test('running a determination for a benefit month that already has one shows a validation message and does not call the API', async () => {
  // jsdom's <input type="date"> doesn't sync a fireEvent.change back into React's
  // controlled state (a known jsdom limitation, confirmed against this exact
  // component), so this test can't drive the collision through the date field.
  // It instead matches the fixture to CaseDetailPage's own default benefit-month
  // calculation (first of the current month) -- the same collision a worker would
  // hit by just clicking "Run determination" without touching the date at all.
  const now = new Date();
  const defaultBenefitMonth = new Date(now.getFullYear(), now.getMonth(), 1).toISOString().slice(0, 10);
  const caseWithCurrentMonthDetermination: CaseDetailResponse = {
    ...caseDetail,
    determinations: [{ ...firstDetermination, benefitMonth: defaultBenefitMonth }],
  };
  vi.spyOn(client, 'getCase').mockResolvedValue(caseWithCurrentMonthDetermination);
  vi.spyOn(client, 'getAuditTrail').mockResolvedValue([]);
  // Nothing in this file resets mocks between tests, so a fresh spy on an
  // already-spied method inherits the previous test's call history -- clear it so
  // this test's own assertion isn't polluted by the prior test's real call.
  const run = vi.spyOn(client, 'runDetermination');
  run.mockClear();

  renderAtCase();
  await screen.findByText('Eligible');

  await userEvent.click(screen.getByRole('button', { name: /run determination/i }));

  expect(await screen.findByRole('alert')).toHaveTextContent(/already.*determination/i);
  expect(run).not.toHaveBeenCalled();
});

test('the trace panel lists each DMN decision name and value in evaluation order once expanded', async () => {
  vi.spyOn(client, 'getCase').mockResolvedValue(caseDetail);
  vi.spyOn(client, 'getAuditTrail').mockResolvedValue([]);
  vi.spyOn(client, 'getTrace').mockResolvedValue({
    inputSnapshot: {},
    decisionResults: { 'Gross Income Test': 'PASS', 'Net Income': '1200' },
    dmnModelHash: 'abc123',
    policyParameterVersion: 'SNAP-FY2025',
  });

  const { container } = renderAtCase();
  await screen.findByText('Eligible');

  await userEvent.click(screen.getByText(/dmn evaluation trace/i));

  const list = await screen.findByRole('list', { name: /dmn decisions/i });
  expect(list).toHaveTextContent('Gross Income Test');
  expect(list).toHaveTextContent('PASS');
  expect(list).toHaveTextContent('Net Income');
  expect(list).toHaveTextContent('1200');
  expect(await axe(container)).toHaveNoViolations();
});

test('fetches and renders the audit trail below the determination history', async () => {
  vi.spyOn(client, 'getCase').mockResolvedValue(caseDetail);
  const events: AuditEventResponse[] = [
    {
      eventType: 'APPLICATION_SUBMITTED',
      occurredAt: '2025-06-01T09:00:00Z',
      actorId: 'citizen-123',
      actorType: 'HUMAN',
      payload: {},
    },
    {
      eventType: 'DETERMINATION_MADE',
      occurredAt: '2025-06-15T12:00:00Z',
      actorId: 'SYSTEM',
      actorType: 'SYSTEM',
      payload: { benefitAmount: '649.00' },
    },
  ];
  vi.spyOn(client, 'getAuditTrail').mockResolvedValue(events);

  const { container } = renderAtCase();
  await screen.findByText('Eligible');

  expect(await screen.findByText('APPLICATION_SUBMITTED')).toBeInTheDocument();
  expect(screen.getByText('DETERMINATION_MADE')).toBeInTheDocument();
  expect(screen.getByText('HUMAN')).toBeInTheDocument();
  expect(screen.getByText('SYSTEM')).toBeInTheDocument();
  expect(await axe(container)).toHaveNoViolations();
});
