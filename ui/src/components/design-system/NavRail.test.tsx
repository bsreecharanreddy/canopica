import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { NavRail } from './NavRail';

test('CUSTOMER sees Apply and Ask about policy links only', () => {
  render(
    <MemoryRouter>
      {/* oxlint-disable-next-line jsx-a11y/aria-role -- `role` here is NavRail's own prop, not the DOM aria attribute; oxlint doesn't distinguish custom-component props from intrinsic elements for this rule */}
      <NavRail role="CUSTOMER" />
    </MemoryRouter>,
  );
  expect(screen.getByRole('link', { name: 'Apply' })).toBeInTheDocument();
  expect(screen.getByRole('link', { name: 'Ask about policy' })).toBeInTheDocument();
  expect(screen.queryByRole('link', { name: 'Cases' })).not.toBeInTheDocument();
});

test('WORKER sees only the Cases link', () => {
  render(
    <MemoryRouter>
      {/* oxlint-disable-next-line jsx-a11y/aria-role -- see the CUSTOMER test above */}
      <NavRail role="WORKER" />
    </MemoryRouter>,
  );
  expect(screen.getByRole('link', { name: 'Cases' })).toBeInTheDocument();
  expect(screen.queryByRole('link', { name: 'Apply' })).not.toBeInTheDocument();
});

test('ADMIN sees only the Rule authoring link', () => {
  render(
    <MemoryRouter>
      {/* oxlint-disable-next-line jsx-a11y/aria-role -- see the CUSTOMER test above */}
      <NavRail role="ADMIN" />
    </MemoryRouter>,
  );
  expect(screen.getByRole('link', { name: 'Rule authoring' })).toBeInTheDocument();
  expect(screen.queryByRole('link', { name: 'Cases' })).not.toBeInTheDocument();
});
