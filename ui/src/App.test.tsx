import { render, screen } from '@testing-library/react';

import App from './App';

test('renders the Canopica application shell', () => {
  render(<App />);
  expect(screen.getByRole('heading', { name: /Canopica/i })).toBeInTheDocument();
});
