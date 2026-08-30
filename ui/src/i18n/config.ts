/** react-i18next wiring (Task 7 plan, Step 1) -- pure UI-string tooling, no LLM
 * involved (design doc §2.5). Resources are bundled at build time via static
 * JSON imports rather than an HTTP backend: this app is small enough that a
 * lazy-loaded namespace would add a network round trip for no real benefit,
 * and a bundled resource set is what keeps `useTranslation` synchronously
 * ready in tests without an async `waitFor` in every render.
 */
import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';

import enCommon from './locales/en/common.json';
import enDashboard from './locales/en/dashboard.json';
import enWorkerCases from './locales/en/workerCases.json';
import enCaseDetail from './locales/en/caseDetail.json';
import enIntake from './locales/en/intake.json';
import enPolicyQa from './locales/en/policyQa.json';
import enDocumentReview from './locales/en/documentReview.json';
import enNoticeReview from './locales/en/noticeReview.json';
import enFraudReview from './locales/en/fraudReview.json';
import enQcReview from './locales/en/qcReview.json';
import enSlaMonitor from './locales/en/slaMonitor.json';
import enSopCopilot from './locales/en/sopCopilot.json';
import enRuleAuthoring from './locales/en/ruleAuthoring.json';

import esCommon from './locales/es/common.json';
import esDashboard from './locales/es/dashboard.json';
import esWorkerCases from './locales/es/workerCases.json';
import esCaseDetail from './locales/es/caseDetail.json';
import esIntake from './locales/es/intake.json';
import esPolicyQa from './locales/es/policyQa.json';
import esDocumentReview from './locales/es/documentReview.json';
import esNoticeReview from './locales/es/noticeReview.json';
import esFraudReview from './locales/es/fraudReview.json';
import esQcReview from './locales/es/qcReview.json';
import esSlaMonitor from './locales/es/slaMonitor.json';
import esSopCopilot from './locales/es/sopCopilot.json';
import esRuleAuthoring from './locales/es/ruleAuthoring.json';

export const SUPPORTED_LANGUAGES = ['en', 'es'] as const;
export type SupportedLanguage = (typeof SUPPORTED_LANGUAGES)[number];

void i18n
  .use(initReactI18next)
  .init({
    lng: 'en',
    fallbackLng: 'en',
    defaultNS: 'common',
    ns: [
      'common',
      'dashboard',
      'workerCases',
      'caseDetail',
      'intake',
      'policyQa',
      'documentReview',
      'noticeReview',
      'fraudReview',
      'qcReview',
      'slaMonitor',
      'sopCopilot',
      'ruleAuthoring',
    ],
    resources: {
      en: {
        common: enCommon,
        dashboard: enDashboard,
        workerCases: enWorkerCases,
        caseDetail: enCaseDetail,
        intake: enIntake,
        policyQa: enPolicyQa,
        documentReview: enDocumentReview,
        noticeReview: enNoticeReview,
        fraudReview: enFraudReview,
        qcReview: enQcReview,
        slaMonitor: enSlaMonitor,
        sopCopilot: enSopCopilot,
        ruleAuthoring: enRuleAuthoring,
      },
      es: {
        common: esCommon,
        dashboard: esDashboard,
        workerCases: esWorkerCases,
        caseDetail: esCaseDetail,
        intake: esIntake,
        policyQa: esPolicyQa,
        documentReview: esDocumentReview,
        noticeReview: esNoticeReview,
        fraudReview: esFraudReview,
        qcReview: esQcReview,
        slaMonitor: esSlaMonitor,
        sopCopilot: esSopCopilot,
        ruleAuthoring: esRuleAuthoring,
      },
    },
    // React already escapes interpolated values -- i18next's own escaping
    // on top would double-escape things like a household head's name.
    interpolation: { escapeValue: false },
  });

export default i18n;
