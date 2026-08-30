import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { confirmQcReview, dismissQcReview, getQcReviewQueue } from '../api/client';
import type { PaymentErrorReviewItem } from '../api/types';
import { Button } from '@/components/ui/button';
import { RecordSheet } from '@/components/design-system/RecordSheet';
import { StatusPill } from '@/components/design-system/StatusPill';
import { AiAdvisoryBadge } from '@/components/design-system/AiAdvisoryBadge';

function formatUsd(amount: number): string {
  return `$${amount.toFixed(2)}`;
}

function ReviewPanel({
  item,
  onDecided,
}: {
  item: PaymentErrorReviewItem;
  onDecided: (reviewId: string) => void;
}) {
  const { t } = useTranslation('qcReview');
  const [deciding, setDeciding] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleDecision(decide: (reviewId: string) => Promise<unknown>, failureMessage: string) {
    setDeciding(true);
    setError(null);
    try {
      await decide(item.id);
      onDecided(item.id);
    } catch {
      setError(failureMessage);
    } finally {
      setDeciding(false);
    }
  }

  return (
    <RecordSheet>
      <AiAdvisoryBadge />
      <h3 className="mt-2 font-display text-lg">
        {t('amounts', {
          original: formatUsd(item.originalAmount),
          reproduced: formatUsd(item.reproducedAmount),
          diff: formatUsd(item.errorAmount),
        })}
      </h3>

      {error && (
        <p role="alert" className="mt-3 text-sm text-destructive">
          {error}
        </p>
      )}

      <div className="mt-4">
        <h4 className="text-sm font-semibold text-foreground">{t('aiSummary')}</h4>
        <p className="mt-2 text-sm text-muted-foreground">{item.aiSummary ?? t('noSummaryYet')}</p>
      </div>

      <div className="mt-5 flex gap-3">
        <Button
          type="button"
          disabled={deciding}
          onClick={() => handleDecision(confirmQcReview, t('confirmError'))}
        >
          {deciding ? t('working') : t('confirmDiscrepancy')}
        </Button>
        <Button
          type="button"
          variant="outline"
          disabled={deciding}
          onClick={() => handleDecision(dismissQcReview, t('dismissError'))}
        >
          {t('dismiss')}
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
  items: PaymentErrorReviewItem[];
  selectedId: string | null;
  onSelect: (reviewId: string) => void;
}) {
  const { t } = useTranslation('qcReview');
  if (items.length === 0) {
    return <p className="text-sm text-muted-foreground">{t('empty')}</p>;
  }
  return (
    <ul className="flex flex-col gap-3">
      {items.map((item) => (
        <li key={item.id}>
          <RecordSheet className={selectedId === item.id ? 'border-primary' : undefined}>
            <button
              type="button"
              onClick={() => onSelect(item.id)}
              className="flex w-full items-center justify-between gap-3 text-left"
            >
              <span className="font-display text-foreground">{formatUsd(item.originalAmount)}</span>
              <StatusPill tone="exception">{formatUsd(item.errorAmount)}</StatusPill>
            </button>
          </RecordSheet>
        </li>
      ))}
    </ul>
  );
}

export default function QcReviewPage() {
  const { t } = useTranslation('qcReview');
  const [items, setItems] = useState<PaymentErrorReviewItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getQcReviewQueue()
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

  function handleDecided(reviewId: string) {
    setItems((current) => current?.filter((item) => item.id !== reviewId) ?? current);
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

  const selected = items.find((item) => item.id === selectedId) ?? null;

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
