import { useEffect, useState } from 'react';
import { confirmDocument, getDocumentReviewQueue } from '../api/client';
import type { ConfirmDocumentRequest, ConfirmedIncomeEntry, DocumentReviewItem, ExtractedField } from '../api/types';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { FormField } from '@/components/design-system/FormField';
import { RecordSheet } from '@/components/design-system/RecordSheet';
import { StatusPill, type StatusPillTone } from '@/components/design-system/StatusPill';
import { AiAdvisoryBadge } from '@/components/design-system/AiAdvisoryBadge';

function todayIso(): string {
  return new Date().toISOString().slice(0, 10);
}

// Not color alone (this project's accessibility bar, Phase 1b onward): every tier carries its own text
// label too, so a low-confidence field is still identifiable without relying on the pill's color.
function confidenceTier(confidence: number): { tone: StatusPillTone; label: string } {
  if (confidence < 0.5) return { tone: 'exception', label: 'Low confidence' };
  if (confidence < 0.8) return { tone: 'pending', label: 'Medium confidence' };
  return { tone: 'affirmed', label: 'High confidence' };
}

// Best-effort pre-fill only -- the worker's own edited value in the form below, not this guess, is what
// actually gets sent on confirm (design doc §2.3's mandatory human-confirmation gate).
function guessMonthlyAmount(fields: ExtractedField[]): string {
  const match = fields.find((f) => f.name.toLowerCase().includes('amount'));
  return match?.value ?? '';
}

function ExtractedFieldsTable({ fields }: { fields: ExtractedField[] }) {
  if (fields.length === 0) {
    return <p className="text-sm text-muted-foreground">No fields were extracted from this document.</p>;
  }
  return (
    <table className="w-full border-collapse text-sm">
      <thead>
        <tr>
          <th scope="col" className="border-b border-border px-3 py-2 text-left text-xs uppercase tracking-wide text-muted-foreground">
            Field
          </th>
          <th scope="col" className="border-b border-border px-3 py-2 text-left text-xs uppercase tracking-wide text-muted-foreground">
            Extracted value
          </th>
          <th scope="col" className="border-b border-border px-3 py-2 text-left text-xs uppercase tracking-wide text-muted-foreground">
            Confidence
          </th>
        </tr>
      </thead>
      <tbody>
        {fields.map((field) => {
          const tier = confidenceTier(field.confidence);
          return (
            <tr key={field.name} className="border-b border-border">
              <th scope="row" className="px-3 py-2 text-left font-normal text-foreground">
                {field.name}
              </th>
              <td className="px-3 py-2 text-foreground">{field.value}</td>
              <td className="px-3 py-2">
                <StatusPill tone={tier.tone}>{tier.label}</StatusPill>
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

function VerificationChecklist({
  verificationIds,
  selected,
  onToggle,
}: {
  verificationIds: string[];
  selected: Set<string>;
  onToggle: (id: string) => void;
}) {
  if (verificationIds.length === 0) {
    return <p className="text-sm text-muted-foreground">This document did not match any outstanding verification.</p>;
  }
  return (
    <ul className="flex flex-col gap-2">
      {verificationIds.map((id) => {
        const checkboxId = `verification-${id}`;
        return (
          <li key={id} className="flex items-center gap-2">
            <input
              id={checkboxId}
              type="checkbox"
              className="h-4 w-4 rounded border-border accent-primary focus-visible:outline-2 focus-visible:outline-ring"
              checked={selected.has(id)}
              onChange={() => onToggle(id)}
            />
            <label htmlFor={checkboxId} className="text-sm text-foreground">
              Satisfies outstanding verification {id.slice(0, 8)}
            </label>
          </li>
        );
      })}
    </ul>
  );
}

function IncomeRecordFields({
  income,
  onChange,
}: {
  income: ConfirmedIncomeEntry;
  onChange: (next: ConfirmedIncomeEntry) => void;
}) {
  return (
    <div className="mt-3 flex flex-col gap-4">
      <FormField id="incomeType" label="Income type">
        <Input id="incomeType" value={income.incomeType} onChange={(e) => onChange({ ...income, incomeType: e.target.value })} />
      </FormField>
      <FormField id="monthlyAmount" label="Monthly amount">
        <Input
          id="monthlyAmount"
          inputMode="decimal"
          value={income.monthlyAmount}
          onChange={(e) => onChange({ ...income, monthlyAmount: e.target.value })}
        />
      </FormField>
      <FormField id="effectiveFrom" label="Effective from">
        <Input
          id="effectiveFrom"
          type="date"
          value={income.effectiveFrom}
          onChange={(e) => onChange({ ...income, effectiveFrom: e.target.value })}
        />
      </FormField>
    </div>
  );
}

function ReviewForm({ item, onConfirmed }: { item: DocumentReviewItem; onConfirmed: (documentId: string) => void }) {
  const extraction = item.extraction;
  const isIncomeReport = extraction?.document_type === 'INCOME_REPORT';

  const [selectedVerificationIds, setSelectedVerificationIds] = useState<Set<string>>(
    () => new Set(extraction?.matched_verification_ids ?? []),
  );
  const [postIncome, setPostIncome] = useState(isIncomeReport);
  const [income, setIncome] = useState<ConfirmedIncomeEntry>(() => ({
    personId: item.headPersonId,
    incomeType: 'WAGES',
    earned: true,
    monthlyAmount: guessMonthlyAmount(extraction?.fields ?? []),
    effectiveFrom: todayIso(),
  }));
  const [confirming, setConfirming] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function toggleVerification(id: string) {
    setSelectedVerificationIds((current) => {
      const next = new Set(current);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  }

  async function handleConfirm() {
    setConfirming(true);
    setError(null);
    try {
      const payload: ConfirmDocumentRequest = {
        satisfiedVerificationIds: Array.from(selectedVerificationIds),
        incomeRecords: postIncome && income.monthlyAmount ? [income] : [],
      };
      const confirmed = await confirmDocument(item.documentId, payload);
      onConfirmed(confirmed.id);
    } catch {
      setError('Could not confirm this document. Nothing was applied; please try again.');
    } finally {
      setConfirming(false);
    }
  }

  return (
    <RecordSheet>
      <AiAdvisoryBadge />
      <h3 className="mt-2 font-display text-lg">Reviewing document for {item.householdHeadName}</h3>
      {extraction && (
        <p className="mt-1 text-sm text-muted-foreground">
          Classified as {extraction.document_type} by {extraction.generation_model} (prompt {extraction.prompt_version}).
          Nothing reaches this case until you confirm.
        </p>
      )}

      {error && (
        <p role="alert" className="mt-3 text-sm text-destructive">
          {error}
        </p>
      )}

      <div className="mt-4">
        <ExtractedFieldsTable fields={extraction?.fields ?? []} />
      </div>

      <div className="mt-5">
        <h4 className="font-display text-base">Outstanding verifications</h4>
        <div className="mt-2">
          <VerificationChecklist
            verificationIds={extraction?.matched_verification_ids ?? []}
            selected={selectedVerificationIds}
            onToggle={toggleVerification}
          />
        </div>
      </div>

      {isIncomeReport && (
        <div className="mt-5">
          <div className="flex items-center gap-2">
            <input
              id="postIncome"
              type="checkbox"
              className="h-4 w-4 rounded border-border accent-primary"
              checked={postIncome}
              onChange={(e) => setPostIncome(e.target.checked)}
            />
            <label htmlFor="postIncome" className="font-display text-base text-foreground">
              Post an income record from this document
            </label>
          </div>
          {postIncome && <IncomeRecordFields income={income} onChange={setIncome} />}
        </div>
      )}

      <Button type="button" disabled={confirming} onClick={handleConfirm} className="mt-5">
        {confirming ? 'Confirming…' : 'Confirm'}
      </Button>
    </RecordSheet>
  );
}

function ReviewQueueList({
  items,
  selectedId,
  onSelect,
}: {
  items: DocumentReviewItem[];
  selectedId: string | null;
  onSelect: (documentId: string) => void;
}) {
  if (items.length === 0) {
    return <p className="text-sm text-muted-foreground">No documents are waiting for review.</p>;
  }
  return (
    <ul className="flex flex-col gap-3">
      {items.map((item) => {
        const confidence = item.extractionConfidence === null ? null : Number(item.extractionConfidence);
        const tier = confidence === null ? null : confidenceTier(confidence);
        return (
          <li key={item.documentId}>
            <RecordSheet className={selectedId === item.documentId ? 'border-primary' : undefined}>
              <button type="button" onClick={() => onSelect(item.documentId)} className="flex w-full items-center justify-between gap-3 text-left">
                <span>
                  <span className="font-display text-foreground">{item.householdHeadName}</span>
                  <span className="ml-2 text-sm text-muted-foreground">{item.extraction?.document_type ?? item.contentType}</span>
                </span>
                {tier && <StatusPill tone={tier.tone}>{tier.label}</StatusPill>}
              </button>
            </RecordSheet>
          </li>
        );
      })}
    </ul>
  );
}

export default function DocumentReviewPage() {
  const [items, setItems] = useState<DocumentReviewItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getDocumentReviewQueue()
      .then((result) => {
        if (!cancelled) {
          setItems(result);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setError('Could not load the document review queue.');
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  function handleConfirmed(documentId: string) {
    setItems((current) => current?.filter((item) => item.documentId !== documentId) ?? current);
    setSelectedId(null);
  }

  if (error) {
    return (
      <p role="alert" className="text-sm text-destructive">
        {error}
      </p>
    );
  }

  if (items === null) {
    return <p className="text-sm text-muted-foreground">Loading the review queue…</p>;
  }

  const selected = items.find((item) => item.documentId === selectedId) ?? null;

  return (
    <section className="flex flex-col gap-6">
      <div>
        <h2 className="font-display text-xl">Document review</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Documents the intake pipeline classified, lowest confidence first. Nothing here has touched a case
          yet -- confirming is what applies it.
        </p>
      </div>

      <ReviewQueueList items={items} selectedId={selectedId} onSelect={setSelectedId} />

      {selected && <ReviewForm item={selected} onConfirmed={handleConfirmed} />}
    </section>
  );
}
