import { BrowserRouter, Navigate, NavLink, Route, Routes } from 'react-router-dom';
import { CanopicaAuthProvider, useIesAuth } from './auth/AuthContext';
import IntakePage from './pages/IntakePage';
import WorkerCasesPage from './pages/WorkerCasesPage';
import CaseDetailPage from './pages/CaseDetailPage';

function Nav({ role }: { role: 'CUSTOMER' | 'WORKER' }) {
  return (
    <nav aria-label="Main">
      {role === 'CUSTOMER' && <NavLink to="/apply">Apply</NavLink>}
      {role === 'WORKER' && <NavLink to="/cases">Cases</NavLink>}
    </nav>
  );
}

function AuthedAppShell({ role, signOut }: { role: 'CUSTOMER' | 'WORKER'; signOut: () => void }) {
  return (
    <>
      <header>
        <h1>Canopica</h1>
        <Nav role={role} />
        <button type="button" onClick={signOut}>
          Sign out
        </button>
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

function AppShell() {
  const auth = useIesAuth();

  // 'choosing' never actually reaches here -- CanopicaAuthProvider renders its own realm-choice screen instead
  // of children in that state. Handled anyway so this function's return type stays exhaustive.
  switch (auth.status) {
    case 'authenticated':
      return <AuthedAppShell role={auth.role} signOut={auth.signOut} />;
    case 'error':
      return (
        <div role="alert">
          <p>Sign-in failed: {auth.message}</p>
          <button type="button" onClick={auth.signOut}>
            Try again
          </button>
        </div>
      );
    case 'loading':
    case 'choosing':
    default:
      return <p>Signing in…</p>;
  }
}

export default function App() {
  return (
    <BrowserRouter>
      <CanopicaAuthProvider>
        <AppShell />
      </CanopicaAuthProvider>
    </BrowserRouter>
  );
}
