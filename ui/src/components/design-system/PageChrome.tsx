import { createContext, useContext, useEffect, useState, type ReactNode } from 'react';

type BreadcrumbCtx = { breadcrumb: string | null; setBreadcrumb: (v: string | null) => void };
const BreadcrumbContext = createContext<BreadcrumbCtx | null>(null);

export function PageChromeProvider({ children }: { children: ReactNode }) {
  const [breadcrumb, setBreadcrumb] = useState<string | null>(null);
  return (
    <BreadcrumbContext.Provider value={{ breadcrumb, setBreadcrumb }}>{children}</BreadcrumbContext.Provider>
  );
}

/** Call on a page's mount to show it in TopUtilityBar's breadcrumb slot; clears on unmount. */
export function useBreadcrumb(value: string | null) {
  const ctx = useContext(BreadcrumbContext);
  useEffect(() => {
    ctx?.setBreadcrumb(value);
    return () => ctx?.setBreadcrumb(null);
  }, [ctx, value]);
}

export function useBreadcrumbValue(): string | null {
  return useContext(BreadcrumbContext)?.breadcrumb ?? null;
}
