import { NavLink, useMatch } from 'react-router-dom';
import { motion, useReducedMotion } from 'framer-motion';
import { cn } from '@/lib/utils';
import type { Role } from '@/auth/AuthContext';

const LINKS_FOR: Record<Role, { to: string; label: string }[]> = {
  CUSTOMER: [
    { to: '/apply', label: 'Apply' },
    { to: '/ask', label: 'Ask about policy' },
  ],
  WORKER: [{ to: '/cases', label: 'Cases' }],
  ADMIN: [{ to: '/rule-authoring', label: 'Rule authoring' }],
};

function NavRailLink({ to, label }: { to: string; label: string }) {
  const isActive = Boolean(useMatch(to));
  const reduceMotion = useReducedMotion();
  return (
    <li className="relative">
      {isActive && (
        <motion.span
          layoutId="nav-active"
          className="absolute inset-0 rounded-sm bg-primary/20"
          transition={reduceMotion ? { duration: 0 } : { duration: 0.18 }}
        />
      )}
      <NavLink
        to={to}
        className={cn(
          'relative block px-3 py-2 text-sm',
          isActive ? 'text-sidebar-foreground' : 'text-sidebar-foreground/80 hover:bg-white/5',
        )}
      >
        {label}
      </NavLink>
    </li>
  );
}

function BrandMark() {
  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 24 24"
      className="h-6 w-6 shrink-0 rounded-sm bg-sidebar-foreground/10 p-1 text-primary"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
    >
      <path d="M5 3.5h11l3 3V20a.5.5 0 0 1-.5.5h-13A.5.5 0 0 1 5 20V3.5Z" />
      <path d="M16 3.5V6a.5.5 0 0 0 .5.5H19" />
      <path d="M8 12h8M8 15h8M8 9h4" strokeLinecap="round" />
    </svg>
  );
}

export function NavRail({ role }: { role: Role }) {
  return (
    <nav aria-label="Main" className="flex h-full w-56 flex-col bg-sidebar text-sidebar-foreground">
      <div className="flex items-center gap-2 px-5 py-6">
        <BrandMark />
        <h1 className="font-display text-lg tracking-wide">Canopica</h1>
      </div>
      <ul className="flex flex-col gap-1 px-3">
        {LINKS_FOR[role].map((link) => (
          <NavRailLink key={link.to} to={link.to} label={link.label} />
        ))}
      </ul>
    </nav>
  );
}
