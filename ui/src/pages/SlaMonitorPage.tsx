import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { getAtRiskQueue } from '../api/client';
import type { AtRiskCaseItem } from '../api/types';
import { RecordSheet } from '@/components/design-system/RecordSheet';
import { StatusPill } from '@/components/design-system/StatusPill';
import { AiAdvisoryBadge } from '@/components/design-system/AiAdvisoryBadge';

// Read-only monitoring queue (design doc §2.4) -- unlike fraud/QC review, there is no confirm/
// dismiss action here: a supervisor is meant to act on the underlying case itself (the case
// detail page), not on this queue row.
function urgencyTone(daysRemaining: number): 'exception' | 'pending' {
  return daysRemaining <= 0 ? 'exception' : 'pending';
}

function AtRiskRow({ item }: { item: AtRiskCaseItem }) {
  const { t } = useTranslation('slaMonitor');
  return (
    <RecordSheet>
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="font-display text-lg text-foreground">{item.householdHeadName}</h3>
          <p className="mt-1 text-sm text-muted-foreground">
            {t('requestedOn', { date: item.requestedOn })}
            {item.isExpedited && <span className="ml-2">{t('expedited')}</span>}
          </p>
        </div>
        <StatusPill tone={urgencyTone(item.daysRemaining)}>
          {item.daysRemaining >= 0
            ? t('daysRemaining', { count: item.daysRemaining })
            : t('daysOverdue', { count: Math.abs(item.daysRemaining) })}
        </StatusPill>
      </div>

      <div className="mt-4">
        {item.stallReason ? (
          <>
            <AiAdvisoryBadge />
            <p className="mt-2 text-sm text-muted-foreground">{item.stallReason}</p>
          </>
        ) : (
          <p className="text-sm text-muted-foreground">{t('noReasonYet')}</p>
        )}
      </div>
    </RecordSheet>
  );
}

export default function SlaMonitorPage() {
  const { t } = useTranslation('slaMonitor');
  const [items, setItems] = useState<AtRiskCaseItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getAtRiskQueue()
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

  return (
    <section className="flex flex-col gap-6">
      <div>
        <h2 className="font-display text-xl">{t('heading')}</h2>
        <p className="mt-1 text-sm text-muted-foreground">{t('description')}</p>
      </div>

      {items.length === 0 ? (
        <p className="text-sm text-muted-foreground">{t('empty')}</p>
      ) : (
        <ul className="flex flex-col gap-3">
          {items.map((item) => (
            <li key={item.programRequestId}>
              <AtRiskRow item={item} />
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
