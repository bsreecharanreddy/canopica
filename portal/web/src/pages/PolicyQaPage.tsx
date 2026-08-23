import { useState, type FormEvent } from 'react';
import { askPolicyQuestion, askWhyWasIDenied } from '../api/client';
import type { QaAnswer } from '../api/types';

function AnswerPanel({ answer }: { answer: QaAnswer }) {
  if (answer.abstained) {
    // Rendered distinctly from a real answer (design doc §2.2) -- a
    // low-confidence guess and a grounded answer must never look the same
    // to the person reading it.
    return <output className="qa-abstention">{answer.answer}</output>;
  }
  return (
    <output>
      <p>{answer.answer}</p>
      {answer.citations.length > 0 && (
        <>
          <h3>Citations</h3>
          <ul>
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
    <section>
      <h2>Ask about SNAP policy</h2>

      <form onSubmit={handleAsk}>
        {askError && <p role="alert">{askError}</p>}
        <label htmlFor="question">Your question</label>
        <input id="question" value={question} onChange={(e) => setQuestion(e.target.value)} />
        <button type="submit" disabled={asking || !question}>
          Ask
        </button>
      </form>
      {answer && <AnswerPanel answer={answer} />}

      <h3>Why was I denied?</h3>
      <form onSubmit={handleExplainDenial}>
        {denialError && <p role="alert">{denialError}</p>}
        <label htmlFor="determinationId">Determination ID</label>
        <input
          id="determinationId"
          value={determinationId}
          onChange={(e) => setDeterminationId(e.target.value)}
        />
        <button type="submit" disabled={explaining || !determinationId}>
          Explain this determination
        </button>
      </form>
      {denialAnswer && <AnswerPanel answer={denialAnswer} />}
    </section>
  );
}
