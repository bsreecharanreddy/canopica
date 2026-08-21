import { BrowserRouter, Navigate, NavLink, Route, Routes } from 'react-router-dom';
import { RoleProvider, useRole } from './RoleContext';
import IntakePage from './pages/IntakePage';
import WorkerCasesPage from './pages/WorkerCasesPage';
import CaseDetailPage from './pages/CaseDetailPage';

/**
 * Phase 1a has no login (roles are hardcoded server-side too, see
 * `ies.portal.config.HardcodedRoleFilter`) -- this switch stands in for it, the same simplification on
 * the client that the server already makes.
 */
function RoleSwitch() {
  const { role, setRole } = useRole();
  return (
    <fieldset>
      <legend>Viewing as</legend>
      <label htmlFor="role-customer">
        <input
          id="role-customer"
          type="radio"
          name="role"
          value="CUSTOMER"
          checked={role === 'CUSTOMER'}
          onChange={() => setRole('CUSTOMER')}
        />
        Customer
      </label>
      <label htmlFor="role-worker">
        <input
          id="role-worker"
          type="radio"
          name="role"
          value="WORKER"
          checked={role === 'WORKER'}
          onChange={() => setRole('WORKER')}
        />
        Worker
      </label>
    </fieldset>
  );
}

function Nav() {
  const { role } = useRole();
  return (
    <nav aria-label="Main">
      {role === 'CUSTOMER' && <NavLink to="/apply">Apply</NavLink>}
      {role === 'WORKER' && <NavLink to="/cases">Cases</NavLink>}
    </nav>
  );
}

function AppShell() {
  const { role } = useRole();
  return (
    <>
      <header>
        <h1>IES</h1>
        <RoleSwitch />
        <Nav />
      </header>
      <main>
        <Routes>
          <Route path="/" element={<Navigate to={role === 'WORKER' ? '/cases' : '/apply'} replace />} />
          <Route path="/apply" element={<IntakePage />} />
          <Route path="/cases" element={<WorkerCasesPage />} />
          <Route path="/cases/:programRequestId" element={<CaseDetailPage />} />
        </Routes>
      </main>
    </>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <RoleProvider>
        <AppShell />
      </RoleProvider>
    </BrowserRouter>
  );
}
