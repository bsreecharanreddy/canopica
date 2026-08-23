package ies.portal.api;

/** Raw JSON bodies for {@code POST /api/applications}, matching {@code IntakeRequest}'s field names exactly. */
final class TestPayloads {

    private TestPayloads() {
    }

    /** Same shape as {@code CaseFixtures.threePersonWorkingHousehold}: three-person household, one wage earner. */
    static String threePersonWorkingHouseholdIntake() {
        return """
                {
                  "county": "Test County",
                  "addressLine1": "123 Test St",
                  "city": "Testville",
                  "state": "TS",
                  "zipCode": "00000",
                  "channel": "ONLINE",
                  "arrangementType": "RENTS",
                  "paysUtilitiesSeparately": false,
                  "members": [
                    {
                      "firstName": "Dana", "lastName": "Reyes", "dateOfBirth": "1990-04-02",
                      "sex": "X", "relationship": "SELF",
                      "incomes": [
                        {"incomeType": "WAGES", "earned": true, "monthlyAmount": "1500.00", "effectiveFrom": "2025-01-01"}
                      ],
                      "expenses": [
                        {"expenseType": "RENT_OR_MORTGAGE", "monthlyAmount": "800.00", "effectiveFrom": "2025-01-01"},
                        {"expenseType": "UTILITIES", "monthlyAmount": "300.00", "effectiveFrom": "2025-01-01"}
                      ]
                    },
                    {
                      "firstName": "Alex", "lastName": "Reyes", "dateOfBirth": "1991-06-15",
                      "sex": "X", "relationship": "SPOUSE"
                    },
                    {
                      "firstName": "Sam", "lastName": "Reyes", "dateOfBirth": "2015-09-20",
                      "sex": "X", "relationship": "CHILD"
                    }
                  ]
                }
                """;
    }

    /** Low income, low liquid resources -- qualifies for expedited (7-day) processing under 7 CFR 273.2(i)(1)(i). */
    static String expeditedHouseholdIntake() {
        return """
                {
                  "county": "Test County",
                  "addressLine1": "123 Test St",
                  "city": "Testville",
                  "state": "TS",
                  "zipCode": "00000",
                  "channel": "ONLINE",
                  "arrangementType": "RENTS",
                  "members": [
                    {
                      "firstName": "Jordan", "lastName": "Lee", "dateOfBirth": "1985-01-01",
                      "sex": "X", "relationship": "SELF",
                      "incomes": [
                        {"incomeType": "UNEMPLOYMENT", "earned": false, "monthlyAmount": "100.00", "effectiveFrom": "2025-01-01"}
                      ]
                    }
                  ],
                  "resources": [
                    {"resourceType": "CASH", "amount": "50.00", "effectiveFrom": "2025-01-01"}
                  ]
                }
                """;
    }

    static String intakeWithNoMembers() {
        return """
                {
                  "county": "Test County",
                  "addressLine1": "123 Test St",
                  "city": "Testville",
                  "state": "TS",
                  "zipCode": "00000",
                  "arrangementType": "RENTS",
                  "members": []
                }
                """;
    }

    /** Same household as {@link #threePersonWorkingHouseholdIntake()}, but the head's income has effectiveTo before effectiveFrom. */
    static String intakeWithInvertedIncomeDates() {
        return """
                {
                  "county": "Test County",
                  "addressLine1": "123 Test St",
                  "city": "Testville",
                  "state": "TS",
                  "zipCode": "00000",
                  "arrangementType": "RENTS",
                  "members": [
                    {
                      "firstName": "Dana", "lastName": "Reyes", "dateOfBirth": "1990-04-02",
                      "sex": "X", "relationship": "SELF",
                      "incomes": [
                        {
                          "incomeType": "WAGES", "earned": true, "monthlyAmount": "1500.00",
                          "effectiveFrom": "2025-03-01", "effectiveTo": "2025-02-01"
                        }
                      ]
                    }
                  ]
                }
                """;
    }
}
