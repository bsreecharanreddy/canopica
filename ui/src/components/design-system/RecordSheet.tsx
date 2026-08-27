import type { HTMLAttributes, ReactNode } from 'react';
import { cn } from '@/lib/utils';

type RecordSheetProps = { children: ReactNode; className?: string } & HTMLAttributes<HTMLDivElement>;

export function RecordSheet({ children, className, ...rest }: RecordSheetProps) {
  return (
    <div className={cn('rounded-lg border border-border bg-card px-6 py-5 shadow-sm', className)} {...rest}>
      {children}
    </div>
  );
}
