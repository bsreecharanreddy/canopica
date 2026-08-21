"""Pydantic models for a generated household, shaped after the operational schema's own
normalized tables (person / household_member / income_record / expense_record) rather than
the intake API's nested wire format -- ``SyntheticHousehold.to_intake_payload()`` is the one
place that reshapes into what Task 7's ``POST /api/applications`` actually expects.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from pydantic import BaseModel


class SyntheticPerson(BaseModel):
    person_id: uuid.UUID
    first_name: str
    last_name: str
    date_of_birth: date
    age: int
    sex: str  # "M" | "F" -- ACS PUMS's SEX variable has no third category to sample from.
    relationship: str  # SELF | SPOUSE | CHILD | PARENT | OTHER_RELATIVE | UNRELATED
    us_citizen: bool = True
    purchases_and_prepares_food_together: bool = True


class SyntheticIncome(BaseModel):
    person_id: uuid.UUID
    income_type: str
    is_earned: bool
    monthly_amount: Decimal
    effective_from: date


class SyntheticExpense(BaseModel):
    person_id: uuid.UUID
    expense_type: str
    monthly_amount: Decimal
    effective_from: date


class LivingArrangement(BaseModel):
    arrangement_type: str  # RENTS | OWNS | SHARED_HOUSING (see fetch_pums.py's tenure mapping)
    pays_utilities_separately: bool


class SyntheticHousehold(BaseModel):
    """One generated household, internally shaped like the operational schema's own tables."""

    household_id: uuid.UUID
    county: str
    address_line1: str
    city: str
    state: str
    zip_code: str
    members: list[SyntheticPerson]
    incomes: list[SyntheticIncome]
    expenses: list[SyntheticExpense]
    living_arrangement: LivingArrangement

    def to_intake_payload(self) -> dict[str, object]:
        """The exact JSON body `POST /api/applications` expects (IntakeRequest, Task 7)."""
        incomes_by_person: dict[uuid.UUID, list[dict[str, object]]] = {
            m.person_id: [] for m in self.members
        }
        for income in self.incomes:
            incomes_by_person[income.person_id].append(
                {
                    "incomeType": income.income_type,
                    "earned": income.is_earned,
                    "monthlyAmount": str(income.monthly_amount),
                    "effectiveFrom": income.effective_from.isoformat(),
                }
            )

        expenses_by_person: dict[uuid.UUID, list[dict[str, object]]] = {
            m.person_id: [] for m in self.members
        }
        for expense in self.expenses:
            expenses_by_person[expense.person_id].append(
                {
                    "expenseType": expense.expense_type,
                    "monthlyAmount": str(expense.monthly_amount),
                    "effectiveFrom": expense.effective_from.isoformat(),
                }
            )

        members_payload = [
            {
                "firstName": member.first_name,
                "lastName": member.last_name,
                "dateOfBirth": member.date_of_birth.isoformat(),
                "sex": member.sex,
                "usCitizen": member.us_citizen,
                "relationship": member.relationship,
                "purchasesAndPreparesFoodTogether": member.purchases_and_prepares_food_together,
                "incomes": incomes_by_person[member.person_id],
                "expenses": expenses_by_person[member.person_id],
            }
            for member in self.members
        ]

        return {
            "county": self.county,
            "addressLine1": self.address_line1,
            "city": self.city,
            "state": self.state,
            "zipCode": self.zip_code,
            "arrangementType": self.living_arrangement.arrangement_type,
            "paysUtilitiesSeparately": self.living_arrangement.pays_utilities_separately,
            "members": members_payload,
        }
