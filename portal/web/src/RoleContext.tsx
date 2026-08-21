import { createContext, useContext, useMemo, useState, type ReactNode } from 'react';
import { getRole, setRole as setClientRole, type Role } from './api/client';

type RoleContextValue = {
  role: Role;
  setRole: (role: Role) => void;
};

// A default value (not just `null!`) so a component using useRole() renders sensibly even in a test
// that doesn't wrap it in <RoleProvider> -- Phase 1a has no login, CUSTOMER is the sensible default.
const RoleContext = createContext<RoleContextValue>({
  role: 'CUSTOMER',
  setRole: () => {},
});

export function RoleProvider({ children }: { children: ReactNode }) {
  const [role, setRoleState] = useState<Role>(getRole());

  const value = useMemo<RoleContextValue>(
    () => ({
      role,
      setRole: (next: Role) => {
        setClientRole(next);
        setRoleState(next);
      },
    }),
    [role],
  );

  return <RoleContext.Provider value={value}>{children}</RoleContext.Provider>;
}

export function useRole(): RoleContextValue {
  return useContext(RoleContext);
}
