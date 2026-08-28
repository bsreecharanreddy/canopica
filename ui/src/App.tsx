import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { CanopicaAuthProvider, useIesAuth, type Role } from './auth/AuthContext';
import { NavRail } from './components/design-system/NavRail';
import { TopUtilityBar } from './components/design-system/TopUtilityBar';
import { PageChromeProvider } from './components/design-system/PageChrome';
import IntakePage from './pages/IntakePage';
import WorkerCasesPage from './pages/WorkerCasesPage';
import CaseDetailPage from './pages/CaseDetailPage';
import PolicyQaPage from './pages/PolicyQaPage';
import RuleAuthoringPage from './pages/RuleAuthoringPage';
import DashboardPage from './pages/DashboardPage';
import DocumentReviewPage from './pages/DocumentReviewPage';

// Where each role lands with no path of its own. ADMIN is deliberately not sent
// to /cases: an admin holds no caseload and /api/worker/** would refuse them.
const HOME_FOR: Record<Role, string> = {
  CUSTOMER: '/apply',
  WORKER: '/dashboard',
  ADMIN: '/rule-authoring',
};

function AuthedAppShell({ role, signOut }: { role: Role; signOut: () => void }) {
  return (
    <PageChromeProvider>
      <div className="flex min-h-screen">
        <NavRail role={role} onSignOut={signOut} />
        <div className="flex flex-1 flex-col">
          <TopUtilityBar />
          <main className="flex-1 bg-background p-8">
            <div className="mx-auto max-w-[1640px]">
              <Routes>
                <Route path="/" element={<Navigate to={HOME_FOR[role]} replace />} />
                <Route path="/apply" element={<IntakePage />} />
                <Route path="/ask" element={<PolicyQaPage />} />
                <Route path="/dashboard" element={<DashboardPage />} />
                <Route path="/cases" element={<WorkerCasesPage />} />
                <Route path="/cases/:programRequestId" element={<CaseDetailPage />} />
                <Route path="/documents/review" element={<DocumentReviewPage />} />
                <Route path="/rule-authoring" element={<RuleAuthoringPage />} />
              </Routes>
            </div>
          </main>
        </div>
      </div>
    </PageChromeProvider>
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
