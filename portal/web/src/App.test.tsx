import { render, screen } from '@testing-library/react';

import App from './App';

test('renders the IES application shell', () => {
  render(<App />);
  expect(screen.getByRole('heading', { name: /IES/i })).toBeInTheDocument();
});
