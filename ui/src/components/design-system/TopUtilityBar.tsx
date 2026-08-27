import type { Role } from '@/auth/AuthContext';
import { Button } from '@/components/ui/button';

const ROLE_LABEL: Record<Role, string> = {
  CUSTOMER: 'Applicant',
  WORKER: 'Caseworker',
  ADMIN: 'Administrator',
};

export function TopUtilityBar({ role, onSignOut }: { role: Role; onSignOut: () => void }) {
  return (
    <div className="sticky top-0 z-20 flex items-center justify-end gap-4 border-b border-border bg-card/90 px-6 py-3 backdrop-blur-sm">
      <span className="text-sm text-muted-foreground">Signed in as {ROLE_LABEL[role]}</span>
      <Button variant="outline" size="sm" onClick={onSignOut}>
        Sign out
      </Button>
    </div>
  );
}
