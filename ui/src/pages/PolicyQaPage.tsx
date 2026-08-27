import { useState, type FormEvent } from 'react';
import { askPolicyQuestion, askWhyWasIDenied } from '../api/client';
import type { QaAnswer } from '../api/types';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { FormField } from '@/components/design-system/FormField';
import { AiAdvisoryBadge } from '@/components/design-system/AiAdvisoryBadge';

function AnswerPanel({ answer }: { answer: QaAnswer }) {
  if (answer.abstained) {
    // Rendered distinctly from a real answer (design doc §2.2) -- a
    // low-confidence guess and a grounded answer must never look the same
    // to the person reading it.
    return (
      <output className="qa-abstention block rounded-md border border-amber bg-amber px-4 py-3 text-amber-foreground">
        {answer.answer}
      </output>
    );
  }
  return (
    <output className="block rounded-md border border-border bg-card px-4 py-3">
      <AiAdvisoryBadge />
      <p className="mt-2 text-foreground">{answer.answer}</p>
      {answer.citations.length > 0 && (
        <>
          <h3 className="mt-3 font-display text-sm">Citations</h3>
          <ul className="mt-1 list-inside list-disc text-sm text-muted-foreground">
            {answer.citations.map((citation) => (
              <li key={citation}>{citation}</li>
            ))}
          </ul>
        </>
      )}
    </output>
  );
}

export default function PolicyQaPage() {
  const [question, setQuestion] = useState('');
  const [answer, setAnswer] = useState<QaAnswer | null>(null);
  const [asking, setAsking] = useState(false);
  const [askError, setAskError] = useState<string | null>(null);

  const [determinationId, setDeterminationId] = useState('');
  const [denialAnswer, setDenialAnswer] = useState<QaAnswer | null>(null);
  const [explaining, setExplaining] = useState(false);
  const [denialError, setDenialError] = useState<string | null>(null);

  async function handleAsk(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setAsking(true);
    setAskError(null);
    try {
      setAnswer(await askPolicyQuestion(question));
    } catch {
      setAskError('Could not get an answer right now. Please try again.');
    } finally {
      setAsking(false);
    }
  }

  async function handleExplainDenial(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setExplaining(true);
    setDenialError(null);
    try {
      setDenialAnswer(await askWhyWasIDenied(determinationId));
    } catch {
      setDenialError('Could not explain this determination right now. Please try again.');
    } finally {
      setExplaining(false);
    }
  }

  return (
    <section className="flex flex-col gap-6">
      <h2 className="font-display text-xl">Ask about SNAP policy</h2>

      <form onSubmit={handleAsk} className="flex flex-col gap-4">
        {askError && (
          <p role="alert" className="text-sm text-destructive">
            {askError}
          </p>
        )}
        <FormField id="question" label="Your question">
          <Input id="question" value={question} onChange={(e) => setQuestion(e.target.value)} />
        </FormField>
        <Button type="submit" disabled={asking || !question} className="self-start">
          {asking ? 'Asking…' : 'Ask'}
        </Button>
      </form>
      {answer && <AnswerPanel answer={answer} />}

      <h3 className="font-display text-lg">Why was I denied?</h3>
      <form onSubmit={handleExplainDenial} className="flex flex-col gap-4">
        {denialError && (
          <p role="alert" className="text-sm text-destructive">
            {denialError}
          </p>
        )}
        <FormField id="determinationId" label="Determination ID">
          <Input
            id="determinationId"
            value={determinationId}
            onChange={(e) => setDeterminationId(e.target.value)}
          />
        </FormField>
        <Button type="submit" disabled={explaining || !determinationId} className="self-start">
          {explaining ? 'Explaining…' : 'Explain this determination'}
        </Button>
      </form>
      {denialAnswer && <AnswerPanel answer={denialAnswer} />}
    </section>
  );
}
