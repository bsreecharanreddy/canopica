import type { IntakeExpense } from '../api/types';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { FormField } from '@/components/design-system/FormField';
import { RecordSheet } from '@/components/design-system/RecordSheet';

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
    <RecordSheet>
      <h3 className="font-display text-lg">Expenses</h3>
      <div className="mt-4 flex flex-col gap-4">
        {expenses.map((expense, index) => {
          const idPrefix = `member-${memberIndex}-expense-${index}`;
          const expenseType = expense.expenseType as (typeof EXPENSE_TYPES)[number];
          const amountLabel = `Monthly ${EXPENSE_LABELS[expenseType] ?? expenseType.toLowerCase()}`;
          return (
            <div key={index} className="flex flex-col gap-4">
              <FormField id={`${idPrefix}-type`} label="Expense type">
                <select
                  id={`${idPrefix}-type`}
                  value={expense.expenseType}
                  onChange={(e) => updateAt(index, { expenseType: e.target.value })}
                  className="rounded-md border border-input bg-background px-3 py-2 text-sm"
                >
                  {EXPENSE_TYPES.map((type) => (
                    <option key={type} value={type}>
                      {EXPENSE_LABELS[type]}
                    </option>
                  ))}
                </select>
              </FormField>

              <FormField id={`${idPrefix}-amount`} label={amountLabel}>
                <Input
                  id={`${idPrefix}-amount`}
                  type="number"
                  min="0"
                  step="0.01"
                  value={expense.monthlyAmount}
                  onChange={(e) => updateAt(index, { monthlyAmount: e.target.value })}
                />
              </FormField>

              <FormField id={`${idPrefix}-from`} label="Expense effective from">
                <Input
                  id={`${idPrefix}-from`}
                  type="date"
                  value={expense.effectiveFrom}
                  onChange={(e) => updateAt(index, { effectiveFrom: e.target.value })}
                />
              </FormField>

              <Button type="button" variant="outline" onClick={() => remove(index)} className="self-start">
                Remove expense
              </Button>
            </div>
          );
        })}
        <Button type="button" variant="secondary" onClick={add} className="self-start">
          Add expense
        </Button>
      </div>
    </RecordSheet>
  );
}
