import { useBreadcrumbValue } from './PageChrome';

export function TopUtilityBar() {
  const breadcrumb = useBreadcrumbValue();
  return (
    <div className="sticky top-0 z-20 flex items-center border-b border-border bg-card/90 px-6 py-3 backdrop-blur-sm">
      <span className="text-sm font-medium text-muted-foreground">{breadcrumb}</span>
    </div>
  );
}
