import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { vi } from 'vitest';
import { axe } from 'vitest-axe';
import * as client from '../api/client';
import WorkerCasesPage from './WorkerCasesPage';

test('renders an accessible table of cases, with column headers and a link per row', async () => {
  vi.spyOn(client, 'listCases').mockResolvedValue([
    {
      programRequestId: 'pr-1',
      householdHeadName: 'Dana Reyes',
      status: 'SUBMITTED',
      submittedAt: '2025-06-01T12:00:00Z',
      latestDetermination: { eligible: true, benefitAmount: '649.00', decidedAt: '2025-06-15T12:00:00Z' },
    },
  ]);

  const { container } = render(
    <MemoryRouter>
      <WorkerCasesPage />
    </MemoryRouter>,
  );

  expect(await screen.findByRole('table', { name: /cases/i })).toBeInTheDocument();
  expect(screen.getByRole('columnheader', { name: /household head/i })).toBeInTheDocument();
  expect(screen.getByRole('columnheader', { name: /status/i })).toBeInTheDocument();

  const link = screen.getByRole('link', { name: /dana reyes/i });
  expect(link).toHaveAttribute('href', '/cases/pr-1');
  expect(await axe(container)).toHaveNoViolations();
});
