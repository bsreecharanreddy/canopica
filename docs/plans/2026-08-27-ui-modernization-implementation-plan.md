# UI Modernization — Public Ledger Design System: Implementation Plan

> **For agentic workers:** Steps use checkbox (`- [ ]`) syntax for tracking.
> Execute tasks in order, one commit per completed task, `docs/STATUS.md`
> updated in that same commit (CLAUDE.md, "Conventions"). Run the
> `canopica-task-checkpoint` skill's gate (`make test`, `make lint`,
> STATUS.md, one commit) after every task.

**Goal:** Apply the "Public Ledger" design system to `ui/`'s 5 real pages
on a Tailwind v4 + shadcn/ui foundation, replacing today's fully unstyled
markup — with zero change to any component's logic, handlers, or API
surface.

**Architecture:** One foundation task builds the design tokens, the app
shell (`NavRail` + `TopUtilityBar`), and a small set of shared primitives.
Each of the 5 pages then gets its own migration task — a pure restyle,
verified by its existing test file passing unmodified.

**Tech Stack:** Tailwind CSS v4 (`@tailwindcss/vite`), shadcn/ui
(`Button`/`Input`/`Textarea`/`Label`, generated as owned source, not an
npm runtime dependency), Framer Motion, `@fontsource` for DM Serif
Display + DM Sans (self-hosted, no runtime Google Fonts request).

**Spec:** `docs/design/2026-08-27-ui-modernization-public-ledger.md` (the
approved design doc this plan implements — read it first; this plan
assumes every decision in it as settled and doesn't re-derive them).

## Global Constraints

Everything CLAUDE.md's testing policy and conventions already require
still applies (full suite before every push; one commit per task with
`docs/STATUS.md` in the same commit; changes stay scoped to the task at
hand). This plan adds:

1. **No Manus code, config, or CSS file is imported or copied wholesale.**
   Every token value below was independently re-set as this app's own
   token (design doc §2/§5) — verified by hand (contrast ratios below),
   not assumed from the source.
2. **No dark-mode theme.** shadcn's default scaffold includes a `.dark`
   variant; Public Ledger is a light, warm-paper design only (design doc
   §4). Don't add a theme switcher.
3. **Every migrated page's existing `vitest-axe` assertion keeps
   passing against the new markup** (design doc §7). A task isn't done
   until it does.
4. **WCAG AA contrast (4.5:1 normal text) is enforced by an automated
   test**, not asserted from a screenshot (design doc §7) — Task 1's
   `contrast.test.ts`, using real values computed and checked below, not
   assumed from the source palette.
5. **Motion respects `prefers-reduced-motion`, and never animates a
   dollar amount or a determination's own value** (CLAUDE.md's governing
   principle; design doc §7).
6. **Every migration task is a restyle, not a rewrite.** State,
   handlers, prop shapes, and API calls in existing components are
   copied unchanged; only the returned JSX changes. `api/client.ts` and
   `api/types.ts` are not modified by this plan.
7. **Native `<select>` and native `<input type="checkbox">` elements are
   kept, styled with Tailwind utility classes directly — not swapped for
   shadcn's Radix-based `Select`/`Checkbox`.** Both of those wrap native
   form semantics in a custom widget (a `<button role="checkbox">`, a
   portal-rendered listbox) that would change how `userEvent`/Testing
   Library interacts with them, for zero visual necessity Tailwind
   classes on the native element don't already cover. This is why
   `select.tsx`/`checkbox.tsx` are deliberately not in Task 1's shadcn
   additions below.

### New dependencies this plan adds

| Component | Choice | Why |
|---|---|---|
| CSS framework | `tailwindcss` v4 + `@tailwindcss/vite` | Design doc §5 |
| Component primitives | shadcn/ui CLI-generated (`button`, `input`, `textarea`, `label`) — owned source in `src/components/ui/`, not an npm package | Design doc §5; constraint 7 above narrows the set |
| Motion | `framer-motion` | Design doc §5/§7 |
| Motion utility classes | `tw-animate-css` | Matches the reference exploration's own stack |
| Fonts | `@fontsource/dm-serif-display`, `@fontsource-variable/dm-sans` | Design doc §5 — self-hosted, no runtime Google Fonts request |
| Class merging | `clsx`, `tailwind-merge` (shadcn's own `cn` helper dependency) | Installed automatically by the shadcn CLI |

## File structure (additions and modifications only)

```
canopica/
  ui/
    components.json                                <- Task 1 (shadcn config)
    package.json                                    <- modified: Task 1
    vite.config.ts                                  <- modified: Task 1 (+@tailwindcss/vite, +@ alias)
    tsconfig.app.json                               <- modified: Task 1 (+@/* path)
    src/
      index.css                                     <- Task 1 (new: Public Ledger tokens + Tailwind v4 @theme)
      main.tsx                                       <- modified: Task 1 (+font imports, +./index.css)
      App.tsx                                        <- modified: Task 1 (shell uses NavRail/TopUtilityBar)
      auth/AuthContext.tsx                           <- modified: Task 1 (export the Role type)
      test/setup.ts                                  <- modified: Task 1 (+matchMedia polyfill)
      lib/utils.ts                                   <- Task 1 (shadcn `cn` helper)
      design/contrast.ts                             <- Task 1
      design/contrast.test.ts                        <- Task 1
      components/
        ui/button.tsx                                <- Task 1 (shadcn-generated)
        ui/input.tsx                                 <- Task 1 (shadcn-generated)
        ui/textarea.tsx                              <- Task 1 (shadcn-generated)
        ui/label.tsx                                 <- Task 1 (shadcn-generated)
        design-system/NavRail.tsx                    <- Task 1
        design-system/NavRail.test.tsx               <- Task 1
        design-system/TopUtilityBar.tsx              <- Task 1
        design-system/RecordSheet.tsx                <- Task 1
        design-system/StatusPill.tsx                 <- Task 1
        design-system/StatusPill.test.tsx            <- Task 1
        design-system/DecisionBar.tsx                <- Task 1
        design-system/CustodySpine.tsx               <- Task 1
        design-system/FormField.tsx                  <- Task 1
        HouseholdMemberFields.tsx                    <- modified: Task 2
        IncomeFields.tsx                             <- modified: Task 2
        ExpenseFields.tsx                             <- modified: Task 2
        DeterminationPanel.tsx                        <- modified: Task 5
        TracePanel.tsx                                <- modified: Task 5
      pages/
        IntakePage.tsx                                <- modified: Task 2
        PolicyQaPage.tsx                              <- modified: Task 3
        WorkerCasesPage.tsx                            <- modified: Task 4
        CaseDetailPage.tsx                             <- modified: Task 5
        RuleAuthoringPage.tsx                          <- modified: Task 6
  docs/STATUS.md                                       <- modified: every task
```

## Task list

| # | Task | Deliverable |
|---|---|---|
| 1 | Tailwind + shadcn/ui foundation, tokens, and the app shell | Design tokens live and contrast-verified; `NavRail`/`TopUtilityBar` replace the plain header/nav; shared primitives ready for pages to consume |
| 2 | Migrate `IntakePage` | Applicant's form restyled with `FormField`/shadcn primitives; `IntakePage.test.tsx` passes unmodified |
| 3 | Migrate `PolicyQaPage` | Q&A restyled; abstention visually distinct from a grounded answer (design doc §3's evidence-first principle, made real) |
| 4 | Migrate `WorkerCasesPage` | Case list restyled in place, `StatusPill` for status |
| 5 | Migrate `CaseDetailPage` (+ `DeterminationPanel`, `TracePanel`) | `DecisionBar` + `CustodySpine` — the design system's signature elements, live |
| 6 | Migrate `RuleAuthoringPage` | Last page; already-refactored sub-components (`PendingProposalsList`, `ProposalReview`, `ReviewedStatusBanner`) each get the same primitives |

The design doc left exact migration order to this plan (§9). Order chosen:
walk each role's screens in the order that role actually encounters them
— `CUSTOMER`'s two pages first (`IntakePage` is also literally the first
screen a `CUSTOMER` lands on, and the simplest page, so it's the
lowest-risk first real proof after the foundation), then `WORKER`'s two
pages in the order a worker would click through them (case list → case
detail), then `ADMIN`'s one page last, since it's already the most
structurally complex (the just-completed cyclomatic-complexity refactor)
and benefits from every primitive already being proven on four other
pages first.

---

## Task 1: Tailwind + shadcn/ui foundation, tokens, and the app shell

**Files:**
- Create: `components.json`, `src/index.css`, `src/lib/utils.ts`
- Create: `src/design/contrast.ts`, `src/design/contrast.test.ts`
- Create: `src/components/ui/{button,input,textarea,label}.tsx`
- Create: `src/components/design-system/{NavRail,TopUtilityBar,RecordSheet,StatusPill,DecisionBar,CustodySpine,FormField}.tsx`
- Create: `src/components/design-system/NavRail.test.tsx`, `StatusPill.test.tsx`
- Modify: `package.json`, `vite.config.ts`, `tsconfig.app.json`, `src/main.tsx`, `src/App.tsx`, `src/auth/AuthContext.tsx`

**Interfaces:**
- Produces: `cn(...inputs: ClassValue[]): string` (`src/lib/utils.ts`) —
  every later primitive uses this to merge Tailwind classes.
- Produces: `contrastRatio(hexA: string, hexB: string): number`
  (`src/design/contrast.ts`).
- Produces: `NavRail({ role: Role }): JSX.Element`,
  `TopUtilityBar({ role: Role, onSignOut: () => void }): JSX.Element`
  (`Role` now exported from `src/auth/AuthContext.tsx`).
- Produces: `RecordSheet({ children: ReactNode, className?: string } & HTMLAttributes<HTMLDivElement>)`,
  `StatusPill({ tone: 'affirmed' | 'exception' | 'pending' | 'neutral', children: ReactNode })`,
  `DecisionBar({ amount: string, policyVersion: string, note: ReactNode })`,
  `CustodySpine({ items: { label: string, value: string }[] })`,
  `FormField({ id: string, label: string, error?: string, children: ReactNode })`
  — every one of these is what Tasks 2–6 import.
- Consumes: `react-router-dom`'s `NavLink` (already a dependency).

- [ ] **Step 1: Install dependencies, configure the `@` path alias.**

  ```bash
  npm install tailwindcss @tailwindcss/vite tw-animate-css framer-motion \
    @fontsource/dm-serif-display @fontsource-variable/dm-sans clsx tailwind-merge
  ```

  Edit `vite.config.ts`:

  ```ts
  /// <reference types="vitest/config" />
  import path from 'node:path';
  import { defineConfig } from 'vite';
  import react from '@vitejs/plugin-react';
  import tailwindcss from '@tailwindcss/vite';

  export default defineConfig({
    plugins: [react(), tailwindcss()],
    resolve: {
      alias: { '@': path.resolve(__dirname, './src') },
    },
    server: {
      port: 3000,
      proxy: { '/api': 'http://localhost:8080' },
    },
    test: {
      environment: 'jsdom',
      globals: true,
      setupFiles: './src/test/setup.ts',
    },
  });
  ```

  Edit `tsconfig.app.json`'s `compilerOptions`, adding:

  ```json
  "baseUrl": ".",
  "paths": { "@/*": ["./src/*"] }
  ```

  `framer-motion`'s `useReducedMotion` (used by `NavRail` in Step 4 and
  `CustodySpine` in Task 5) calls `window.matchMedia` internally, which
  jsdom doesn't implement — every test that renders either component
  would crash with `TypeError: window.matchMedia is not a function`
  otherwise. Add a polyfill to `src/test/setup.ts` now, before it's
  needed:

  ```ts
  import '@testing-library/jest-dom/vitest';
  import 'vitest-axe/extend-expect';

  // framer-motion's useReducedMotion() calls window.matchMedia, which
  // jsdom doesn't implement. Always reports "no preference" in tests --
  // deterministic, and no test in this suite asserts on animation state.
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: (query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    }),
  });
  ```

- [ ] **Step 2: Author the design tokens (`src/index.css`), then lock
      their contrast in with a test.**

  Write the failing test first — `src/design/contrast.test.ts`:

  ```ts
  import { describe, expect, test } from 'vitest';
  import { contrastRatio } from './contrast';

  // Real Public Ledger token pairs from src/index.css. 4.5:1 is WCAG AA
  // for normal text (§1.4.3) -- every pairing actually used for body or
  // label text must clear it, not just look plausible. These values were
  // hand-computed before being chosen (design doc §7); this test is what
  // stops a future token edit from silently breaking accessibility.
  describe('Public Ledger token contrast (WCAG AA, 4.5:1 for normal text)', () => {
    test('foreground on background', () => {
      expect(contrastRatio('#1b2b26', '#f8f6ef')).toBeGreaterThanOrEqual(4.5);
    });

    test('sidebar-foreground on sidebar', () => {
      expect(contrastRatio('#f7f3e9', '#17221f')).toBeGreaterThanOrEqual(4.5);
    });

    test('primary (verdigris) on background', () => {
      expect(contrastRatio('#167c6b', '#f8f6ef')).toBeGreaterThanOrEqual(4.5);
    });

    test('muted-foreground on background', () => {
      expect(contrastRatio('#56665e', '#f8f6ef')).toBeGreaterThanOrEqual(4.5);
    });

    test('amber-foreground on background', () => {
      expect(contrastRatio('#8a672c', '#f8f6ef')).toBeGreaterThanOrEqual(4.5);
    });

    test('amber-foreground on amber', () => {
      expect(contrastRatio('#8a672c', '#fbf3e7')).toBeGreaterThanOrEqual(4.5);
    });

    test('destructive on background', () => {
      expect(contrastRatio('#a13f2e', '#f8f6ef')).toBeGreaterThanOrEqual(4.5);
    });

    test('info on background', () => {
      expect(contrastRatio('#2f5f8a', '#f8f6ef')).toBeGreaterThanOrEqual(4.5);
    });
  });
  ```

  Run it (`npx vitest run src/design/contrast.test.ts`) — expect FAIL,
  `Cannot find module './contrast'`. Then write `src/design/contrast.ts`:

  ```ts
  /** WCAG 2.1 relative luminance + contrast ratio (§1.4.3), for hex colors. */

  function relativeLuminance(hex: string): number {
    const clean = hex.replace('#', '');
    const [r, g, b] = [0, 2, 4].map((i) => parseInt(clean.slice(i, i + 2), 16) / 255);
    const linearize = (channel: number) =>
      channel <= 0.03928 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4;
    const [lr, lg, lb] = [r, g, b].map(linearize);
    return 0.2126 * lr + 0.7152 * lg + 0.0722 * lb;
  }

  export function contrastRatio(hexA: string, hexB: string): number {
    const [lighter, darker] = [relativeLuminance(hexA), relativeLuminance(hexB)].sort(
      (a, b) => b - a,
    );
    return (lighter + 0.05) / (darker + 0.05);
  }
  ```

  Run the test again — expect PASS (all 8 pairings; these exact numbers
  were verified during the design doc's own review: foreground/background
  13.67:1, sidebar-foreground/sidebar 14.75:1, primary/background 4.70:1,
  muted-foreground/background 5.62:1, amber-foreground/background 4.79:1,
  amber-foreground/amber 4.70:1, destructive/background 5.95:1,
  info/background 6.21:1).

  Then write `src/index.css`:

  ```css
  @import "tailwindcss";
  @import "tw-animate-css";

  @theme inline {
    --color-background: var(--background);
    --color-foreground: var(--foreground);
    --color-card: var(--card);
    --color-card-foreground: var(--card-foreground);
    --color-popover: var(--popover);
    --color-popover-foreground: var(--popover-foreground);
    --color-primary: var(--primary);
    --color-primary-foreground: var(--primary-foreground);
    --color-secondary: var(--secondary);
    --color-secondary-foreground: var(--secondary-foreground);
    --color-muted: var(--muted);
    --color-muted-foreground: var(--muted-foreground);
    --color-accent: var(--accent);
    --color-accent-foreground: var(--accent-foreground);
    --color-destructive: var(--destructive);
    --color-destructive-foreground: var(--destructive-foreground);
    --color-amber: var(--amber);
    --color-amber-foreground: var(--amber-foreground);
    --color-info: var(--info);
    --color-border: var(--border);
    --color-input: var(--input);
    --color-ring: var(--ring);
    --color-sidebar: var(--sidebar);
    --color-sidebar-foreground: var(--sidebar-foreground);
    --radius-sm: calc(var(--radius) - 4px);
    --radius-md: calc(var(--radius) - 2px);
    --radius-lg: var(--radius);
    --font-display: "DM Serif Display", Georgia, serif;
    --font-sans: "DM Sans Variable", "DM Sans", system-ui, sans-serif;
  }

  :root {
    /* Public Ledger palette (design doc §3/§5) -- values re-set here as
       this app's own tokens, not imported from the source exploration. */
    --background: #f8f6ef;
    --foreground: #1b2b26;
    --card: #fffdf8;
    --card-foreground: #1b2b26;
    --popover: #fffdf8;
    --popover-foreground: #1b2b26;
    --primary: #167c6b;
    --primary-foreground: #f7f3e9;
    --secondary: #efece1;
    --secondary-foreground: #1b2b26;
    --muted: #efece1;
    --muted-foreground: #56665e;
    --accent: #efece1;
    --accent-foreground: #1b2b26;
    --destructive: #a13f2e;
    --destructive-foreground: #f7f3e9;
    --amber: #fbf3e7;
    --amber-foreground: #8a672c;
    --info: #2f5f8a;
    --border: #d8d6cb;
    --input: #d8d6cb;
    --ring: #167c6b;
    --sidebar: #17221f;
    --sidebar-foreground: #f7f3e9;
    --radius: 0.5rem;
  }

  @layer base {
    * {
      @apply border-border;
    }
    body {
      @apply bg-background text-foreground;
      font-family: var(--font-sans);
    }
    h1, h2, h3 {
      font-family: var(--font-display);
    }
  }
  ```

  Edit `src/main.tsx`, adding at the top:

  ```ts
  import '@fontsource/dm-serif-display';
  import '@fontsource-variable/dm-sans';
  import './index.css';
  ```

- [ ] **Step 3: shadcn/ui setup and the four primitives this plan uses.**

  Create `components.json`:

  ```json
  {
    "$schema": "https://ui.shadcn.com/schema.json",
    "style": "new-york",
    "rsc": false,
    "tsx": true,
    "tailwind": {
      "config": "",
      "css": "src/index.css",
      "baseColor": "neutral",
      "cssVariables": true,
      "prefix": ""
    },
    "aliases": {
      "components": "@/components",
      "utils": "@/lib/utils",
      "ui": "@/components/ui",
      "lib": "@/lib",
      "hooks": "@/hooks"
    }
  }
  ```

  ```bash
  npx shadcn@latest add button input textarea label -y -o
  ```

  This generates `src/lib/utils.ts` (the `cn` helper) and
  `src/components/ui/{button,input,textarea,label}.tsx` automatically,
  installing `class-variance-authority`, `clsx`, `tailwind-merge`, and
  `@radix-ui/react-label`/`@radix-ui/react-slot` as it does. Confirm
  `src/lib/utils.ts` exports `cn` as described in this task's Interfaces
  block — if the generated signature differs, this plan's later imports
  need updating to match, not the other way around.

- [ ] **Step 4: Export `Role`, build `NavRail`.**

  `Role` is currently declared twice, un-exported, in both `App.tsx` and
  `AuthContext.tsx`. `NavRail`/`TopUtilityBar` need it too, so export it
  once from where it's actually produced. Edit
  `src/auth/AuthContext.tsx`, changing:

  ```ts
  type Role = 'CUSTOMER' | 'WORKER' | 'ADMIN';
  ```

  to:

  ```ts
  export type Role = 'CUSTOMER' | 'WORKER' | 'ADMIN';
  ```

  Write the failing test first — `src/components/design-system/NavRail.test.tsx`:

  ```tsx
  import { render, screen } from '@testing-library/react';
  import { MemoryRouter } from 'react-router-dom';
  import { NavRail } from './NavRail';

  test('CUSTOMER sees Apply and Ask about policy links only', () => {
    render(
      <MemoryRouter>
        <NavRail role="CUSTOMER" />
      </MemoryRouter>,
    );
    expect(screen.getByRole('link', { name: 'Apply' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Ask about policy' })).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Cases' })).not.toBeInTheDocument();
  });

  test('WORKER sees only the Cases link', () => {
    render(
      <MemoryRouter>
        <NavRail role="WORKER" />
      </MemoryRouter>,
    );
    expect(screen.getByRole('link', { name: 'Cases' })).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Apply' })).not.toBeInTheDocument();
  });

  test('ADMIN sees only the Rule authoring link', () => {
    render(
      <MemoryRouter>
        <NavRail role="ADMIN" />
      </MemoryRouter>,
    );
    expect(screen.getByRole('link', { name: 'Rule authoring' })).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Cases' })).not.toBeInTheDocument();
  });
  ```

  Run it — expect FAIL, `Cannot find module './NavRail'`. Then write
  `src/components/design-system/NavRail.tsx`. This is also where
  `framer-motion` gets its first real use (design doc §3/§7: "brief
  160–220ms transitions for... navigation," gated by
  `prefers-reduced-motion`) — a shared-layout highlight that slides
  between nav items on route change, via `layoutId`:

  ```tsx
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

  export function NavRail({ role }: { role: Role }) {
    return (
      <nav aria-label="Main" className="flex h-full w-56 flex-col bg-sidebar text-sidebar-foreground">
        <div className="px-5 py-6">
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
  ```

  `useMatch` needs a Router context, which `NavRail.test.tsx`'s
  `MemoryRouter` wrapper already provides; none of its three tests
  navigate to a matching path, so `isActive` is `false` and the motion
  span never renders in tests — this test file needs no change for the
  motion addition. Run the test again — expect PASS.

- [ ] **Step 5: Build `TopUtilityBar`, wire both into `App.tsx`.**

  `src/components/design-system/TopUtilityBar.tsx`:

  ```tsx
  import type { Role } from '@/auth/AuthContext';
  import { Button } from '@/components/ui/button';

  const ROLE_LABEL: Record<Role, string> = {
    CUSTOMER: 'Applicant',
    WORKER: 'Caseworker',
    ADMIN: 'Administrator',
  };

  export function TopUtilityBar({ role, onSignOut }: { role: Role; onSignOut: () => void }) {
    return (
      <div className="flex items-center justify-end gap-4 border-b border-border bg-card px-6 py-3">
        <span className="text-sm text-muted-foreground">Signed in as {ROLE_LABEL[role]}</span>
        <Button variant="outline" size="sm" onClick={onSignOut}>
          Sign out
        </Button>
      </div>
    );
  }
  ```

  Edit `src/App.tsx`: remove the `Nav` function and its `NavLink` import
  entirely; replace `AuthedAppShell`'s body with:

  ```tsx
  import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
  import { CanopicaAuthProvider, useIesAuth, type Role } from './auth/AuthContext';
  import { NavRail } from './components/design-system/NavRail';
  import { TopUtilityBar } from './components/design-system/TopUtilityBar';
  import IntakePage from './pages/IntakePage';
  import WorkerCasesPage from './pages/WorkerCasesPage';
  import CaseDetailPage from './pages/CaseDetailPage';
  import PolicyQaPage from './pages/PolicyQaPage';
  import RuleAuthoringPage from './pages/RuleAuthoringPage';

  const HOME_FOR: Record<Role, string> = {
    CUSTOMER: '/apply',
    WORKER: '/cases',
    ADMIN: '/rule-authoring',
  };

  function AuthedAppShell({ role, signOut }: { role: Role; signOut: () => void }) {
    return (
      <div className="flex min-h-screen">
        <NavRail role={role} />
        <div className="flex flex-1 flex-col">
          <TopUtilityBar role={role} onSignOut={signOut} />
          <main className="flex-1 bg-background p-8">
            <Routes>
              <Route path="/" element={<Navigate to={HOME_FOR[role]} replace />} />
              <Route path="/apply" element={<IntakePage />} />
              <Route path="/ask" element={<PolicyQaPage />} />
              <Route path="/cases" element={<WorkerCasesPage />} />
              <Route path="/cases/:programRequestId" element={<CaseDetailPage />} />
              <Route path="/rule-authoring" element={<RuleAuthoringPage />} />
            </Routes>
          </main>
        </div>
      </div>
    );
  }
  ```

  `AppShell`'s `auth.status` switch and the outer `App` function (the
  `BrowserRouter`/`CanopicaAuthProvider` wrap) are unchanged. Run
  `src/App.test.tsx` — expect PASS unmodified: it renders through
  `CanopicaAuthProvider`'s unauthenticated `'choosing'` state (no realm
  cookie in a fresh test), which renders `RealmChooser`'s own
  `<h1>Canopica</h1>` — a screen this task deliberately does not restyle
  (design doc §4 scopes this pass to the 5 authenticated pages; the
  realm-choice/loading/error screens are pre-auth chrome, left as-is,
  same exclusion in spirit as the design doc's own non-goals list).

- [ ] **Step 6: Build the remaining shared primitives.**

  `src/components/design-system/RecordSheet.tsx`:

  ```tsx
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
  ```

  Spreading `HTMLAttributes<HTMLDivElement>` (rather than declaring only
  `children`/`className`) means `aria-label` and similar standard
  attributes just work for any later consumer — Task 5 needs
  `aria-label` and shouldn't have to change this signature to get it.

  Write the failing test first — `src/components/design-system/StatusPill.test.tsx`:

  ```tsx
  import { render, screen } from '@testing-library/react';
  import { StatusPill } from './StatusPill';

  test.each([
    ['affirmed', 'Eligible'],
    ['exception', 'Not eligible'],
    ['pending', 'Awaiting review'],
    ['neutral', 'Draft'],
  ] as const)('renders %s tone with its own text', (tone, text) => {
    render(<StatusPill tone={tone}>{text}</StatusPill>);
    expect(screen.getByText(text)).toBeInTheDocument();
  });
  ```

  Run it — expect FAIL, `Cannot find module './StatusPill'`. Then write
  `src/components/design-system/StatusPill.tsx`:

  ```tsx
  import type { ReactNode } from 'react';
  import { cn } from '@/lib/utils';

  export type StatusPillTone = 'affirmed' | 'exception' | 'pending' | 'neutral';

  const TONE_CLASSES: Record<StatusPillTone, string> = {
    affirmed: 'bg-primary/10 text-primary',
    exception: 'bg-amber text-amber-foreground',
    pending: 'bg-muted text-muted-foreground',
    neutral: 'bg-secondary text-secondary-foreground',
  };

  export function StatusPill({ tone, children }: { tone: StatusPillTone; children: ReactNode }) {
    return (
      <span
        className={cn(
          'inline-block rounded-sm px-2 py-0.5 text-xs font-medium uppercase tracking-wide',
          TONE_CLASSES[tone],
        )}
      >
        {children}
      </span>
    );
  }
  ```

  Run the test again — expect PASS. Then, no test needed beyond the
  existing page tests that will exercise these visually (they carry no
  independent logic to unit-test — pure presentational wrappers):

  `src/components/design-system/DecisionBar.tsx`:

  ```tsx
  import type { ReactNode } from 'react';

  export function DecisionBar({
    amount,
    policyVersion,
    note,
  }: {
    amount: string;
    policyVersion: string;
    note: ReactNode;
  }) {
    return (
      <div className="flex items-baseline justify-between border-y border-border bg-card px-4 py-3">
        <span className="font-display text-2xl tabular-nums text-foreground">${amount}/month</span>
        <span className="text-xs text-muted-foreground">
          Policy <strong className="font-medium text-foreground">{policyVersion}</strong>
        </span>
        <span className="text-xs text-muted-foreground">{note}</span>
      </div>
    );
  }
  ```

  `policyVersion` is deliberately wrapped in its own `<strong>`, not
  concatenated into the surrounding `<span>`'s text: Task 5's
  `CaseDetailPage.test.tsx` asserts `getByText('SNAP-FY2025')` with an
  exact-match string, which only matches an element whose own text
  content is exactly that string — `"Policy SNAP-FY2025"` as one node's
  full text would not match.

  `src/components/design-system/CustodySpine.tsx` — `framer-motion`'s
  second use: the spine itself draws in on entry (design doc §3: "the
  decision spine should draw in subtly on page entry"), gated by
  `prefers-reduced-motion`:

  ```tsx
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
  ```

  `src/components/design-system/FormField.tsx`:

  ```tsx
  import type { ReactNode } from 'react';
  import { Label } from '@/components/ui/label';

  export function FormField({
    id,
    label,
    error,
    children,
  }: {
    id: string;
    label: string;
    error?: string;
    children: ReactNode;
  }) {
    return (
      <div className="flex flex-col gap-1.5">
        <Label htmlFor={id}>{label}</Label>
        {children}
        {error && (
          <p role="alert" className="text-sm text-destructive">
            {error}
          </p>
        )}
      </div>
    );
  }
  ```

- [ ] **Step 7: Manual browser check.** `npm run dev`, sign in as each of
      the three realms/roles, confirm: the dark rail renders with the
      right links per role, the top bar shows the right role label and
      signs out correctly, and every existing page still renders (still
      unstyled internally until its own task — this step is checking the
      shell, not the pages).

- [ ] **Step 8: Full suite + commit.**

  ```bash
  make test && make lint
  git add ui/components.json ui/package.json ui/package-lock.json \
    ui/vite.config.ts ui/tsconfig.app.json ui/src/index.css ui/src/main.tsx \
    ui/src/App.tsx ui/src/auth/AuthContext.tsx ui/src/test/setup.ts ui/src/lib \
    ui/src/design ui/src/components/ui ui/src/components/design-system docs/STATUS.md
  git commit -m "Add Tailwind/shadcn foundation and the Public Ledger app shell"
  ```

---

## Task 2: Migrate `IntakePage`

**Files:**
- Modify: `src/pages/IntakePage.tsx`, `src/components/HouseholdMemberFields.tsx`,
  `src/components/IncomeFields.tsx`, `src/components/ExpenseFields.tsx`
- Test (unmodified, must keep passing): `src/pages/IntakePage.test.tsx`

**Interfaces:**
- Consumes: `FormField`, `Button`, `Input` (Task 1). Native `<select>`
  and `<input type="checkbox">` stay native, per Global Constraint 7 —
  restyled with Tailwind classes directly.
- No prop-shape or handler changes to any of the four files — `onChange`
  callbacks, `emptyMember`, and every piece of `useState` in
  `IntakePage` are copied unchanged.

- [ ] **Step 1: Restyle `IntakePage.tsx`.** Every `<label>`/`<input>`
      pair (`county`, `addressLine1`, `city`, `state`, `zipCode`,
      `liquidResources`) becomes a `FormField` wrapping a shadcn `Input`,
      e.g.:

  ```tsx
  <FormField id="county" label="County">
    <Input id="county" value={county} onChange={(e) => setCounty(e.target.value)} />
  </FormField>
  ```

  The `arrangementType` `<select>` keeps its native tag, gaining
  Tailwind classes (`className="rounded-md border border-input bg-background px-3 py-2 text-sm"`)
  and wrapped in `FormField` for its label. The `paysUtilitiesSeparately`
  checkbox keeps its native `<input type="checkbox">`, gaining
  `className="h-4 w-4 rounded border-input accent-primary"` — no
  `FormField` wrapper needed since its own `<label>` already wraps it.
  The submit button becomes `<Button type="submit" disabled={submitting}>Submit application</Button>`.
  The error list (`role="alert"`) gets `className="text-sm text-destructive"`.
  The confirmation screen's `<section>` becomes a `RecordSheet`.

- [ ] **Step 2: Restyle `HouseholdMemberFields.tsx`.** Each `<fieldset>`
      becomes a `RecordSheet` (keep the `<legend>` inside it as a
      `<h3 className="font-display text-lg">`, since `RecordSheet` has no
      opinion on headings). `firstName`/`lastName`/`dateOfBirth` become
      `FormField`+`Input` as in Step 1. The `relationship` `<select>`
      stays native, restyled the same way as `arrangementType` above.
      "Remove"/"Add household member" buttons become `Button variant="outline"`
      and `Button variant="secondary"` respectively.

- [ ] **Step 3: Restyle `IncomeFields.tsx` and `ExpenseFields.tsx`.**
      Same pattern: `<fieldset>` → `RecordSheet`, text/number/date
      `<input>`s → `FormField`+`Input`, the `incomeType`/`expenseType`
      `<select>`s stay native with the same Tailwind classes, "Earned
      income" checkbox stays native, "Add"/"Remove" buttons → `Button`.

- [ ] **Step 4: Run the existing test, unmodified.**

  ```bash
  npx vitest run src/pages/IntakePage.test.tsx
  ```

  Expect PASS, both tests, including the `axe(container)` assertion —
  if axe reports a new violation, fix the markup (most likely cause:
  a `FormField`'s `Label`/`Input` `id` mismatch), not the test.

- [ ] **Step 5: Manual browser check.** `npm run dev`, sign in as a
      citizen, fill out the form (add a household member, add an income
      and an expense, submit), confirm the visual result matches the
      design doc's civic-editorial direction and nothing regressed
      functionally.

- [ ] **Step 6: Full suite + commit.**

  ```bash
  make test && make lint
  git add ui/src/pages/IntakePage.tsx ui/src/components/HouseholdMemberFields.tsx \
    ui/src/components/IncomeFields.tsx ui/src/components/ExpenseFields.tsx docs/STATUS.md
  git commit -m "Migrate IntakePage to the Public Ledger design system"
  ```

---

## Task 3: Migrate `PolicyQaPage`

**Files:**
- Modify: `src/pages/PolicyQaPage.tsx`
- Test (unmodified, must keep passing): `src/pages/PolicyQaPage.test.tsx`

**Interfaces:**
- Consumes: `FormField`, `Button`, `Input`, `StatusPill` (Task 1).
- `AnswerPanel`'s prop shape (`{ answer: QaAnswer }`) and both handlers
  (`handleAsk`, `handleExplainDenial`) are unchanged.

- [ ] **Step 1: Restyle `AnswerPanel`.** This is design doc §3's
      "evidence before assertion" principle made concrete: an abstention
      must look distinct from a grounded answer, not just carry a
      `className="qa-abstention"` that's never had a stylesheet to back
      it (there is currently no stylesheet at all). **Keep that exact
      class name** alongside the new Tailwind classes —
      `PolicyQaPage.test.tsx` asserts `toHaveClass('qa-abstention')`
      directly (verified against the real test before writing this
      step), so it's a real compatibility hook, not dead weight to drop:

  ```tsx
  function AnswerPanel({ answer }: { answer: QaAnswer }) {
    if (answer.abstained) {
      return (
        <output className="qa-abstention block rounded-md border border-amber bg-amber px-4 py-3 text-amber-foreground">
          {answer.answer}
        </output>
      );
    }
    return (
      <output className="block rounded-md border border-border bg-card px-4 py-3">
        <p className="text-foreground">{answer.answer}</p>
        {answer.citations.length > 0 && (
          <>
            <h3 className="mt-3 font-display text-sm">Citations</h3>
            <ul className="mt-1 list-inside list-disc text-sm text-muted-foreground">
              {answer.citations.map((citation) => (
                <li key={citation}>{citation}</li>
              ))}
            </ul>
          </>
        )}
      </output>
    );
  }
  ```

- [ ] **Step 2: Restyle the two forms.** Both `question` and
      `determinationId` `<input>`s become `FormField`+`Input`; both
      submit buttons become `Button`; both `role="alert"` error
      paragraphs get `className="text-sm text-destructive"`. The page's
      two `<h2>`/`<h3>` headings pick up the display font automatically
      via `src/index.css`'s `@layer base` rule from Task 1 — no class
      needed.

- [ ] **Step 3: Run the existing test, unmodified.**

  ```bash
  npx vitest run src/pages/PolicyQaPage.test.tsx
  ```

  Expect PASS, including its `axe` assertion.

- [ ] **Step 4: Manual browser check.** `npm run dev`, ask a policy
      question, confirm a grounded answer and an abstention (trigger one
      with a nonsense question if the local AI stack is running,
      otherwise verify visually via React DevTools by forcing
      `answer.abstained = true`) are visually distinct.

- [ ] **Step 5: Full suite + commit.**

  ```bash
  make test && make lint
  git add ui/src/pages/PolicyQaPage.tsx docs/STATUS.md
  git commit -m "Migrate PolicyQaPage to the Public Ledger design system"
  ```

---

## Task 4: Migrate `WorkerCasesPage`

**Files:**
- Modify: `src/pages/WorkerCasesPage.tsx`
- Test (unmodified, must keep passing): `src/pages/WorkerCasesPage.test.tsx`

**Interfaces:**
- Consumes: `StatusPill` (Task 1) only. **Not `RecordSheet`** —
  `WorkerCasesPage.test.tsx` asserts real semantic-table roles
  (`getByRole('table', { name: /cases/i })`,
  `getByRole('columnheader', { name: /household head/i })`, and a second
  `columnheader` for status), so this page keeps its `<table>`/`<thead>`/
  `<th scope="col">` structure exactly as-is — restyled with Tailwind
  classes, not replaced with `RecordSheet` rows. Design doc §3's general
  preference for "stacked record sheets, not card mosaics" doesn't
  override an existing, correct semantic-table test contract; `Task 5`'s
  and `Task 6`'s list contexts (which have no such constraint) are where
  `RecordSheet` actually gets used for list-like content.
- No change to `listCases()` call, loading/error state, or the
  `CaseSummaryResponse` shape consumed.

- [ ] **Step 1: Restyle the existing `<table>` in place.**

  ```tsx
  export default function WorkerCasesPage() {
    // ...existing useState/useEffect unchanged...

    if (error) {
      return (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      );
    }

    if (cases === null) {
      return <p className="text-sm text-muted-foreground">Loading cases…</p>;
    }

    return (
      <table aria-label="Cases" className="w-full border-collapse text-sm">
        <thead>
          <tr>
            <th scope="col" className="border-b border-border px-3 py-2 text-left text-xs uppercase tracking-wide text-muted-foreground">
              Household head
            </th>
            <th scope="col" className="border-b border-border px-3 py-2 text-left text-xs uppercase tracking-wide text-muted-foreground">
              Status
            </th>
            <th scope="col" className="border-b border-border px-3 py-2 text-left text-xs uppercase tracking-wide text-muted-foreground">
              Submitted
            </th>
            <th scope="col" className="border-b border-border px-3 py-2 text-left text-xs uppercase tracking-wide text-muted-foreground">
              Latest determination
            </th>
          </tr>
        </thead>
        <tbody>
          {cases.map((c) => (
            <tr key={c.programRequestId} className="border-b border-border">
              <td className="px-3 py-2">
                <Link to={`/cases/${c.programRequestId}`} className="font-display text-primary hover:underline">
                  {c.householdHeadName}
                </Link>
              </td>
              <td className="px-3 py-2">
                <StatusPill tone={c.status === 'DECIDED' ? 'affirmed' : 'pending'}>{c.status}</StatusPill>
              </td>
              <td className="px-3 py-2 text-muted-foreground">{new Date(c.submittedAt).toLocaleDateString()}</td>
              <td className="px-3 py-2">
                {c.latestDetermination
                  ? `${c.latestDetermination.eligible ? 'Eligible' : 'Not eligible'} — $${c.latestDetermination.benefitAmount}`
                  : 'Not yet determined'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    );
  }
  ```

- [ ] **Step 2: Run the existing test, unmodified.**

  ```bash
  npx vitest run src/pages/WorkerCasesPage.test.tsx
  ```

  Expect PASS — `table`/`columnheader`/`link` roles are all still real
  HTML elements, unchanged by the added `className`s.

- [ ] **Step 3: Manual browser check.** `npm run dev`, sign in as a
      worker, confirm the case list renders with visible column headers,
      status pills, and links that still navigate to case detail.

- [ ] **Step 4: Full suite + commit.**

  ```bash
  make test && make lint
  git add ui/src/pages/WorkerCasesPage.tsx docs/STATUS.md
  git commit -m "Migrate WorkerCasesPage to the Public Ledger design system"
  ```

---

## Task 5: Migrate `CaseDetailPage`, `DeterminationPanel`, `TracePanel`

**Files:**
- Modify: `src/pages/CaseDetailPage.tsx`, `src/components/DeterminationPanel.tsx`,
  `src/components/TracePanel.tsx`
- Test (unmodified, must keep passing): `src/pages/CaseDetailPage.test.tsx`

**Interfaces:**
- Consumes: `RecordSheet`, `FormField`, `Input`, `Button`, `DecisionBar`,
  `CustodySpine`, `StatusPill` (Task 1).
- `DecisionBar`'s `note` slot carries `Decided {decidedAt}` here —
  `DeterminationResponse` has no human-reviewer field (a determination
  is a deterministic auto-decision, not a human-reviewed record), so
  this is the adapted, domain-correct use of the primitive's third slot,
  not a literal "reviewer name."
- `CustodySpine`'s `items` are built from `TraceResponse.decisionResults`
  (`Record<string, unknown>`) via
  `Object.entries(trace.decisionResults).map(([label, value]) => ({ label, value: renderValue(value) }))`,
  reusing `TracePanel`'s existing `renderValue` helper unchanged.
- **Verified against the real `CaseDetailPage.test.tsx` before writing
  this task** (not assumed): it asserts `findByText('Eligible')` and
  `getByText('SNAP-FY2025')`, both exact-string matches, plus
  `getByText(/649\.00/)` as a regex substring match. The code below is
  written to satisfy all three literally, not just visually.

- [ ] **Step 1: Restyle `CaseDetailPage.tsx`.**

  ```tsx
  import { useEffect, useState, type FormEvent } from 'react';
  import { useParams } from 'react-router-dom';
  import { getCase, runDetermination } from '../api/client';
  import type { CaseDetailResponse } from '../api/types';
  import DeterminationPanel from '../components/DeterminationPanel';
  import { Button } from '@/components/ui/button';
  import { Input } from '@/components/ui/input';
  import { FormField } from '@/components/design-system/FormField';
  import { RecordSheet } from '@/components/design-system/RecordSheet';

  function todayIso(): string {
    return new Date().toISOString().slice(0, 10);
  }

  function firstOfCurrentMonthIso(): string {
    const now = new Date();
    return new Date(now.getFullYear(), now.getMonth(), 1).toISOString().slice(0, 10);
  }

  export default function CaseDetailPage() {
    const { programRequestId } = useParams<{ programRequestId: string }>();
    const [caseDetail, setCaseDetail] = useState<CaseDetailResponse | null>(null);
    const [loadError, setLoadError] = useState<string | null>(null);

    const [asOfDate, setAsOfDate] = useState(todayIso());
    const [benefitMonth, setBenefitMonth] = useState(firstOfCurrentMonthIso());
    const [running, setRunning] = useState(false);
    const [runError, setRunError] = useState<string | null>(null);

    useEffect(() => {
      if (!programRequestId) {
        return;
      }
      getCase(programRequestId)
        .then(setCaseDetail)
        .catch(() => setLoadError('Could not load this case.'));
    }, [programRequestId]);

    async function handleRunDetermination(event: FormEvent<HTMLFormElement>) {
      event.preventDefault();
      if (!programRequestId) {
        return;
      }
      setRunning(true);
      setRunError(null);
      try {
        const determination = await runDetermination(programRequestId, { asOfDate, benefitMonth });
        setCaseDetail((current) =>
          current ? { ...current, determinations: [determination, ...current.determinations] } : current,
        );
      } catch {
        setRunError('Could not run a determination for this case.');
      } finally {
        setRunning(false);
      }
    }

    if (loadError) {
      return (
        <p role="alert" className="text-sm text-destructive">
          {loadError}
        </p>
      );
    }

    if (!caseDetail) {
      return <p className="text-sm text-muted-foreground">Loading case…</p>;
    }

    return (
      <div className="flex flex-col gap-6">
        <RecordSheet>
          <h2 className="font-display text-xl">{caseDetail.householdHeadName}</h2>
          <dl className="mt-3 grid grid-cols-2 gap-x-6 gap-y-1">
            <dt className="text-sm text-muted-foreground">Program</dt>
            <dd className="text-sm text-foreground">{caseDetail.programCode}</dd>
            <dt className="text-sm text-muted-foreground">Status</dt>
            <dd className="text-sm text-foreground">{caseDetail.status}</dd>
            <dt className="text-sm text-muted-foreground">Requested on</dt>
            <dd className="text-sm text-foreground">{caseDetail.requestedOn}</dd>
          </dl>
        </RecordSheet>

        <RecordSheet>
          <form onSubmit={handleRunDetermination} className="flex flex-col gap-4">
            <h3 className="font-display text-lg">Run a determination</h3>
            {runError && (
              <p role="alert" className="text-sm text-destructive">
                {runError}
              </p>
            )}

            <FormField id="asOfDate" label="As-of date">
              <Input id="asOfDate" type="date" value={asOfDate} onChange={(e) => setAsOfDate(e.target.value)} />
            </FormField>

            <FormField id="benefitMonth" label="Benefit month">
              <Input
                id="benefitMonth"
                type="date"
                value={benefitMonth}
                onChange={(e) => setBenefitMonth(e.target.value)}
              />
            </FormField>

            <Button type="submit" disabled={running} className="self-start">
              Run determination
            </Button>
          </form>
        </RecordSheet>

        <div>
          <h3 className="font-display text-lg">Determination history</h3>
          {caseDetail.determinations.length === 0 ? (
            <p className="mt-2 text-sm text-muted-foreground">No determination has been made yet.</p>
          ) : (
            <div className="mt-3 flex flex-col gap-3">
              {caseDetail.determinations.map((determination) => (
                <DeterminationPanel key={determination.determinationId} determination={determination} />
              ))}
            </div>
          )}
        </div>
      </div>
    );
  }
  ```

- [ ] **Step 2: Restyle `DeterminationPanel.tsx`.** The original
      renders the literal text `Eligible`/`Not eligible` as its own
      `<strong>` — the test asserts on that exact text
      (`findByText('Eligible')`), so it has to keep existing as its own
      isolated element, not get folded into `DecisionBar`'s combined
      amount string. Use `StatusPill` for it instead of a bare
      `<strong>`, and `DecisionBar` for the amount/policy/decided-at
      strip:

  ```tsx
  import type { DeterminationResponse } from '../api/types';
  import { DecisionBar } from './design-system/DecisionBar';
  import { RecordSheet } from './design-system/RecordSheet';
  import { StatusPill } from './design-system/StatusPill';
  import TracePanel from './TracePanel';

  type Props = {
    determination: DeterminationResponse;
  };

  export default function DeterminationPanel({ determination }: Props) {
    return (
      <RecordSheet aria-label={`Determination decided ${determination.decidedAt}`}>
        <StatusPill tone={determination.eligible ? 'affirmed' : 'exception'}>
          {determination.eligible ? 'Eligible' : 'Not eligible'}
        </StatusPill>
        <DecisionBar
          amount={determination.benefitAmount}
          policyVersion={determination.policyParameterVersion}
          note={`Decided ${determination.decidedAt}`}
        />
        <dl className="mt-3 grid grid-cols-2 gap-x-6 gap-y-1">
          <dt className="text-sm text-muted-foreground">Reason code</dt>
          <dd className="text-sm text-foreground">{determination.reasonCode}</dd>
          <dt className="text-sm text-muted-foreground">Benefit month</dt>
          <dd className="text-sm text-foreground">{determination.benefitMonth}</dd>
          <dt className="text-sm text-muted-foreground">As-of date</dt>
          <dd className="text-sm text-foreground">{determination.asOfDate}</dd>
        </dl>
        <TracePanel determinationId={determination.determinationId} />
      </RecordSheet>
    );
  }
  ```

  `RecordSheet`'s `aria-label` here (via the `HTMLAttributes` spread
  from Task 1) preserves exactly what the original `<article
  aria-label={...}>` carried, even though the real test doesn't
  currently query by it — real, useful information for a screen-reader
  user either way.

- [ ] **Step 3: Restyle `TracePanel.tsx`** to use `CustodySpine` in
      place of the current `<ol>`:

  ```tsx
  import { useState } from 'react';
  import { getTrace } from '../api/client';
  import type { TraceResponse } from '../api/types';
  import { CustodySpine } from './design-system/CustodySpine';

  type Props = {
    determinationId: string;
  };

  function renderValue(value: unknown): string {
    if (value === null || value === undefined) {
      return '—';
    }
    return typeof value === 'object' ? JSON.stringify(value) : String(value);
  }

  export default function TracePanel({ determinationId }: Props) {
    const [trace, setTrace] = useState<TraceResponse | null>(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    function handleToggle(event: React.SyntheticEvent<HTMLDetailsElement>) {
      if (!event.currentTarget.open || trace || loading) {
        return;
      }
      setLoading(true);
      setError(null);
      getTrace(determinationId)
        .then(setTrace)
        .catch(() => setError('Could not load the determination trace.'))
        .finally(() => setLoading(false));
    }

    return (
      <details onToggle={handleToggle} className="mt-3">
        <summary className="cursor-pointer text-sm font-medium text-primary">DMN evaluation trace</summary>
        {loading && <p className="mt-2 text-sm text-muted-foreground">Loading trace…</p>}
        {error && (
          <p role="alert" className="mt-2 text-sm text-destructive">
            {error}
          </p>
        )}
        {trace && (
          <>
            <p className="mt-2 text-sm text-muted-foreground">
              Model hash <code className="font-mono">{trace.dmnModelHash}</code>, policy parameters{' '}
              <strong className="text-foreground">{trace.policyParameterVersion}</strong>
            </p>
            <CustodySpine
              items={Object.entries(trace.decisionResults).map(([label, value]) => ({
                label,
                value: renderValue(value),
              }))}
            />
          </>
        )}
      </details>
    );
  }
  ```

- [ ] **Step 4: Run the existing test, unmodified.**

  ```bash
  npx vitest run src/pages/CaseDetailPage.test.tsx
  ```

  Expect PASS, including its `axe` assertion. `CustodySpine`'s root
  `<ol aria-label="DMN decisions in evaluation order">` matches the
  original list's own `aria-label` exactly (see Task 1's `CustodySpine`)
  — if the test queries by that label, it still resolves.

- [ ] **Step 5: Manual browser check.** `npm run dev`, sign in as a
      worker, open a case with at least one determination, expand its
      trace, confirm the `DecisionBar` and `CustodySpine` render as the
      design doc's signature elements (amount/policy/decided-at side by
      side; a connected vertical line with node markers down the trace).

- [ ] **Step 6: Full suite + commit.**

  ```bash
  make test && make lint
  git add ui/src/pages/CaseDetailPage.tsx ui/src/components/DeterminationPanel.tsx \
    ui/src/components/TracePanel.tsx ui/src/components/design-system/RecordSheet.tsx docs/STATUS.md
  git commit -m "Migrate CaseDetailPage to the Public Ledger design system"
  ```

---

## Task 6: Migrate `RuleAuthoringPage`

**Files:**
- Modify: `src/pages/RuleAuthoringPage.tsx`
- Test (unmodified, must keep passing): `src/pages/RuleAuthoringPage.test.tsx`

**Interfaces:**
- Consumes: `RecordSheet`, `StatusPill`, `FormField`, `Input`, `Button`
  (Task 1).
- This file's own component split (`PendingProposalsList`,
  `ReviewedStatusBanner`, `ProposalReview`, `PublicationFields`,
  `DiffTable`) — the direct result of the earlier cyclomatic-complexity
  refactor — is unchanged by this task; each of those five functions
  gets the same restyling treatment internally, not a further split.

- [ ] **Step 1: Restyle `DiffTable`.** Keep the semantic `<table>`
      (tabular data, correctly marked up already); add Tailwind classes:
      `className="w-full border-collapse text-sm"` on `<table>`,
      `className="border-b border-border px-3 py-2 text-left text-xs uppercase tracking-wide text-muted-foreground"`
      on each `<th>`, `className="border-b border-border px-3 py-2"` on
      each `<td>`/`<th scope="row">`.

- [ ] **Step 2: Restyle `PublicationFields`.** The `<fieldset>` becomes
      a `RecordSheet`; each of the three `<label>`/`<input>` pairs
      becomes `FormField`+`Input`.

- [ ] **Step 3: Restyle `PendingProposalsList` and `ReviewedStatusBanner`.**
      In `PendingProposalsList`, the `<ul>`'s items each become a
      `RecordSheet` wrapping the existing button (restyled as
      `Button variant="outline"`). In `ReviewedStatusBanner`, the `<p>`
      becomes a `StatusPill` with `tone="affirmed"` when
      `proposal.status === 'ACCEPTED'` and `tone="exception"` otherwise,
      wrapping the existing text content.

- [ ] **Step 4: Restyle `ProposalReview` and the top-level page.** The
      `<article>` becomes a `RecordSheet`; the hasChanges ternary's two
      branches keep their structure (real `DiffTable` vs. a
      `text-sm text-muted-foreground` message); the Accept/Reject
      buttons become `Button` (`variant="default"` for accept,
      `variant="outline"` for reject). At the top level, the excerpt
      `<textarea>` becomes a shadcn `Textarea` wrapped in `FormField`;
      the submit button becomes `Button`; the error paragraph gets
      `className="text-sm text-destructive"`.

- [ ] **Step 5: Run the existing test, unmodified.**

  ```bash
  npx vitest run src/pages/RuleAuthoringPage.test.tsx
  ```

  Expect PASS, all 9 tests, including the `axe` assertion.

- [ ] **Step 6: Manual browser check.** `npm run dev`, sign in as an
      admin, draft a proposal from a pasted excerpt, review and accept
      or reject it, confirm the full flow renders correctly styled end
      to end — this is the last page, so this is also the first point
      the whole app can be walked through with the new design system on
      every screen.

- [ ] **Step 7: Full suite + commit.**

  ```bash
  make test && make lint
  git add ui/src/pages/RuleAuthoringPage.tsx docs/STATUS.md
  git commit -m "Migrate RuleAuthoringPage to the Public Ledger design system"
  ```
