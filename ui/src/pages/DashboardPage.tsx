import { useEffect, useState } from 'react';
import { getCaseloadStats } from '../api/client';
import type { CaseloadStatsResponse } from '../api/types';
import { AuditTrail } from '@/components/design-system/AuditTrail';
import { StatTile } from '@/components/design-system/StatTile';

export default function DashboardPage() {
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
          setLoadError('Could not load your caseload stats.');
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (loadError) {
    return (
      <p role="alert" className="text-sm text-destructive">
        {loadError}
      </p>
    );
  }

  if (!stats) {
    return <p className="text-sm text-muted-foreground">Loading dashboard…</p>;
  }

  return (
    <div className="flex flex-col gap-6">
      <h2 className="font-display text-xl">Dashboard</h2>

      <div className="grid grid-cols-2 gap-4">
        <StatTile label="Active cases" value={stats.activeCases} />
        <StatTile label="Pending determination" value={stats.pendingDetermination} />
      </div>

      <div>
        <h3 className="font-display text-lg">Recent activity</h3>
        <div className="mt-3">
          <AuditTrail events={stats.recentEvents} />
        </div>
      </div>
    </div>
  );
}
