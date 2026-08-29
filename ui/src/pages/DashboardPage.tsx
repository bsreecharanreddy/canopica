import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { getCaseloadStats } from '../api/client';
import type { CaseloadStatsResponse } from '../api/types';
import { AuditTrail } from '@/components/design-system/AuditTrail';
import { StatTile } from '@/components/design-system/StatTile';

export default function DashboardPage() {
  const { t } = useTranslation('dashboard');
  const [stats, setStats] = useState<CaseloadStatsResponse | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getCaseloadStats()
      .then((result) => {
        if (!cancelled) {
          setStats(result);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setLoadError(t('loadError'));
        }
      });
    return () => {
      cancelled = true;
    };
  }, [t]);

  if (loadError) {
    return (
      <p role="alert" className="text-sm text-destructive">
        {loadError}
      </p>
    );
  }

  if (!stats) {
    return <p className="text-sm text-muted-foreground">{t('loading')}</p>;
  }

  return (
    <div className="flex flex-col gap-6">
      <h2 className="font-display text-xl">{t('heading')}</h2>

      <div className="grid grid-cols-2 gap-4">
        <StatTile label={t('activeCases')} value={stats.activeCases} />
        <StatTile label={t('pendingDetermination')} value={stats.pendingDetermination} />
      </div>

      <div>
        <h3 className="font-display text-lg">{t('recentActivity')}</h3>
        <div className="mt-3">
          <AuditTrail events={stats.recentEvents} />
        </div>
      </div>
    </div>
  );
}
