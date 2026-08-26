-- Sensitive-case flagging (design doc §2.1): flag-and-log, not sealing --
-- every role that could already see a case still can once this is set, it
-- only raises the audit signal a real access-review process would triage
-- first. SUPERVISOR-only to set, via the /api/supervisor endpoint.
alter table household add column is_sensitive boolean not null default false;
alter table household add column sensitive_reason text;
