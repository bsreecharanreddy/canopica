import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { axe } from 'vitest-axe';
import * as client from '../api/client';
import type { SopAnswer } from '../api/types';
import SopCopilotPage from './SopCopilotPage';

test('asking a question renders the answer and its citations', async () => {
  const answer: SopAnswer = {
    answer: 'Expedited cases must be decided within 7 days.',
    citations: ['new_application -- Expedited service screening'],
    abstained: false,
  };
  const ask = vi.spyOn(client, 'askSopCopilot').mockResolvedValue(answer);

  const { container } = render(<SopCopilotPage />);
  await userEvent.type(
    screen.getByLabelText(/your question/i),
    'How fast must an expedited case be decided?',
  );
  await userEvent.click(screen.getByRole('button', { name: /^ask$/i }));

  expect(ask).toHaveBeenCalledWith('How fast must an expedited case be decided?');
  expect(await screen.findByText(/decided within 7 days/i)).toBeInTheDocument();
  expect(screen.getByText('new_application -- Expedited service screening')).toBeInTheDocument();
  expect(await axe(container)).toHaveNoViolations();
});

test('an abstained answer is rendered distinctly, with no citations list', async () => {
  const answer: SopAnswer = {
    answer: 'insufficient information in the SOP corpus to answer this',
    citations: [],
    abstained: true,
  };
  vi.spyOn(client, 'askSopCopilot').mockResolvedValue(answer);

  render(<SopCopilotPage />);
  await userEvent.type(screen.getByLabelText(/your question/i), 'How do I bake a cake?');
  await userEvent.click(screen.getByRole('button', { name: /^ask$/i }));

  expect(await screen.findByText(/insufficient information/i)).toBeInTheDocument();
  expect(screen.queryByText('Citations')).not.toBeInTheDocument();
});

test('a failed request shows an inline error rather than a silent no-op', async () => {
  vi.spyOn(client, 'askSopCopilot').mockRejectedValue(new Error('500'));

  render(<SopCopilotPage />);
  await userEvent.type(screen.getByLabelText(/your question/i), 'A question');
  await userEvent.click(screen.getByRole('button', { name: /^ask$/i }));

  expect(await screen.findByRole('alert')).toHaveTextContent(/could not get an answer/i);
});
