import { NavLink, useMatch } from 'react-router-dom';
import { motion, useReducedMotion } from 'framer-motion';
import { useTranslation } from 'react-i18next';
import {
  AlarmClock,
  BookOpenText,
  Briefcase,
  FileCog,
  FileSearch,
  FileText,
  LayoutDashboard,
  LogOut,
  Mail,
  MessageCircleQuestion,
  ScanSearch,
  ShieldAlert,
  type LucideIcon,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import type { Role } from '@/auth/AuthContext';

const WORKER_LINKS = [
  { to: '/dashboard', labelKey: 'nav.dashboard', icon: LayoutDashboard },
  { to: '/cases', labelKey: 'nav.cases', icon: Briefcase },
  { to: '/documents/review', labelKey: 'nav.documentReview', icon: FileSearch },
  { to: '/notices/review', labelKey: 'nav.noticeReview', icon: Mail },
  // Caseworker SOP Copilot (Phase 4 Task 7) -- worker-facing, not supervisor-only, so it lives
  // on the shared WORKER_LINKS array rather than SUPERVISOR's own additions below.
  { to: '/sop-copilot', labelKey: 'nav.sopCopilot', icon: BookOpenText },
];

const LINKS_FOR: Record<Role, { to: string; labelKey: string; icon: LucideIcon }[]> = {
  CUSTOMER: [
    { to: '/apply', labelKey: 'nav.apply', icon: FileText },
    { to: '/ask', labelKey: 'nav.askAboutPolicy', icon: MessageCircleQuestion },
  ],
  WORKER: WORKER_LINKS,
  // A strict superset of WORKER's own links (SecurityConfig's own hasAnyRole("WORKER",
  // "SUPERVISOR") pattern on most case endpoints), plus the SUPERVISOR-only fraud review queue
  // (Phase 4 Task 3, design doc §2.9 -- reuses this role, no new Keycloak role), QC review queue
  // (Phase 4 Task 5, same role/reasoning), and the SLA at-risk queue (Phase 4 Task 6, same
  // role/reasoning again).
  SUPERVISOR: [
    ...WORKER_LINKS,
    { to: '/fraud/review', labelKey: 'nav.fraudReview', icon: ShieldAlert },
    { to: '/qc/review', labelKey: 'nav.qcReview', icon: ScanSearch },
    { to: '/sla/monitor', labelKey: 'nav.slaMonitor', icon: AlarmClock },
  ],
  ADMIN: [{ to: '/rule-authoring', labelKey: 'nav.ruleAuthoring', icon: FileCog }],
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
  const { t } = useTranslation('common');
  return (
    <nav aria-label="Main" className="flex h-full w-60 flex-col bg-sidebar text-sidebar-foreground">
      <div className="px-5 py-6">
        <div className="flex items-center gap-2">
          <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-white text-sm font-bold text-sidebar">
            C
          </span>
          <h1 className="font-display text-lg font-bold tracking-tight">{t('app.name')}</h1>
        </div>
        <p className="mt-1 pl-9 text-[11px] font-medium uppercase tracking-wider text-sidebar-foreground/50">
          {t('app.tagline')}
        </p>
      </div>
      <ul className="flex flex-1 flex-col gap-1 px-3">
        {LINKS_FOR[role].map((link) => (
          <NavRailLink key={link.to} to={link.to} label={t(link.labelKey)} icon={link.icon} />
        ))}
      </ul>
      <div className="flex flex-col gap-2 border-t border-white/10 px-3 py-4">
        <div className="flex items-center gap-2.5 px-3 py-1">
          <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-sidebar-active text-xs font-semibold">
            {t(`role.${role}`).charAt(0)}
          </span>
          <span className="text-sm text-sidebar-foreground/80">{t(`role.${role}`)}</span>
        </div>
        <Button
          variant="ghost"
          size="sm"
          onClick={onSignOut}
          className="justify-start gap-2.5 px-3 text-sidebar-foreground/70 hover:bg-white/5 hover:text-sidebar-foreground"
        >
          <LogOut aria-hidden="true" className="h-4 w-4" />
          {t('nav.signOut')}
        </Button>
      </div>
    </nav>
  );
}
