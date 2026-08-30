import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { clearFraudRisk, confirmFraudRisk, getFraudReviewQueue } from '../api/client';
import type { FraudRiskScoreItem } from '../api/types';
import { Button } from '@/components/ui/button';
import { RecordSheet } from '@/components/design-system/RecordSheet';
import { StatusPill } from '@/components/design-system/StatusPill';
import { AiAdvisoryBadge } from '@/components/design-system/AiAdvisoryBadge';

// Structured display, not free text (design doc §2.12) -- each contributing feature is its own
// row with a name and a numeric z-score, the same "don't let a model narrate its own evidence"
// discipline ValidationSummary's own errors list already follows for NoticeReviewPage.
function TopFeaturesList({ item }: { item: FraudRiskScoreItem }) {
  const { t } = useTranslation('fraudReview');
  return (
    <div className="mt-4">
      <h4 className="text-sm font-semibold text-foreground">{t('topFeatures')}</h4>
      <ul className="mt-2 flex flex-col gap-1 text-sm text-muted-foreground">
        {item.topContributingFeatures.map((feature) => (
          <li key={feature.feature}>
            {t('featureZScore', { feature: feature.feature, zScore: feature.z_score.toFixed(2) })}
          </li>
        ))}
      </ul>
    </div>
  );
}

function ReviewPanel({
  item,
  onDecided,
}: {
  item: FraudRiskScoreItem;
  onDecided: (scoreId: string) => void;
}) {
  const { t } = useTranslation('fraudReview');
  const [deciding, setDeciding] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleDecision(decide: (scoreId: string) => Promise<unknown>, failureMessage: string) {
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
      <h3 className="mt-2 font-display text-lg">{t('scoreHeading', { score: item.score.toFixed(2) })}</h3>
      <p className="mt-1 text-sm text-muted-foreground">{t('scoredBy', { model: item.modelVersion })}</p>

      {error && (
        <p role="alert" className="mt-3 text-sm text-destructive">
          {error}
        </p>
      )}

      <TopFeaturesList item={item} />

      <div className="mt-5 flex gap-3">
        <Button
          type="button"
          disabled={deciding}
          onClick={() => handleDecision(confirmFraudRisk, t('confirmError'))}
        >
          {deciding ? t('working') : t('confirmRisk')}
        </Button>
        <Button
          type="button"
          variant="outline"
          disabled={deciding}
          onClick={() => handleDecision(clearFraudRisk, t('clearError'))}
        >
          {t('clear')}
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
  items: FraudRiskScoreItem[];
  selectedId: string | null;
  onSelect: (scoreId: string) => void;
}) {
  const { t } = useTranslation('fraudReview');
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
              <span className="font-display text-foreground">{item.modelVersion}</span>
              <StatusPill tone="exception">{t('scoreHeading', { score: item.score.toFixed(2) })}</StatusPill>
            </button>
          </RecordSheet>
        </li>
      ))}
    </ul>
  );
}

export default function FraudReviewPage() {
  const { t } = useTranslation('fraudReview');
  const [items, setItems] = useState<FraudRiskScoreItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getFraudReviewQueue()
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

  function handleDecided(scoreId: string) {
    setItems((current) => current?.filter((item) => item.id !== scoreId) ?? current);
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
