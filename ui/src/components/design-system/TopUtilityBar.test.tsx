import { afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import i18n from '@/i18n/config';
import { NavRail } from './NavRail';
import { TopUtilityBar } from './TopUtilityBar';
import { PageChromeProvider } from './PageChrome';

afterEach(async () => {
  await i18n.changeLanguage('en');
});

test('switching the language selector re-renders already-mounted copy in the new language', async () => {
  render(
    <PageChromeProvider>
      <MemoryRouter>
        <TopUtilityBar />
        {/* oxlint-disable-next-line jsx-a11y/aria-role -- `role` here is NavRail's own prop, not the DOM aria attribute */}
        <NavRail role="WORKER" onSignOut={() => {}} />
      </MemoryRouter>
    </PageChromeProvider>,
  );

  expect(screen.getByRole('link', { name: 'Dashboard' })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Sign out' })).toBeInTheDocument();

  await userEvent.selectOptions(screen.getByRole('combobox', { name: /language/i }), 'es');

  expect(await screen.findByRole('link', { name: 'Panel' })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Cerrar sesión' })).toBeInTheDocument();
  expect(screen.queryByRole('link', { name: 'Dashboard' })).not.toBeInTheDocument();
});
