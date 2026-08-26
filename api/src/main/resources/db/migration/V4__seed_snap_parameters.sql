-- Figures verified against USDA FNS's published memos; see
-- docs/design/policy-parameter-provenance.md for the full transcription and
-- citations. Statutory figures (earned-income deduction rate, medical expense
-- threshold, shelter-income share, benefit-reduction rate, minimum-benefit
-- household-size cutoff) are set by law, not the annual COLA, and are
-- identical across both fiscal years seeded here.

insert into policy_parameter_set (id, program_code, version_label, effective_from, effective_to, source_citation, retrieved_on)
values ('9f1c0e10-0000-4000-8000-000000000001', 'SNAP', 'SNAP-FY2025', date '2024-10-01', date '2025-09-30',
        'SNAP Fiscal Year (FY) 2025 Maximum Allotments and Deductions (https://fns-prod.azureedge.us/sites/default/files/media/file/FY2025-Maximum-Allotments-Deductions.pdf) and FY 2025 Income Eligibility Standards (https://fns-prod.azureedge.us/sites/default/files/media/file/FY2025-Income-Eligibility-Standards.pdf), USDA FNS, updated 10/1/2024', date '2026-08-21');

insert into policy_parameter (id, parameter_set_id, name, household_size, numeric_value, unit)
values
  (gen_random_uuid(), '9f1c0e10-0000-4000-8000-000000000001', 'MAX_ALLOTMENT', 1, 292, 'USD_PER_MONTH'),
  (gen_random_uuid(), '9f1c0e10-0000-4000-8000-000000000001', 'MAX_ALLOTMENT', 2, 536, 'USD_PER_MONTH'),
  (gen_random_uuid(), '9f1c0e10-0000-4000-8000-000000000001', 'MAX_ALLOTMENT', 3, 768, 'USD_PER_MONTH'),
  (gen_random_uuid(), '9f1c0e10-0000-4000-8000-000000000001', 'MAX_ALLOTMENT', 4, 975, 'USD_PER_MONTH'),
  (gen_random_uuid(), '9f1c0e10-0000-4000-8000-000000000001', 'MAX_ALLOTMENT', 5, 1158, 'USD_PER_MONTH'),
  (gen_random_uuid(), '9f1c0e10-0000-4000-8000-000000000001', 'MAX_ALLOTMENT', 6, 1390, 'USD_PER_MONTH'),
  (gen_random_uuid(), '9f1c0e10-0000-4000-8000-000000000001', 'MAX_ALLOTMENT', 7, 1536, 'USD_PER_MONTH'),
  (gen_random_uuid(), '9f1c0e10-0000-4000-8000-000000000001', 'MAX_ALLOTMENT', 8, 1756, 'USD_PER_MONTH'),
  (gen_random_uuid(), '9f1c0e10-0000-4000-8000-000000000001', 'STANDARD_DEDUCTION', 1, 204, 'USD_PER_MONTH'),
  (gen_random_uuid(), '9f1c0e10-0000-4000-8000-000000000001', 'STANDARD_DEDUCTION', 2, 204, 'USD_PER_MONTH'),
  (gen_random_uuid(), '9f1c0e10-0000-4000-8000-000000000001', 'STANDARD_DEDUCTION', 3, 204, 'USD_PER_MONTH'),
  (gen_random_uuid(), '9f1c0e10-0000-4000-8000-000000000001', 'STANDARD_DEDUCTION', 4, 217, 'USD_PER_MONTH'),
  (gen_random_uuid(), '9f1c0e10-0000-4000-8000-000000000001', 'STANDARD_DEDUCTION', 5, 254, 'USD_PER_MONTH'),
  (gen_random_uuid(), '9f1c0e10-0000-4000-8000-000000000001', 'STANDARD_DEDUCTION', 6, 291, 'USD_PER_MONTH'),
  (gen_random_uuid(), '9f1c0e10-0000-4000-8000-000000000001', 'STANDARD_DEDUCTION', 7, 291, 'USD_PER_MONTH'),
  (gen_random_uuid(), '9f1c0e10-0000-4000-8000-000000000001', 'STANDARD_DEDUCTION', 8, 291, 'USD_PER_MONTH'),
  (gen_random_uuid(), '9f1c0e10-0000-4000-8000-000000000001', 'GROSS_INCOME_LIMIT', 1, 1632, 'USD_PER_MONTH'),
  (gen_random_uuid(), '9f1c0e10-0000-4000-8000-000000000001', 'GROSS_INCOME_LIMIT', 2, 2215, 'USD_PER_MONTH'),
  (gen_random_uuid(), '9f1c0e10-0000-4000-8000-000000000001', 'GROSS_INCOME_LIMIT', 3, 2798, 'USD_PER_MONTH'),
  (gen_random_uuid(), '9f1c0e10-0000-4000-8000-000000000001', 'GROSS_INCOME_LIMIT', 4, 3380, 'USD_PER_MONTH'),
  (gen_random_uuid(), '9f1c0e10-0000-4000-8000-000000000001', 'GROSS_INCOME_LIMIT', 5, 3963, 'USD_PER_MONTH'),
  (gen_random_uuid(), '9f1c0e10-0000-4000-8000-000000000001', 'GROSS_INCOME_LIMIT', 6, 4546, 'USD_PER_MONTH'),
  (gen_random_uuid(), '9f1c0e10-0000-4000-8000-000000000001', 'GROSS_INCOME_LIMIT', 7, 5129, 'USD_PER_MONTH'),
  (gen_random_uuid(), '9f1c0e10-0000-4000-8000-000000000001', 'GROSS_INCOME_LIMIT', 8, 5712, 'USD_PER_MONTH'),
  (gen_random_uuid(), '9f1c0e10-0000-4000-8000-000000000001', 'NET_INCOME_LIMIT', 1, 1255, 'USD_PER_MONTH'),
  (gen_random_uuid(), '9f1c0e10-0000-4000-8000-000000000001', 'NET_INCOME_LIMIT', 2, 1704, 'USD_PER_MONTH'),
  (gen_random_uuid(), '9f1c0e10-0000-4000-8000-000000000001', 'NET_INCOME_LIMIT', 3, 2152, 'USD_PER_MONTH'),
  (gen_random_uuid(), '9f1c0e10-0000-4000-8000-000000000001', 'NET_INCOME_LIMIT', 4, 2600, 'USD_PER_MONTH'),
  (gen_random_uuid(), '9f1c0e10-0000-4000-8000-000000000001', 'NET_INCOME_LIMIT', 5, 3049, 'USD_PER_MONTH'),
  (gen_random_uuid(), '9f1c0e10-0000-4000-8000-000000000001', 'NET_INCOME_LIMIT', 6, 3497, 'USD_PER_MONTH'),
  (gen_random_uuid(), '9f1c0e10-0000-4000-8000-000000000001', 'NET_INCOME_LIMIT', 7, 3945, 'USD_PER_MONTH'),
  (gen_random_uuid(), '9f1c0e10-0000-4000-8000-000000000001', 'NET_INCOME_LIMIT', 8, 4394, 'USD_PER_MONTH'),
  (gen_random_uuid(), '9f1c0e10-0000-4000-8000-000000000001', 'EXCESS_SHELTER_CAP', null, 712, 'USD_PER_MONTH'),
  (gen_random_uuid(), '9f1c0e10-0000-4000-8000-000000000001', 'MINIMUM_BENEFIT', null, 23, 'USD_PER_MONTH'),
  (gen_random_uuid(), '9f1c0e10-0000-4000-8000-000000000001', 'EARNED_INCOME_DEDUCTION_RATE', null, 0.20, 'RATE'),
  (gen_random_uuid(), '9f1c0e10-0000-4000-8000-000000000001', 'MEDICAL_EXPENSE_THRESHOLD', null, 35, 'USD_PER_MONTH'),
  (gen_random_uuid(), '9f1c0e10-0000-4000-8000-000000000001', 'SHELTER_INCOME_SHARE', null, 0.50, 'RATE'),
  (gen_random_uuid(), '9f1c0e10-0000-4000-8000-000000000001', 'BENEFIT_REDUCTION_RATE', null, 0.30, 'RATE'),
  (gen_random_uuid(), '9f1c0e10-0000-4000-8000-000000000001', 'MINIMUM_BENEFIT_MAX_HOUSEHOLD_SIZE', null, 2, 'COUNT');

insert into policy_parameter_set (id, program_code, version_label, effective_from, effective_to, source_citation, retrieved_on)
values ('9f1c0e10-0000-4000-8000-000000000002', 'SNAP', 'SNAP-FY2026', date '2025-10-01', null,
        'SNAP - Fiscal Year 2026 Cost-of-Living Adjustments, memo dated 2025-08-13, USDA FNS, signed Ronald Ward, Acting Associate Administrator, SNAP (https://www.usda.gov/sites/default/files/guidance-documents/fns.snap-cola-fy26memo.pdf)', date '2026-08-21');

insert into policy_parameter (id, parameter_set_id, name, household_size, numeric_value, unit)
values
  (gen_random_uuid(), '9f1c0e10-0000-4000-8000-000000000002', 'MAX_ALLOTMENT', 1, 298, 'USD_PER_MONTH'),
  (gen_random_uuid(), '9f1c0e10-0000-4000-8000-000000000002', 'MAX_ALLOTMENT', 2, 546, 'USD_PER_MONTH'),
  (gen_random_uuid(), '9f1c0e10-0000-4000-8000-000000000002', 'MAX_ALLOTMENT', 3, 785, 'USD_PER_MONTH'),
  (gen_random_uuid(), '9f1c0e10-0000-4000-8000-000000000002', 'MAX_ALLOTMENT', 4, 994, 'USD_PER_MONTH'),
  (gen_random_uuid(), '9f1c0e10-0000-4000-8000-000000000002', 'MAX_ALLOTMENT', 5, 1183, 'USD_PER_MONTH'),
  (gen_random_uuid(), '9f1c0e10-0000-4000-8000-000000000002', 'MAX_ALLOTMENT', 6, 1421, 'USD_PER_MONTH'),
  (gen_random_uuid(), '9f1c0e10-0000-4000-8000-000000000002', 'MAX_ALLOTMENT', 7, 1571, 'USD_PER_MONTH'),
  (gen_random_uuid(), '9f1c0e10-0000-4000-8000-000000000002', 'MAX_ALLOTMENT', 8, 1789, 'USD_PER_MONTH'),
  (gen_random_uuid(), '9f1c0e10-0000-4000-8000-000000000002', 'STANDARD_DEDUCTION', 1, 209, 'USD_PER_MONTH'),
  (gen_random_uuid(), '9f1c0e10-0000-4000-8000-000000000002', 'STANDARD_DEDUCTION', 2, 209, 'USD_PER_MONTH'),
  (gen_random_uuid(), '9f1c0e10-0000-4000-8000-000000000002', 'STANDARD_DEDUCTION', 3, 209, 'USD_PER_MONTH'),
  (gen_random_uuid(), '9f1c0e10-0000-4000-8000-000000000002', 'STANDARD_DEDUCTION', 4, 223, 'USD_PER_MONTH'),
  (gen_random_uuid(), '9f1c0e10-0000-4000-8000-000000000002', 'STANDARD_DEDUCTION', 5, 261, 'USD_PER_MONTH'),
  (gen_random_uuid(), '9f1c0e10-0000-4000-8000-000000000002', 'STANDARD_DEDUCTION', 6, 299, 'USD_PER_MONTH'),
  (gen_random_uuid(), '9f1c0e10-0000-4000-8000-000000000002', 'STANDARD_DEDUCTION', 7, 299, 'USD_PER_MONTH'),
  (gen_random_uuid(), '9f1c0e10-0000-4000-8000-000000000002', 'STANDARD_DEDUCTION', 8, 299, 'USD_PER_MONTH'),
  (gen_random_uuid(), '9f1c0e10-0000-4000-8000-000000000002', 'GROSS_INCOME_LIMIT', 1, 1696, 'USD_PER_MONTH'),
  (gen_random_uuid(), '9f1c0e10-0000-4000-8000-000000000002', 'GROSS_INCOME_LIMIT', 2, 2292, 'USD_PER_MONTH'),
  (gen_random_uuid(), '9f1c0e10-0000-4000-8000-000000000002', 'GROSS_INCOME_LIMIT', 3, 2888, 'USD_PER_MONTH'),
  (gen_random_uuid(), '9f1c0e10-0000-4000-8000-000000000002', 'GROSS_INCOME_LIMIT', 4, 3483, 'USD_PER_MONTH'),
  (gen_random_uuid(), '9f1c0e10-0000-4000-8000-000000000002', 'GROSS_INCOME_LIMIT', 5, 4079, 'USD_PER_MONTH'),
  (gen_random_uuid(), '9f1c0e10-0000-4000-8000-000000000002', 'GROSS_INCOME_LIMIT', 6, 4675, 'USD_PER_MONTH'),
  (gen_random_uuid(), '9f1c0e10-0000-4000-8000-000000000002', 'GROSS_INCOME_LIMIT', 7, 5271, 'USD_PER_MONTH'),
  (gen_random_uuid(), '9f1c0e10-0000-4000-8000-000000000002', 'GROSS_INCOME_LIMIT', 8, 5867, 'USD_PER_MONTH'),
  (gen_random_uuid(), '9f1c0e10-0000-4000-8000-000000000002', 'NET_INCOME_LIMIT', 1, 1305, 'USD_PER_MONTH'),
  (gen_random_uuid(), '9f1c0e10-0000-4000-8000-000000000002', 'NET_INCOME_LIMIT', 2, 1763, 'USD_PER_MONTH'),
  (gen_random_uuid(), '9f1c0e10-0000-4000-8000-000000000002', 'NET_INCOME_LIMIT', 3, 2221, 'USD_PER_MONTH'),
  (gen_random_uuid(), '9f1c0e10-0000-4000-8000-000000000002', 'NET_INCOME_LIMIT', 4, 2680, 'USD_PER_MONTH'),
  (gen_random_uuid(), '9f1c0e10-0000-4000-8000-000000000002', 'NET_INCOME_LIMIT', 5, 3138, 'USD_PER_MONTH'),
  (gen_random_uuid(), '9f1c0e10-0000-4000-8000-000000000002', 'NET_INCOME_LIMIT', 6, 3596, 'USD_PER_MONTH'),
  (gen_random_uuid(), '9f1c0e10-0000-4000-8000-000000000002', 'NET_INCOME_LIMIT', 7, 4055, 'USD_PER_MONTH'),
  (gen_random_uuid(), '9f1c0e10-0000-4000-8000-000000000002', 'NET_INCOME_LIMIT', 8, 4513, 'USD_PER_MONTH'),
  (gen_random_uuid(), '9f1c0e10-0000-4000-8000-000000000002', 'EXCESS_SHELTER_CAP', null, 744, 'USD_PER_MONTH'),
  (gen_random_uuid(), '9f1c0e10-0000-4000-8000-000000000002', 'MINIMUM_BENEFIT', null, 24, 'USD_PER_MONTH'),
  (gen_random_uuid(), '9f1c0e10-0000-4000-8000-000000000002', 'EARNED_INCOME_DEDUCTION_RATE', null, 0.20, 'RATE'),
  (gen_random_uuid(), '9f1c0e10-0000-4000-8000-000000000002', 'MEDICAL_EXPENSE_THRESHOLD', null, 35, 'USD_PER_MONTH'),
  (gen_random_uuid(), '9f1c0e10-0000-4000-8000-000000000002', 'SHELTER_INCOME_SHARE', null, 0.50, 'RATE'),
  (gen_random_uuid(), '9f1c0e10-0000-4000-8000-000000000002', 'BENEFIT_REDUCTION_RATE', null, 0.30, 'RATE'),
  (gen_random_uuid(), '9f1c0e10-0000-4000-8000-000000000002', 'MINIMUM_BENEFIT_MAX_HOUSEHOLD_SIZE', null, 2, 'COUNT');
