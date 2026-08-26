import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { axe } from 'vitest-axe';
import * as client from '../api/client';
import type { QaAnswer } from '../api/types';
import PolicyQaPage from './PolicyQaPage';

test('asking a question renders the answer and its citations', async () => {
  const answer: QaAnswer = {
    answer: 'The gross income test compares household income against a limit.',
    citations: ['273.9(a)'],
    abstained: false,
  };
  const ask = vi.spyOn(client, 'askPolicyQuestion').mockResolvedValue(answer);

  const { container } = render(<PolicyQaPage />);
  await userEvent.type(screen.getByLabelText(/your question/i), 'What is the gross income test?');
  await userEvent.click(screen.getByRole('button', { name: /^ask$/i }));

  expect(ask).toHaveBeenCalledWith('What is the gross income test?');
  expect(await screen.findByText(/gross income test compares/i)).toBeInTheDocument();
  expect(screen.getByText('273.9(a)')).toBeInTheDocument();
  expect(await axe(container)).toHaveNoViolations();
});

test('an abstained answer is rendered distinctly, with no citations list', async () => {
  const answer: QaAnswer = {
    answer: 'insufficient information in the policy corpus to answer this',
    citations: [],
    abstained: true,
  };
  vi.spyOn(client, 'askPolicyQuestion').mockResolvedValue(answer);

  render(<PolicyQaPage />);
  await userEvent.type(screen.getByLabelText(/your question/i), 'How do I bake a cake?');
  await userEvent.click(screen.getByRole('button', { name: /^ask$/i }));

  const panel = await screen.findByText(/insufficient information/i);
  expect(panel).toHaveClass('qa-abstention');
  expect(screen.queryByText('Citations')).not.toBeInTheDocument();
});

test('explaining a denial calls the API with the entered determination id', async () => {
  const answer: QaAnswer = {
    answer: 'Your gross income exceeded the limit for your household size.',
    citations: ['273.9(a)'],
    abstained: false,
  };
  const explain = vi.spyOn(client, 'askWhyWasIDenied').mockResolvedValue(answer);

  render(<PolicyQaPage />);
  await userEvent.type(screen.getByLabelText(/determination id/i), 'det-123');
  await userEvent.click(screen.getByRole('button', { name: /explain this determination/i }));

  expect(explain).toHaveBeenCalledWith('det-123');
  expect(await screen.findByText(/gross income exceeded/i)).toBeInTheDocument();
});

test('a failed request shows an inline error rather than a silent no-op', async () => {
  vi.spyOn(client, 'askPolicyQuestion').mockRejectedValue(new Error('network error'));

  render(<PolicyQaPage />);
  await userEvent.type(screen.getByLabelText(/your question/i), 'What is the net income test?');
  await userEvent.click(screen.getByRole('button', { name: /^ask$/i }));

  expect(await screen.findByRole('alert')).toHaveTextContent(/could not get an answer/i);
});
