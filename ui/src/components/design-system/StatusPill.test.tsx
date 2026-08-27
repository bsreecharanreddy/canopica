import { render, screen } from '@testing-library/react';
import { StatusPill } from './StatusPill';

test.each([
  ['affirmed', 'Eligible'],
  ['exception', 'Not eligible'],
  ['pending', 'Awaiting review'],
  ['neutral', 'Draft'],
] as const)('renders %s tone with its own text', (tone, text) => {
  render(<StatusPill tone={tone}>{text}</StatusPill>);
  expect(screen.getByText(text)).toBeInTheDocument();
});
