import { useState, type FormEvent } from 'react';
import { ApiValidationError, submitApplication } from '../api/client';
import type { IntakePerson, IntakeRequest } from '../api/types';
import HouseholdMemberFields, { emptyMember } from '../components/HouseholdMemberFields';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { FormField } from '@/components/design-system/FormField';
import { RecordSheet } from '@/components/design-system/RecordSheet';

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
  const [liquidResources, setLiquidResources] = useState('');

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
      resources: liquidResources
        ? [{ resourceType: 'BANK_ACCOUNT', amount: liquidResources, effectiveFrom: todayIso() }]
        : [],
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
      <RecordSheet>
        <h2 className="font-display text-xl">Application submitted</h2>
        <p className="mt-2 text-sm text-foreground">
          Your reference number is <strong>{confirmation.programRequestId}</strong>. A caseworker will
          review your application.
        </p>
      </RecordSheet>
    );
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-6">
      <h2 className="font-display text-xl">Apply for SNAP</h2>

      {errors.length > 0 && (
        <div role="alert" className="text-sm text-destructive">
          <ul>
            {errors.map((message) => (
              <li key={message}>{message}</li>
            ))}
          </ul>
        </div>
      )}

      <RecordSheet>
        <h3 className="font-display text-lg">Household</h3>
        <div className="mt-4 flex flex-col gap-4">
          <FormField id="county" label="County">
            <Input id="county" value={county} onChange={(e) => setCounty(e.target.value)} />
          </FormField>

          <FormField id="addressLine1" label="Street address">
            <Input id="addressLine1" value={addressLine1} onChange={(e) => setAddressLine1(e.target.value)} />
          </FormField>

          <FormField id="city" label="City">
            <Input id="city" value={city} onChange={(e) => setCity(e.target.value)} />
          </FormField>

          <FormField id="state" label="State">
            <Input id="state" value={state} onChange={(e) => setState(e.target.value)} />
          </FormField>

          <FormField id="zipCode" label="ZIP code">
            <Input id="zipCode" value={zipCode} onChange={(e) => setZipCode(e.target.value)} />
          </FormField>

          <FormField id="arrangementType" label="Living arrangement">
            <select
              id="arrangementType"
              value={arrangementType}
              onChange={(e) => setArrangementType(e.target.value)}
              className="rounded-md border border-input bg-background px-3 py-2 text-sm"
            >
              {ARRANGEMENT_TYPES.map((type) => (
                <option key={type} value={type}>
                  {type}
                </option>
              ))}
            </select>
          </FormField>

          <label htmlFor="paysUtilitiesSeparately" className="flex items-center gap-2 text-sm text-foreground">
            <input
              id="paysUtilitiesSeparately"
              type="checkbox"
              checked={paysUtilitiesSeparately}
              onChange={(e) => setPaysUtilitiesSeparately(e.target.checked)}
              className="h-4 w-4 rounded border-input accent-primary"
            />
            Pays utilities separately from rent
          </label>

          <FormField id="liquidResources" label="Cash and bank accounts on hand ($)">
            <Input
              id="liquidResources"
              inputMode="decimal"
              value={liquidResources}
              onChange={(e) => setLiquidResources(e.target.value)}
            />
          </FormField>
        </div>
      </RecordSheet>

      <HouseholdMemberFields members={members} onChange={setMembers} />

      <Button type="submit" disabled={submitting} className="self-start">
        Submit application
      </Button>
    </form>
  );
}
