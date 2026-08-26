import type { IntakePerson } from '../api/types';
import IncomeFields from './IncomeFields';
import ExpenseFields from './ExpenseFields';

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
    <div>
      {members.map((member, index) => {
        const idPrefix = `member-${index}`;
        return (
          <fieldset key={index}>
            <legend>{index === 0 ? 'Head of household' : `Household member ${index + 1}`}</legend>

            <label htmlFor={`${idPrefix}-firstName`}>First name</label>
            <input
              id={`${idPrefix}-firstName`}
              value={member.firstName}
              onChange={(e) => updateAt(index, { firstName: e.target.value })}
            />

            <label htmlFor={`${idPrefix}-lastName`}>Last name</label>
            <input
              id={`${idPrefix}-lastName`}
              value={member.lastName}
              onChange={(e) => updateAt(index, { lastName: e.target.value })}
            />

            <label htmlFor={`${idPrefix}-dob`}>Date of birth</label>
            <input
              id={`${idPrefix}-dob`}
              type="date"
              value={member.dateOfBirth}
              onChange={(e) => updateAt(index, { dateOfBirth: e.target.value })}
            />

            <label htmlFor={`${idPrefix}-relationship`}>Relationship to head of household</label>
            <select
              id={`${idPrefix}-relationship`}
              value={member.relationship}
              disabled={index === 0}
              onChange={(e) => updateAt(index, { relationship: e.target.value })}
            >
              {RELATIONSHIPS.map((relationship) => (
                <option key={relationship} value={relationship}>
                  {relationship}
                </option>
              ))}
            </select>

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
              <button type="button" onClick={() => removeMember(index)}>
                Remove this household member
              </button>
            )}
          </fieldset>
        );
      })}
      <button type="button" onClick={addMember}>
        Add household member
      </button>
    </div>
  );
}
