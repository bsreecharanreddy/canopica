import type { IntakeIncome } from '../api/types';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { FormField } from '@/components/design-system/FormField';
import { RecordSheet } from '@/components/design-system/RecordSheet';

const INCOME_TYPES = [
  'WAGES',
  'SELF_EMPLOYMENT',
  'UNEMPLOYMENT',
  'SOCIAL_SECURITY',
  'SSI',
  'CHILD_SUPPORT',
  'PENSION',
  'OTHER_UNEARNED',
] as const;

type Props = {
  memberIndex: number;
  incomes: IntakeIncome[];
  onChange: (incomes: IntakeIncome[]) => void;
};

export default function IncomeFields({ memberIndex, incomes, onChange }: Props) {
  function updateAt(index: number, patch: Partial<IntakeIncome>) {
    onChange(incomes.map((income, i) => (i === index ? { ...income, ...patch } : income)));
  }

  function add() {
    onChange([
      ...incomes,
      { incomeType: 'WAGES', earned: true, monthlyAmount: '', effectiveFrom: new Date().toISOString().slice(0, 10) },
    ]);
  }

  function remove(index: number) {
    onChange(incomes.filter((_, i) => i !== index));
  }

  return (
    <RecordSheet>
      <h3 className="font-display text-lg">Income</h3>
      <div className="mt-4 flex flex-col gap-4">
        {incomes.map((income, index) => {
          const idPrefix = `member-${memberIndex}-income-${index}`;
          const amountLabel = income.earned ? 'Monthly earned income' : 'Monthly unearned income';
          return (
            <div key={index} className="flex flex-col gap-4">
              <FormField id={`${idPrefix}-type`} label="Income type">
                <select
                  id={`${idPrefix}-type`}
                  value={income.incomeType}
                  onChange={(e) => updateAt(index, { incomeType: e.target.value })}
                  className="rounded-md border border-input bg-background px-3 py-2 text-sm"
                >
                  {INCOME_TYPES.map((type) => (
                    <option key={type} value={type}>
                      {type}
                    </option>
                  ))}
                </select>
              </FormField>

              <label htmlFor={`${idPrefix}-earned`} className="flex items-center gap-2 text-sm text-foreground">
                <input
                  id={`${idPrefix}-earned`}
                  type="checkbox"
                  checked={income.earned}
                  onChange={(e) => updateAt(index, { earned: e.target.checked })}
                  className="h-4 w-4 rounded border-input accent-primary"
                />
                Earned income
              </label>

              <FormField id={`${idPrefix}-amount`} label={amountLabel}>
                <Input
                  id={`${idPrefix}-amount`}
                  type="number"
                  min="0"
                  step="0.01"
                  value={income.monthlyAmount}
                  onChange={(e) => updateAt(index, { monthlyAmount: e.target.value })}
                />
              </FormField>

              <FormField id={`${idPrefix}-from`} label="Income effective from">
                <Input
                  id={`${idPrefix}-from`}
                  type="date"
                  value={income.effectiveFrom}
                  onChange={(e) => updateAt(index, { effectiveFrom: e.target.value })}
                />
              </FormField>

              <Button type="button" variant="outline" onClick={() => remove(index)} className="self-start">
                Remove income
              </Button>
            </div>
          );
        })}
        <Button type="button" variant="secondary" onClick={add} className="self-start">
          Add income
        </Button>
      </div>
    </RecordSheet>
  );
}
