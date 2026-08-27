import type { HTMLAttributes, ReactNode } from 'react';
import { cn } from '@/lib/utils';

type RecordSheetProps = { children: ReactNode; className?: string } & HTMLAttributes<HTMLDivElement>;

export function RecordSheet({ children, className, ...rest }: RecordSheetProps) {
  return (
    <div className={cn('border-t-[3px] border-t-foreground bg-card px-6 py-5', className)} {...rest}>
      {children}
    </div>
  );
}
