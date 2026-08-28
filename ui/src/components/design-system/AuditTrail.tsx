import type { AuditEventResponse } from '@/api/types';
import { RecordSheet } from './RecordSheet';
import { StatusPill } from './StatusPill';

export function AuditTrail({ events }: { events: AuditEventResponse[] }) {
  if (events.length === 0) {
    return <p className="text-sm text-muted-foreground">No audit events recorded for this case yet.</p>;
  }

  return (
    <RecordSheet className="flex flex-col gap-3">
      {events.map((event, index) => (
        <div
          key={`${event.eventType}-${event.occurredAt}-${index}`}
          className="flex items-center justify-between gap-4 border-b border-border pb-3 last:border-b-0 last:pb-0"
        >
          <div className="flex items-center gap-3">
            <StatusPill tone="neutral">{event.actorType}</StatusPill>
            <span className="text-sm text-foreground">{event.eventType}</span>
          </div>
          <span className="text-xs text-muted-foreground">{event.occurredAt}</span>
        </div>
      ))}
    </RecordSheet>
  );
}
