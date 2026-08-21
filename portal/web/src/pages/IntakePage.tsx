import { useState, type FormEvent } from 'react';
import { ApiValidationError, submitApplication } from '../api/client';
import type { IntakePerson, IntakeRequest } from '../api/types';
import HouseholdMemberFields, { emptyMember } from '../components/HouseholdMemberFields';

const ARRANGEMENT_TYPES = ['RENTS', 'OWNS', 'HOMELESS', 'SHARED_HOUSING', 'INSTITUTION'] as const;

function todayIso(): string {
  return new Date().toISOString().slice(0, 10);
}

function initialMembers(): IntakePerson[] {
  const head = emptyMember('SELF');
  head.incomes = [{ incomeType: 'WAGES', earned: true, monthlyAmount: '', effectiveFrom: todayIso() }];
  head.expenses = [{ expenseType: 'RENT_OR_MORTGAGE', monthlyAmount: '', effectiveFrom: todayIso() }];
  return [head];
}

export default function IntakePage() {
  const [county, setCounty] = useState('');
  const [addressLine1, setAddressLine1] = useState('');
  const [city, setCity] = useState('');
  const [state, setState] = useState('');
  const [zipCode, setZipCode] = useState('');
  const [arrangementType, setArrangementType] = useState<string>(ARRANGEMENT_TYPES[0]);
  const [paysUtilitiesSeparately, setPaysUtilitiesSeparately] = useState(false);
  const [members, setMembers] = useState<IntakePerson[]>(initialMembers());

  const [submitting, setSubmitting] = useState(false);
  const [errors, setErrors] = useState<string[]>([]);
  const [confirmation, setConfirmation] = useState<{ programRequestId: string } | null>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setErrors([]);
    setSubmitting(true);

    const request: IntakeRequest = {
      county,
      addressLine1,
      city,
      state,
      zipCode,
      arrangementType,
      paysUtilitiesSeparately,
      members,
    };

    try {
      const response = await submitApplication(request);
      setConfirmation({ programRequestId: response.programRequestId });
    } catch (err) {
      if (err instanceof ApiValidationError) {
        setErrors(err.errors.map((e) => (e.field ? `${e.field}: ${e.message}` : e.message)));
      } else {
        setErrors(['Something went wrong submitting your application. Please try again.']);
      }
    } finally {
      setSubmitting(false);
    }
  }

  if (confirmation) {
    return (
      <section>
        <h2>Application submitted</h2>
        <p>
          Your reference number is <strong>{confirmation.programRequestId}</strong>. A caseworker will
          review your application.
        </p>
      </section>
    );
  }

  return (
    <form onSubmit={handleSubmit}>
      <h2>Apply for SNAP</h2>

      {errors.length > 0 && (
        <div role="alert">
          <ul>
            {errors.map((message) => (
              <li key={message}>{message}</li>
            ))}
          </ul>
        </div>
      )}

      <fieldset>
        <legend>Household</legend>

        <label htmlFor="county">County</label>
        <input id="county" value={county} onChange={(e) => setCounty(e.target.value)} />

        <label htmlFor="addressLine1">Street address</label>
        <input id="addressLine1" value={addressLine1} onChange={(e) => setAddressLine1(e.target.value)} />

        <label htmlFor="city">City</label>
        <input id="city" value={city} onChange={(e) => setCity(e.target.value)} />

        <label htmlFor="state">State</label>
        <input id="state" value={state} onChange={(e) => setState(e.target.value)} />

        <label htmlFor="zipCode">ZIP code</label>
        <input id="zipCode" value={zipCode} onChange={(e) => setZipCode(e.target.value)} />

        <label htmlFor="arrangementType">Living arrangement</label>
        <select id="arrangementType" value={arrangementType} onChange={(e) => setArrangementType(e.target.value)}>
          {ARRANGEMENT_TYPES.map((type) => (
            <option key={type} value={type}>
              {type}
            </option>
          ))}
        </select>

        <label htmlFor="paysUtilitiesSeparately">
          <input
            id="paysUtilitiesSeparately"
            type="checkbox"
            checked={paysUtilitiesSeparately}
            onChange={(e) => setPaysUtilitiesSeparately(e.target.checked)}
          />
          Pays utilities separately from rent
        </label>
      </fieldset>

      <HouseholdMemberFields members={members} onChange={setMembers} />

      <button type="submit" disabled={submitting}>
        Submit application
      </button>
    </form>
  );
}
