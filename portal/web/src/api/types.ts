/**
 * Hand-written mirrors of the Java DTOs in `portal/src/main/java/canopica/portal/api/dto/`.
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
  benefitAmount: string; // string, not number: money never round-trips through a float
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

export type ApiFieldError = {
  field?: string;
  message: string;
};

// Mirrors canopica_ai.policy_intelligence.qa.service.QaAnswer (the Python AI
// service, not the Java portal) -- Task 2's Policy Q&A response shape.
export type QaAnswer = {
  answer: string;
  citations: string[];
  abstained: boolean;
};
