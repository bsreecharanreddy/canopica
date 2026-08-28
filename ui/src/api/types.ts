/**
 * Hand-written mirrors of the Java DTOs in `api/src/main/java/canopica/api/api/dto/`.
 * Task 13's e2e test is what actually keeps these honest if a field disappears server-side.
 */

export type IntakeIncome = {
  incomeType: string;
  earned: boolean;
  monthlyAmount: string; // money as a string end to end -- never round-trips through a float
  effectiveFrom: string; // ISO date (yyyy-MM-dd)
  effectiveTo?: string;
};

export type IntakeExpense = {
  expenseType: string;
  monthlyAmount: string;
  effectiveFrom: string;
  effectiveTo?: string;
};

export type IntakePerson = {
  firstName: string;
  lastName: string;
  dateOfBirth: string;
  sex: string;
  usCitizen?: boolean;
  relationship: string;
  purchasesAndPreparesFoodTogether?: boolean;
  incomes: IntakeIncome[];
  expenses: IntakeExpense[];
};

// Household-level (unlike income/expense, which are per member) -- feeds
// expedited (7-day) SNAP processing eligibility, 7 CFR 273.2(i).
export type IntakeResource = {
  resourceType: string;
  amount: string;
  effectiveFrom: string;
  effectiveTo?: string;
};

export type IntakeRequest = {
  county: string;
  addressLine1: string;
  addressLine2?: string;
  city: string;
  state: string;
  zipCode: string;
  channel?: string;
  arrangementType: string;
  paysUtilitiesSeparately?: boolean;
  members: IntakePerson[];
  resources: IntakeResource[];
};

export type IntakeResponse = {
  applicationId: string;
  programRequestId: string;
};

export type DetermineRequest = {
  asOfDate: string;
  benefitMonth: string;
};

export type ReasonCode =
  | 'ELIGIBLE'
  | 'GROSS_INCOME_EXCEEDS_LIMIT'
  | 'NET_INCOME_EXCEEDS_LIMIT'
  | 'ZERO_BENEFIT_AMOUNT';

export type DeterminationResponse = {
  determinationId: string;
  eligible: boolean;
  // String, not number: money never round-trips through a float. Enforced on the
  // server by canopica.api.config.JacksonConfig, which serialises every BigDecimal
  // as a plain string -- until that existed this type was simply wrong, and
  // JSON.parse was turning a $649.00 award into the double 649.
  benefitAmount: string;
  reasonCode: ReasonCode;
  policyParameterVersion: string;
  benefitMonth: string;
  asOfDate: string;
  decidedAt: string;
};

export type CaseSummaryResponse = {
  programRequestId: string;
  householdHeadName: string;
  status: string;
  submittedAt: string;
  latestDetermination: {
    eligible: boolean;
    benefitAmount: string;
    decidedAt: string;
  } | null;
};

export type CaseDetailResponse = {
  programRequestId: string;
  applicationId: string;
  householdId: string;
  householdHeadName: string;
  programCode: string;
  status: string;
  requestedOn: string;
  determinations: DeterminationResponse[]; // newest-first
};

export type TraceResponse = {
  inputSnapshot: unknown;
  decisionResults: Record<string, unknown>;
  dmnModelHash: string;
  policyParameterVersion: string;
};

// Mirrors canopica.api.api.dto.AuditEventResponse -- a case's audit-trail events, oldest first.
export type AuditEventResponse = {
  eventType: string;
  occurredAt: string;
  actorId: string;
  actorType: 'SYSTEM' | 'HUMAN';
  payload: Record<string, unknown>;
};

// Mirrors canopica.api.api.dto.CaseloadStatsResponse -- the Caseworker Dashboard's real caseload counts.
export type CaseloadStatsResponse = {
  activeCases: number;
  pendingDetermination: number;
  recentEvents: AuditEventResponse[]; // newest-first
};

export type ApiFieldError = {
  field?: string;
  message: string;
};

// Mirrors canopica_ai.policy_intelligence.qa.service.QaAnswer (the Python AI
// service, not the Java API) -- Task 2's Policy Q&A response shape.
export type QaAnswer = {
  answer: string;
  citations: string[];
  abstained: boolean;
};

// Mirrors canopica.api.api.dto.ParameterProposalResponse (the Java API) and,
// for the diff rows, canopica.api.policy.ProposedParameterValue -- which is the
// same shape canopica_ai...rule_authoring.schema.ProposedParameter emits, since the
// API stores what the copilot returned rather than reshaping it.
export type ProposedParameterValue = {
  name: string;
  householdSize: number | null; // null = the figure is scalar (a rate or a threshold)
  oldValue: string; // money and rates as strings end to end -- never through a float
  newValue: string;
  unit: 'USD_PER_MONTH' | 'RATE' | 'COUNT';
  rationale: string;
};

export type ProposalStatus = 'PENDING' | 'ACCEPTED' | 'REJECTED';

export type ParameterProposal = {
  id: string;
  currentParameterSetId: string;
  currentVersionLabel: string;
  sourceExcerpt: string;
  proposedValues: ProposedParameterValue[];
  status: ProposalStatus;
  proposedBy: string;
  reviewedBy: string | null;
  reviewedAt: string | null;
  publishedParameterSetId: string | null;
  generationModel: string;
  promptVersion: string;
  createdAt: string;
};

// Required only when accepting. None of it is derivable: an effective date is a
// policy fact the memo states, and versionLabel is unique by DB constraint.
export type PublicationDetails = {
  versionLabel: string;
  effectiveFrom: string; // ISO date (yyyy-MM-dd)
  sourceCitation: string;
};

// Mirrors canopica.api.document.Document -- the response shape POST /documents and POST
// /documents/{id}/confirm both return.
export type DocumentResponse = {
  id: string;
  programRequestId: string;
  contentType: string;
  classificationStatus: string;
  uploadedAt: string;
};

export type ExtractedField = {
  name: string;
  value: string;
  confidence: number;
};

// Mirrors canopica_ai.document_intake.schema.DocumentExtraction (the Python worker's own output, Phase 3
// Task 3) -- passed through server-side as a raw JsonNode, so these keys stay snake_case rather than
// following this file's own camelCase convention (same choice TraceResponse's fields already made).
export type DocumentExtraction = {
  document_type: string;
  fields: ExtractedField[];
  matched_verification_ids: string[];
  generation_model: string;
  prompt_version: string;
};

// Mirrors canopica.api.api.dto.DocumentReviewItemResponse -- one review-queue row (Task 4).
export type DocumentReviewItem = {
  documentId: string;
  programRequestId: string;
  contentType: string;
  extractionConfidence: string | null; // money-precision convention: a BigDecimal, so a string, not a number
  extraction: DocumentExtraction | null;
  uploadedAt: string;
  headPersonId: string;
  householdHeadName: string;
};

export type ConfirmedIncomeEntry = {
  personId: string;
  incomeType: string;
  earned: boolean;
  monthlyAmount: string; // money as a string end to end -- never through a float
  effectiveFrom: string;
  effectiveTo?: string;
};

// Mirrors canopica.api.api.dto.ConfirmDocumentRequest -- the worker's final, edited-or-accepted values;
// this, not the extraction itself, is what the confirm endpoint actually applies (design doc §2.3's
// mandatory human-confirmation gate).
export type ConfirmDocumentRequest = {
  satisfiedVerificationIds: string[];
  incomeRecords: ConfirmedIncomeEntry[];
};

// Mirrors canopica_ai.correspondence.schema.ValidationResult (Task 5's own deterministic pre-check output),
// passed through as-is inside NoticeReviewItem -- snake_case-free already, since it's Pydantic's own
// camelCase-compatible field names, not a nested JSON blob like DocumentExtraction.
export type ValidationResult = {
  passed: boolean;
  errors: string[];
};

// Mirrors canopica.api.api.dto.NoticeReviewItemResponse -- one review-queue row (Task 6).
export type NoticeReviewItem = {
  noticeId: string;
  programRequestId: string;
  noticeType: 'APPROVAL' | 'DENIAL' | 'PENDING_VERIFICATION';
  status: string;
  content: string;
  validationResult: ValidationResult;
  generationModel: string;
  promptVersion: string;
  createdAt: string;
};

// Mirrors canopica.api.api.dto.NoticeResponse.
export type NoticeResponse = {
  id: string;
  programRequestId: string;
  noticeType: string;
  status: string;
  approvedAt: string | null;
  sentAt: string | null;
};
