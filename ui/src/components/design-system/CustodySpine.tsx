import { motion, useReducedMotion } from 'framer-motion';

export type CustodySpineItem = { label: string; value: string };

export function CustodySpine({ items }: { items: CustodySpineItem[] }) {
  const reduceMotion = useReducedMotion();
  return (
    <ol aria-label="DMN decisions in evaluation order" className="relative pl-4">
      <motion.span
        aria-hidden="true"
        className="absolute left-0 top-0 h-full w-px origin-top bg-border"
        initial={reduceMotion ? false : { scaleY: 0 }}
        animate={{ scaleY: 1 }}
        transition={{ duration: 0.2 }}
      />
      {items.map((item) => (
        <li key={item.label} className="relative pb-3 last:pb-0">
          <span
            className="absolute -left-[21px] top-1 h-2 w-2 rounded-full border border-primary bg-card"
            aria-hidden="true"
          />
          <strong className="text-sm text-foreground">{item.label}:</strong>{' '}
          <span className="text-sm text-muted-foreground">{item.value}</span>
        </li>
      ))}
    </ol>
  );
}
