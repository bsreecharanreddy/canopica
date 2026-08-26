import type { IntakeIncome } from '../api/types';

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
    <fieldset>
      <legend>Income</legend>
      {incomes.map((income, index) => {
        const idPrefix = `member-${memberIndex}-income-${index}`;
        const amountLabel = income.earned ? 'Monthly earned income' : 'Monthly unearned income';
        return (
          <div key={index}>
            <label htmlFor={`${idPrefix}-type`}>Income type</label>
            <select
              id={`${idPrefix}-type`}
              value={income.incomeType}
              onChange={(e) => updateAt(index, { incomeType: e.target.value })}
            >
              {INCOME_TYPES.map((type) => (
                <option key={type} value={type}>
                  {type}
                </option>
              ))}
            </select>

            <label htmlFor={`${idPrefix}-earned`}>
              <input
                id={`${idPrefix}-earned`}
                type="checkbox"
                checked={income.earned}
                onChange={(e) => updateAt(index, { earned: e.target.checked })}
              />
              Earned income
            </label>

            <label htmlFor={`${idPrefix}-amount`}>{amountLabel}</label>
            <input
              id={`${idPrefix}-amount`}
              type="number"
              min="0"
              step="0.01"
              value={income.monthlyAmount}
              onChange={(e) => updateAt(index, { monthlyAmount: e.target.value })}
            />

            <label htmlFor={`${idPrefix}-from`}>Income effective from</label>
            <input
              id={`${idPrefix}-from`}
              type="date"
              value={income.effectiveFrom}
              onChange={(e) => updateAt(index, { effectiveFrom: e.target.value })}
            />

            <button type="button" onClick={() => remove(index)}>
              Remove income
            </button>
          </div>
        );
      })}
      <button type="button" onClick={add}>
        Add income
      </button>
    </fieldset>
  );
}
