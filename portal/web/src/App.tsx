import { BrowserRouter, Navigate, NavLink, Route, Routes } from 'react-router-dom';
import { CanopicaAuthProvider, useIesAuth } from './auth/AuthContext';
import IntakePage from './pages/IntakePage';
import WorkerCasesPage from './pages/WorkerCasesPage';
import CaseDetailPage from './pages/CaseDetailPage';
import PolicyQaPage from './pages/PolicyQaPage';
import RuleAuthoringPage from './pages/RuleAuthoringPage';

type Role = 'CUSTOMER' | 'WORKER' | 'ADMIN';

// Where each role lands with no path of its own. ADMIN is deliberately not sent
// to /cases: an admin holds no caseload and /api/worker/** would refuse them.
const HOME_FOR: Record<Role, string> = {
  CUSTOMER: '/apply',
  WORKER: '/cases',
  ADMIN: '/rule-authoring',
};

function Nav({ role }: { role: Role }) {
  return (
    <nav aria-label="Main">
      {role === 'CUSTOMER' && <NavLink to="/apply">Apply</NavLink>}
      {role === 'CUSTOMER' && <NavLink to="/ask">Ask about policy</NavLink>}
      {role === 'WORKER' && <NavLink to="/cases">Cases</NavLink>}
      {role === 'ADMIN' && <NavLink to="/rule-authoring">Rule authoring</NavLink>}
    </nav>
  );
}

function AuthedAppShell({ role, signOut }: { role: Role; signOut: () => void }) {
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
          <Route path="/" element={<Navigate to={HOME_FOR[role]} replace />} />
          <Route path="/apply" element={<IntakePage />} />
          <Route path="/ask" element={<PolicyQaPage />} />
          <Route path="/cases" element={<WorkerCasesPage />} />
          <Route path="/cases/:programRequestId" element={<CaseDetailPage />} />
          <Route path="/rule-authoring" element={<RuleAuthoringPage />} />
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
