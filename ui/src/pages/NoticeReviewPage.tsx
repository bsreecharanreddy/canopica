import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { approveNotice, getNoticeReviewQueue, rejectNotice } from '../api/client';
import type { NoticeReviewItem } from '../api/types';
import { Button } from '@/components/ui/button';
import { RecordSheet } from '@/components/design-system/RecordSheet';
import { StatusPill } from '@/components/design-system/StatusPill';
import { AiAdvisoryBadge } from '@/components/design-system/AiAdvisoryBadge';

// Not color alone (this project's accessibility bar, Phase 1b onward): the pre-check's own pass/fail carries
// a text label alongside its StatusPill tone, same reasoning DocumentReviewPage's own confidenceTier uses.
function ValidationSummary({ item }: { item: NoticeReviewItem }) {
  const { t } = useTranslation('noticeReview');
  if (item.validationResult.passed) {
    return <StatusPill tone="affirmed">{t('precheck.passed')}</StatusPill>;
  }
  return (
    <div>
      <StatusPill tone="exception">{t('precheck.failed')}</StatusPill>
      <ul className="mt-2 flex flex-col gap-1 text-sm text-destructive">
        {item.validationResult.errors.map((error, index) => (
          // The deterministic pre-check's own errors have no stable id of their own -- combining with
          // index is safe here since this list is never reordered or edited, only rendered once per notice.
          <li key={`${index}-${error}`}>{error}</li>
        ))}
      </ul>
    </div>
  );
}

function ReviewPanel({ item, onDecided }: { item: NoticeReviewItem; onDecided: (noticeId: string) => void }) {
  const { t } = useTranslation('noticeReview');
  const [deciding, setDeciding] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleDecision(decide: (noticeId: string) => Promise<unknown>, failureMessage: string) {
    setDeciding(true);
    setError(null);
    try {
      await decide(item.noticeId);
      onDecided(item.noticeId);
    } catch {
      setError(failureMessage);
    } finally {
      setDeciding(false);
    }
  }

  return (
    <RecordSheet>
      <AiAdvisoryBadge />
      <h3 className="mt-2 font-display text-lg">{t('noticeHeading', { type: t(`type.${item.noticeType}`) })}</h3>
      <p className="mt-1 text-sm text-muted-foreground">
        {t('draftedBy', { model: item.generationModel, promptVersion: item.promptVersion })}
      </p>

      {error && (
        <p role="alert" className="mt-3 text-sm text-destructive">
          {error}
        </p>
      )}

      <div className="mt-4">
        <ValidationSummary item={item} />
      </div>

      <pre className="mt-4 whitespace-pre-wrap rounded-md border border-border bg-muted p-4 text-sm text-foreground">
        {item.content}
      </pre>

      <div className="mt-5 flex gap-3">
        <Button
          type="button"
          disabled={deciding}
          onClick={() => handleDecision(approveNotice, t('approveError'))}
        >
          {deciding ? t('working') : t('approveAndSend')}
        </Button>
        <Button
          type="button"
          variant="outline"
          disabled={deciding}
          onClick={() => handleDecision(rejectNotice, t('rejectError'))}
        >
          {t('reject')}
        </Button>
      </div>
    </RecordSheet>
  );
}

function ReviewQueueList({
  items,
  selectedId,
  onSelect,
}: {
  items: NoticeReviewItem[];
  selectedId: string | null;
  onSelect: (noticeId: string) => void;
}) {
  const { t } = useTranslation('noticeReview');
  if (items.length === 0) {
    return <p className="text-sm text-muted-foreground">{t('empty')}</p>;
  }
  return (
    <ul className="flex flex-col gap-3">
      {items.map((item) => (
        <li key={item.noticeId}>
          <RecordSheet className={selectedId === item.noticeId ? 'border-primary' : undefined}>
            <button
              type="button"
              onClick={() => onSelect(item.noticeId)}
              className="flex w-full items-center justify-between gap-3 text-left"
            >
              <span className="font-display text-foreground">{t(`type.${item.noticeType}`)}</span>
              {!item.validationResult.passed && <StatusPill tone="exception">{t('precheck.failed')}</StatusPill>}
            </button>
          </RecordSheet>
        </li>
      ))}
    </ul>
  );
}

export default function NoticeReviewPage() {
  const { t } = useTranslation('noticeReview');
  const [items, setItems] = useState<NoticeReviewItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getNoticeReviewQueue()
      .then((result) => {
        if (!cancelled) {
          setItems(result);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setError(t('loadError'));
        }
      });
    return () => {
      cancelled = true;
    };
  }, [t]);

  function handleDecided(noticeId: string) {
    setItems((current) => current?.filter((item) => item.noticeId !== noticeId) ?? current);
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
    return <p className="text-sm text-muted-foreground">{t('loading')}</p>;
  }

  const selected = items.find((item) => item.noticeId === selectedId) ?? null;

  return (
    <section className="flex flex-col gap-6">
      <div>
        <h2 className="font-display text-xl">{t('heading')}</h2>
        <p className="mt-1 text-sm text-muted-foreground">{t('description')}</p>
      </div>

      <ReviewQueueList items={items} selectedId={selectedId} onSelect={setSelectedId} />

      {selected && <ReviewPanel item={selected} onDecided={handleDecided} />}
    </section>
  );
}
