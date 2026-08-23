import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { axe } from 'vitest-axe';
import * as client from '../api/client';
import IntakePage from './IntakePage';

test('submits a household and shows the confirmation with its request id', async () => {
  const submit = vi.spyOn(client, 'submitApplication').mockResolvedValue({
    applicationId: 'a-1',
    programRequestId: 'pr-1',
  });

  const { container } = render(<IntakePage />);
  await userEvent.type(screen.getByLabelText(/first name/i), 'Dana');
  await userEvent.type(screen.getByLabelText(/last name/i), 'Reyes');
  await userEvent.type(screen.getByLabelText(/date of birth/i), '1990-04-02');
  await userEvent.type(screen.getByLabelText(/monthly earned income/i), '1500');
  await userEvent.type(screen.getByLabelText(/monthly rent or mortgage/i), '800');
  await userEvent.click(screen.getByRole('button', { name: /submit application/i }));

  await waitFor(() => expect(submit).toHaveBeenCalledOnce());
  expect(await screen.findByText(/pr-1/)).toBeInTheDocument();
  expect(await axe(container)).toHaveNoViolations();
});

test('shows a field-level error when the API rejects the submission', async () => {
  vi.spyOn(client, 'submitApplication').mockRejectedValue(
    new client.ApiValidationError([{ field: 'members', message: 'must not be empty' }]),
  );

  const { container } = render(<IntakePage />);
  await userEvent.click(screen.getByRole('button', { name: /submit application/i }));

  expect(await screen.findByRole('alert')).toHaveTextContent(/must not be empty/i);
  expect(await axe(container)).toHaveNoViolations();
});
