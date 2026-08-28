import type {
  AuditEventResponse,
  CaseDetailResponse,
  CaseloadStatsResponse,
  CaseSummaryResponse,
  ConfirmDocumentRequest,
  DetermineRequest,
  DeterminationResponse,
  DocumentResponse,
  DocumentReviewItem,
  IntakeRequest,
  IntakeResponse,
  NoticeResponse,
  NoticeReviewItem,
  ParameterProposal,
  ProposalStatus,
  PublicationDetails,
  QaAnswer,
  TraceResponse,
  ApiFieldError,
} from './types';

// A separate origin from the Java API above -- the Python ai/
// service (canopica_ai.policy_intelligence.qa.api). No committed Compose
// service/Dockerfile serves it yet (Task 9's "public hosted demo" is
// where this AI layer actually gets deployed); this default is for
// running `uvicorn canopica_ai.policy_intelligence.qa.api:app --port 8000`
// locally in the meantime.
const AI_API_URL = 'http://localhost:8000';

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

export function getAuditTrail(programRequestId: string): Promise<AuditEventResponse[]> {
  return request<AuditEventResponse[]>(`/api/cases/${programRequestId}/audit`);
}

export function getCaseloadStats(): Promise<CaseloadStatsResponse> {
  return request<CaseloadStatsResponse>('/api/cases/dashboard');
}

export function getDocumentReviewQueue(): Promise<DocumentReviewItem[]> {
  return request<DocumentReviewItem[]>('/api/cases/documents/review-queue');
}

export function confirmDocument(
  documentId: string,
  payload: ConfirmDocumentRequest,
): Promise<DocumentResponse> {
  return request<DocumentResponse>(`/api/cases/documents/${documentId}/confirm`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function getNoticeReviewQueue(): Promise<NoticeReviewItem[]> {
  return request<NoticeReviewItem[]>('/api/cases/notices/review-queue');
}

export function approveNotice(noticeId: string): Promise<NoticeResponse> {
  return request<NoticeResponse>(`/api/cases/notices/${noticeId}/approve`, { method: 'POST' });
}

export function rejectNotice(noticeId: string): Promise<NoticeResponse> {
  return request<NoticeResponse>(`/api/cases/notices/${noticeId}/reject`, { method: 'POST' });
}

export function askPolicyQuestion(question: string): Promise<QaAnswer> {
  return request<QaAnswer>(`${AI_API_URL}/qa/ask`, {
    method: 'POST',
    body: JSON.stringify({ question }),
  });
}

export function askWhyWasIDenied(determinationId: string): Promise<QaAnswer> {
  return request<QaAnswer>(`${AI_API_URL}/qa/why-was-i-denied`, {
    method: 'POST',
    body: JSON.stringify({ determinationId }),
  });
}

// Rule-authoring copilot review (ADMIN-only; SecurityConfig gates
// /api/policy/**). These hit the Java API, not the AI service directly --
// the API owns the parameter data and the publish decision, and asks the
// copilot for a draft on the admin's behalf.
export function listProposals(status: ProposalStatus = 'PENDING'): Promise<ParameterProposal[]> {
  return request<ParameterProposal[]>(`/api/policy/proposals?status=${status}`);
}

export function proposeParameterChanges(documentExcerpt: string): Promise<ParameterProposal> {
  return request<ParameterProposal>('/api/policy/proposals', {
    method: 'POST',
    body: JSON.stringify({ documentExcerpt }),
  });
}

export function reviewProposal(
  proposalId: string,
  accept: boolean,
  publication?: PublicationDetails,
): Promise<ParameterProposal> {
  return request<ParameterProposal>(`/api/policy/proposals/${proposalId}/review`, {
    method: 'POST',
    body: JSON.stringify({ accept, ...(accept ? publication : {}) }),
  });
}
