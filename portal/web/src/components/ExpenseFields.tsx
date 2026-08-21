import type { IntakeExpense } from '../api/types';

const EXPENSE_TYPES = [
  'RENT_OR_MORTGAGE',
  'PROPERTY_TAX',
  'HOME_INSURANCE',
  'UTILITIES',
  'DEPENDENT_CARE',
  'MEDICAL',
  'CHILD_SUPPORT_PAID',
] as const;

const EXPENSE_LABELS: Record<(typeof EXPENSE_TYPES)[number], string> = {
  RENT_OR_MORTGAGE: 'rent or mortgage',
  PROPERTY_TAX: 'property tax',
  HOME_INSURANCE: 'home insurance',
  UTILITIES: 'utilities',
  DEPENDENT_CARE: 'dependent care',
  MEDICAL: 'medical',
  CHILD_SUPPORT_PAID: 'child support paid',
};

type Props = {
  memberIndex: number;
  expenses: IntakeExpense[];
  onChange: (expenses: IntakeExpense[]) => void;
};

export default function ExpenseFields({ memberIndex, expenses, onChange }: Props) {
  function updateAt(index: number, patch: Partial<IntakeExpense>) {
    onChange(expenses.map((expense, i) => (i === index ? { ...expense, ...patch } : expense)));
  }

  function add() {
    onChange([
      ...expenses,
      { expenseType: 'RENT_OR_MORTGAGE', monthlyAmount: '', effectiveFrom: new Date().toISOString().slice(0, 10) },
    ]);
  }

  function remove(index: number) {
    onChange(expenses.filter((_, i) => i !== index));
  }

  return (
    <fieldset>
      <legend>Expenses</legend>
      {expenses.map((expense, index) => {
        const idPrefix = `member-${memberIndex}-expense-${index}`;
        const expenseType = expense.expenseType as (typeof EXPENSE_TYPES)[number];
        const amountLabel = `Monthly ${EXPENSE_LABELS[expenseType] ?? expenseType.toLowerCase()}`;
        return (
          <div key={index}>
            <label htmlFor={`${idPrefix}-type`}>Expense type</label>
            <select
              id={`${idPrefix}-type`}
              value={expense.expenseType}
              onChange={(e) => updateAt(index, { expenseType: e.target.value })}
            >
              {EXPENSE_TYPES.map((type) => (
                <option key={type} value={type}>
                  {EXPENSE_LABELS[type]}
                </option>
              ))}
            </select>

            <label htmlFor={`${idPrefix}-amount`}>{amountLabel}</label>
            <input
              id={`${idPrefix}-amount`}
              type="number"
              min="0"
              step="0.01"
              value={expense.monthlyAmount}
              onChange={(e) => updateAt(index, { monthlyAmount: e.target.value })}
            />

            <label htmlFor={`${idPrefix}-from`}>Expense effective from</label>
            <input
              id={`${idPrefix}-from`}
              type="date"
              value={expense.effectiveFrom}
              onChange={(e) => updateAt(index, { effectiveFrom: e.target.value })}
            />

            <button type="button" onClick={() => remove(index)}>
              Remove expense
            </button>
          </div>
        );
      })}
      <button type="button" onClick={add}>
        Add expense
      </button>
    </fieldset>
  );
}
