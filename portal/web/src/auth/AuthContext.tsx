import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from 'react';
import { AuthProvider, useAuth } from 'react-oidc-context';
import { setAccessToken } from '../api/client';
import { authConfigFor, clearRealmChoice, readRealmChoice, storeRealmChoice, type Realm } from './oidc-config';

type Role = 'CUSTOMER' | 'WORKER' | 'ADMIN';

/**
 * Reads Keycloak's `realm_access.roles` out of the access token, unverified.
 *
 * <p>Unverified is correct here and not a shortcut: this drives which links the UI renders, nothing more.
 * Every one of those routes is enforced server-side against a signature-checked token (SecurityConfig's
 * `/api/policy/**` is ADMIN-only), so the worst a tampered token achieves locally is showing someone a link
 * that 403s. Verifying a signature in the browser would prove nothing extra, since the browser holds the
 * token either way.
 *
 * <p>Realm roles aren't in the ID token by default, so `auth.user.profile` can't answer this -- the access
 * token is where Keycloak actually puts them.
 */
function realmRolesOf(accessToken: string | undefined): string[] {
  if (!accessToken) return [];
  try {
    const payload = accessToken.split('.')[1];
    const json = atob(payload.replace(/-/g, '+').replace(/_/g, '/'));
    const claims = JSON.parse(json) as { realm_access?: { roles?: string[] } };
    return claims.realm_access?.roles ?? [];
  } catch {
    // A malformed token is a sign-in problem, surfaced by react-oidc-context itself. Here it just means
    // "no elevated links", which is the safe direction to fail in.
    return [];
  }
}

function roleFor(realm: Realm, accessToken: string | undefined): Role {
  if (realm !== 'worker') return 'CUSTOMER';
  // ADMIN is a distinct realm role, not a superset of WORKER -- an admin holds no caseload and would be
  // refused by /api/worker/**, so the nav must not offer it to them.
  return realmRolesOf(accessToken).includes('ADMIN') ? 'ADMIN' : 'WORKER';
}

type CanopicaAuthValue =
  | { status: 'choosing'; chooseRealm: (realm: Realm) => void }
  | { status: 'loading' }
  | { status: 'error'; message: string; signOut: () => void }
  | { status: 'authenticated'; role: Role; signOut: () => void };

const CanopicaAuthContext = createContext<CanopicaAuthValue>({ status: 'loading' });

export function useIesAuth(): CanopicaAuthValue {
  return useContext(CanopicaAuthContext);
}

/** Keeps api/client.ts's plain-function calls in sync with react-oidc-context's own token state. */
function AuthBridge({ realm, onSignedOut, children }: { realm: Realm; onSignedOut: () => void; children: ReactNode }) {
  const auth = useAuth();
  // Guards the auto-redirect below to once per mount of this component, not once per render where
  // isAuthenticated happens to be false -- found by actually clicking "Sign out" in a browser: removeUser()
  // resolves asynchronously, so there's a real window where isAuthenticated is false but this component
  // hasn't unmounted yet (that only happens once CanopicaAuthProvider's own realm state resets, a separate,
  // later render). Without this guard, that window was enough to silently re-trigger signinRedirect() --
  // invisible to the user only because Keycloak's own SSO session was still alive, so it round-tripped and
  // returned immediately rather than showing a login form, leaving a stale ?code=...&state=... in the URL
  // and never actually landing back on the realm-choice screen.
  const hasTriedSignin = useRef(false);

  useEffect(() => {
    setAccessToken(auth.user?.access_token ?? null);
    return () => setAccessToken(null);
  }, [auth.user?.access_token]);

  // Auto-redirect to Keycloak the moment a realm is chosen and there's no existing session -- this app has
  // no separate "click to sign in" step beyond the realm choice itself.
  useEffect(() => {
    if (
      !auth.isLoading &&
      !auth.isAuthenticated &&
      !auth.activeNavigator &&
      !auth.error &&
      !hasTriedSignin.current
    ) {
      hasTriedSignin.current = true;
      auth.signinRedirect();
    }
  }, [auth, auth.isLoading, auth.isAuthenticated, auth.activeNavigator, auth.error]);

  function signOut() {
    auth.removeUser();
    clearRealmChoice();
    onSignedOut();
  }

  let value: CanopicaAuthValue;
  if (auth.error) {
    value = { status: 'error', message: auth.error.message, signOut };
  } else if (auth.isAuthenticated) {
    value = { status: 'authenticated', role: roleFor(realm, auth.user?.access_token), signOut };
  } else {
    value = { status: 'loading' };
  }

  return <CanopicaAuthContext.Provider value={value}>{children}</CanopicaAuthContext.Provider>;
}

function RealmChooser({ onChoose }: { onChoose: (realm: Realm) => void }) {
  return (
    <div>
      <h1>Canopica</h1>
      <p>Applying for benefits, or a caseworker signing in?</p>
      <button type="button" onClick={() => onChoose('citizen')}>
        Apply for SNAP
      </button>
      <button type="button" onClick={() => onChoose('worker')}>
        Caseworker sign in
      </button>
    </div>
  );
}

export function CanopicaAuthProvider({ children }: { children: ReactNode }) {
  const [realm, setRealm] = useState<Realm | null>(() => readRealmChoice());

  function chooseRealm(next: Realm) {
    storeRealmChoice(next);
    setRealm(next);
  }

  if (realm === null) {
    return (
      <CanopicaAuthContext.Provider value={{ status: 'choosing', chooseRealm }}>
        <RealmChooser onChoose={chooseRealm} />
      </CanopicaAuthContext.Provider>
    );
  }

  return (
    <AuthProvider {...authConfigFor(realm)}>
      <AuthBridge realm={realm} onSignedOut={() => setRealm(null)}>
        {children}
      </AuthBridge>
    </AuthProvider>
  );
}
