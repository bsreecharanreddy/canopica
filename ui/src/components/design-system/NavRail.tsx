import { NavLink, useMatch } from 'react-router-dom';
import { motion, useReducedMotion } from 'framer-motion';
import {
  Briefcase,
  FileCog,
  FileSearch,
  FileText,
  LayoutDashboard,
  LogOut,
  Mail,
  MessageCircleQuestion,
  type LucideIcon,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import type { Role } from '@/auth/AuthContext';

const LINKS_FOR: Record<Role, { to: string; label: string; icon: LucideIcon }[]> = {
  CUSTOMER: [
    { to: '/apply', label: 'Apply', icon: FileText },
    { to: '/ask', label: 'Ask about policy', icon: MessageCircleQuestion },
  ],
  WORKER: [
    { to: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
    { to: '/cases', label: 'Cases', icon: Briefcase },
    { to: '/documents/review', label: 'Document review', icon: FileSearch },
    { to: '/notices/review', label: 'Notice review', icon: Mail },
  ],
  ADMIN: [{ to: '/rule-authoring', label: 'Rule authoring', icon: FileCog }],
};

const ROLE_LABEL: Record<Role, string> = {
  CUSTOMER: 'Applicant',
  WORKER: 'Caseworker',
  ADMIN: 'Administrator',
};

function NavRailLink({ to, label, icon: Icon }: { to: string; label: string; icon: LucideIcon }) {
  const isActive = Boolean(useMatch(to));
  const reduceMotion = useReducedMotion();
  return (
    <li className="relative">
      {isActive && (
        <motion.span
          layoutId="nav-active"
          className="absolute inset-0 rounded-md bg-sidebar-active"
          transition={reduceMotion ? { duration: 0 } : { duration: 0.18 }}
        />
      )}
      <NavLink
        to={to}
        className={cn(
          'relative flex items-center gap-2.5 px-3 py-2 text-sm font-medium',
          isActive ? 'text-sidebar-foreground' : 'text-sidebar-foreground/70 hover:text-sidebar-foreground',
        )}
      >
        <Icon aria-hidden="true" className="h-4 w-4 shrink-0" />
        {label}
      </NavLink>
    </li>
  );
}

export function NavRail({ role, onSignOut }: { role: Role; onSignOut: () => void }) {
  return (
    <nav aria-label="Main" className="flex h-full w-60 flex-col bg-sidebar text-sidebar-foreground">
      <div className="px-5 py-6">
        <div className="flex items-center gap-2">
          <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-white text-sm font-bold text-sidebar">
            C
          </span>
          <h1 className="font-display text-lg font-bold tracking-tight">Canopica</h1>
        </div>
        <p className="mt-1 pl-9 text-[11px] font-medium uppercase tracking-wider text-sidebar-foreground/50">
          Benefits Platform
        </p>
      </div>
      <ul className="flex flex-1 flex-col gap-1 px-3">
        {LINKS_FOR[role].map((link) => (
          <NavRailLink key={link.to} to={link.to} label={link.label} icon={link.icon} />
        ))}
      </ul>
      <div className="flex flex-col gap-2 border-t border-white/10 px-3 py-4">
        <div className="flex items-center gap-2.5 px-3 py-1">
          <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-sidebar-active text-xs font-semibold">
            {ROLE_LABEL[role].charAt(0)}
          </span>
          <span className="text-sm text-sidebar-foreground/80">{ROLE_LABEL[role]}</span>
        </div>
        <Button
          variant="ghost"
          size="sm"
          onClick={onSignOut}
          className="justify-start gap-2.5 px-3 text-sidebar-foreground/70 hover:bg-white/5 hover:text-sidebar-foreground"
        >
          <LogOut aria-hidden="true" className="h-4 w-4" />
          Sign out
        </Button>
      </div>
    </nav>
  );
}
