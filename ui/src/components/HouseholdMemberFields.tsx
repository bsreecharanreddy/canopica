import type { IntakePerson } from '../api/types';
import IncomeFields from './IncomeFields';
import ExpenseFields from './ExpenseFields';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { FormField } from '@/components/design-system/FormField';
import { RecordSheet } from '@/components/design-system/RecordSheet';

const RELATIONSHIPS = ['SELF', 'SPOUSE', 'CHILD', 'PARENT', 'OTHER_RELATIVE', 'UNRELATED'] as const;

type Props = {
  members: IntakePerson[];
  onChange: (members: IntakePerson[]) => void;
};

export function emptyMember(relationship: string): IntakePerson {
  return {
    firstName: '',
    lastName: '',
    dateOfBirth: '',
    sex: 'X',
    relationship,
    incomes: [],
    expenses: [],
  };
}

export default function HouseholdMemberFields({ members, onChange }: Props) {
  function updateAt(index: number, patch: Partial<IntakePerson>) {
    onChange(members.map((member, i) => (i === index ? { ...member, ...patch } : member)));
  }

  function addMember() {
    onChange([...members, emptyMember('OTHER_RELATIVE')]);
  }

  function removeMember(index: number) {
    onChange(members.filter((_, i) => i !== index));
  }

  return (
    <div className="flex flex-col gap-4">
      {members.map((member, index) => {
        const idPrefix = `member-${index}`;
        return (
          <RecordSheet key={index}>
            <h3 className="font-display text-lg">
              {index === 0 ? 'Head of household' : `Household member ${index + 1}`}
            </h3>

            <div className="mt-4 flex flex-col gap-4">
              <FormField id={`${idPrefix}-firstName`} label="First name">
                <Input
                  id={`${idPrefix}-firstName`}
                  value={member.firstName}
                  onChange={(e) => updateAt(index, { firstName: e.target.value })}
                />
              </FormField>

              <FormField id={`${idPrefix}-lastName`} label="Last name">
                <Input
                  id={`${idPrefix}-lastName`}
                  value={member.lastName}
                  onChange={(e) => updateAt(index, { lastName: e.target.value })}
                />
              </FormField>

              <FormField id={`${idPrefix}-dob`} label="Date of birth">
                <Input
                  id={`${idPrefix}-dob`}
                  type="date"
                  value={member.dateOfBirth}
                  onChange={(e) => updateAt(index, { dateOfBirth: e.target.value })}
                />
              </FormField>

              <FormField id={`${idPrefix}-relationship`} label="Relationship to head of household">
                <select
                  id={`${idPrefix}-relationship`}
                  value={member.relationship}
                  disabled={index === 0}
                  onChange={(e) => updateAt(index, { relationship: e.target.value })}
                  className="rounded-md border border-input bg-background px-3 py-2 text-sm"
                >
                  {RELATIONSHIPS.map((relationship) => (
                    <option key={relationship} value={relationship}>
                      {relationship}
                    </option>
                  ))}
                </select>
              </FormField>

              <IncomeFields
                memberIndex={index}
                incomes={member.incomes}
                onChange={(incomes) => updateAt(index, { incomes })}
              />
              <ExpenseFields
                memberIndex={index}
                expenses={member.expenses}
                onChange={(expenses) => updateAt(index, { expenses })}
              />

              {index > 0 && (
                <Button type="button" variant="outline" onClick={() => removeMember(index)} className="self-start">
                  Remove this household member
                </Button>
              )}
            </div>
          </RecordSheet>
        );
      })}
      <Button type="button" variant="secondary" onClick={addMember} className="self-start">
        Add household member
      </Button>
    </div>
  );
}
