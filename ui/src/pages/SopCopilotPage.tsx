import { useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { askSopCopilot } from '../api/client';
import type { SopAnswer } from '../api/types';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { FormField } from '@/components/design-system/FormField';
import { AiAdvisoryBadge } from '@/components/design-system/AiAdvisoryBadge';

function AnswerPanel({ answer }: { answer: SopAnswer }) {
  const { t } = useTranslation('sopCopilot');
  if (answer.abstained) {
    // Rendered distinctly from a real answer (design doc §2.5) -- same discipline
    // PolicyQaPage's own AnswerPanel already establishes for a different capability.
    return (
      <output className="block rounded-md border border-amber bg-amber px-4 py-3 text-amber-foreground">
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
          <h3 className="mt-3 font-display text-sm">{t('citations')}</h3>
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

export default function SopCopilotPage() {
  const { t } = useTranslation('sopCopilot');
  const [question, setQuestion] = useState('');
  const [answer, setAnswer] = useState<SopAnswer | null>(null);
  const [asking, setAsking] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleAsk(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setAsking(true);
    setError(null);
    try {
      setAnswer(await askSopCopilot(question));
    } catch {
      setError(t('error'));
    } finally {
      setAsking(false);
    }
  }

  return (
    <section className="flex flex-col gap-6">
      <div>
        <h2 className="font-display text-xl">{t('heading')}</h2>
        <p className="mt-1 text-sm text-muted-foreground">{t('description')}</p>
      </div>

      <form onSubmit={handleAsk} className="flex flex-col gap-4">
        {error && (
          <p role="alert" className="text-sm text-destructive">
            {error}
          </p>
        )}
        <FormField id="question" label={t('question.label')}>
          <Input id="question" value={question} onChange={(e) => setQuestion(e.target.value)} />
        </FormField>
        <Button type="submit" disabled={asking || !question} className="self-start">
          {asking ? t('question.asking') : t('question.submit')}
        </Button>
      </form>
      {answer && <AnswerPanel answer={answer} />}
    </section>
  );
}
