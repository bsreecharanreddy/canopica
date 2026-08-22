import type { AuthProviderProps } from 'react-oidc-context';

export type Realm = 'citizen' | 'worker';

const REALM_CHOICE_KEY = 'canopica-realm-choice';

// Keycloak's browser-facing origin: infra/docker-compose.yml publishes it on the host at 8081, the same
// port whether portal-web itself is served by Vite's dev server or nginx inside Compose -- the browser
// always reaches Keycloak directly, never through portal-api's proxy (that's /api/ only, see
// infra's nginx.conf note in docs/STATUS.md's Task 12 row).
const KEYCLOAK_BASE_URL = 'http://localhost:8081';

const REALM_CONFIG: Record<Realm, { authority: string; client_id: string }> = {
  citizen: {
    authority: `${KEYCLOAK_BASE_URL}/realms/canopica-citizens`,
    client_id: 'canopica-portal-web-citizen',
  },
  worker: {
    authority: `${KEYCLOAK_BASE_URL}/realms/canopica-workers`,
    client_id: 'canopica-portal-web',
  },
};

export function authConfigFor(realm: Realm): AuthProviderProps {
  return {
    ...REALM_CONFIG[realm],
    redirect_uri: window.location.origin,
    // Keycloak's own /protocol/openid-connect/token response already includes the realm roles inside the
    // access token itself (see SecurityConfig.realmRoleAuthorities on the server) -- no extra scope needed.
    scope: 'openid profile email',
    onSigninCallback: () => {
      // Strips the ?code=&state=... query string Keycloak appends on redirect back, so a page refresh
      // doesn't try to re-process a spent authorization code.
      window.history.replaceState({}, document.title, window.location.pathname);
    },
  };
}

// Persisted across the full-page redirect to Keycloak and back -- sessionStorage (not React state)
// because the whole app remounts fresh once the browser navigates back from Keycloak.
export function storeRealmChoice(realm: Realm): void {
  try {
    window.sessionStorage.setItem(REALM_CHOICE_KEY, realm);
  } catch {
    // Best-effort only; readRealmChoice() below handles the missing case.
  }
}

export function readRealmChoice(): Realm | null {
  try {
    const stored = window.sessionStorage.getItem(REALM_CHOICE_KEY);
    return stored === 'citizen' || stored === 'worker' ? stored : null;
  } catch {
    return null;
  }
}

export function clearRealmChoice(): void {
  try {
    window.sessionStorage.removeItem(REALM_CHOICE_KEY);
  } catch {
    // Nothing to clean up if storage was never reachable.
  }
}
