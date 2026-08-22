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

// The real access token from whichever realm the user is currently signed into -- set by AuthBridge
// (src/auth/AuthContext.tsx) whenever react-oidc-context's own auth state changes. No storage/persistence
// here: react-oidc-context already persists the token itself (sessionStorage, by its own default), this is
// just a plain read-through so `request()` below doesn't need to be a hook.
let currentAccessToken: string | null = null;

export function setAccessToken(token: string | null): void {
  currentAccessToken = token;
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
      ...(currentAccessToken ? { Authorization: `Bearer ${currentAccessToken}` } : {}),
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
