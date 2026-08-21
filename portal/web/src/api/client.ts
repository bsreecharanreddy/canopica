import type {
  CaseDetailResponse,
  CaseSummaryResponse,
  DetermineRequest,
  DeterminationResponse,
  IntakeRequest,
  IntakeResponse,
  TraceResponse,
  ApiFieldError,
} from './types';

export type Role = 'CUSTOMER' | 'WORKER';

const ROLE_STORAGE_KEY = 'ies-role';

// localStorage can be unavailable (SSR, some jsdom/Node combinations, a browser with site data
// blocked) even where `window` itself exists -- every access below is guarded, never trusted.
function readStoredRole(): Role {
  try {
    return window.localStorage.getItem(ROLE_STORAGE_KEY) === 'WORKER' ? 'WORKER' : 'CUSTOMER';
  } catch {
    return 'CUSTOMER';
  }
}

let currentRole: Role = readStoredRole();

export function getRole(): Role {
  return currentRole;
}

export function setRole(role: Role): void {
  currentRole = role;
  try {
    window.localStorage.setItem(ROLE_STORAGE_KEY, role);
  } catch {
    // Best-effort persistence only -- the in-memory currentRole above is still updated.
  }
}

/** Thrown for a 400 response; {@link errors} mirrors ApiExceptionHandler's `{errors: [{field, message}]}` body. */
export class ApiValidationError extends Error {
  errors: ApiFieldError[];

  constructor(errors: ApiFieldError[]) {
    super(errors.map((e) => e.message).join('; ') || 'validation failed');
    this.name = 'ApiValidationError';
    this.errors = errors;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      'X-IES-Role': currentRole,
      ...init?.headers,
    },
  });

  if (!response.ok) {
    if (response.status === 400) {
      const body = (await response.json()) as { errors?: ApiFieldError[] };
      throw new ApiValidationError(body.errors ?? []);
    }
    throw new Error(`${init?.method ?? 'GET'} ${path} failed with status ${response.status}`);
  }

  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

export function submitApplication(payload: IntakeRequest): Promise<IntakeResponse> {
  return request<IntakeResponse>('/api/applications', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function listCases(): Promise<CaseSummaryResponse[]> {
  return request<CaseSummaryResponse[]>('/api/worker/cases');
}

export function getCase(programRequestId: string): Promise<CaseDetailResponse> {
  return request<CaseDetailResponse>(`/api/program-requests/${programRequestId}`);
}

export function runDetermination(
  programRequestId: string,
  payload: DetermineRequest,
): Promise<DeterminationResponse> {
  return request<DeterminationResponse>(`/api/program-requests/${programRequestId}/determinations`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function getTrace(determinationId: string): Promise<TraceResponse> {
  return request<TraceResponse>(`/api/determinations/${determinationId}/trace`);
}
