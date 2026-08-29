import { useTranslation } from 'react-i18next';
import { useBreadcrumbValue } from './PageChrome';
import { SUPPORTED_LANGUAGES, type SupportedLanguage } from '@/i18n/config';

function LanguageSwitcher() {
  const { t, i18n } = useTranslation('common');
  return (
    <label className="flex items-center gap-2 text-sm text-muted-foreground">
      <span className="sr-only">{t('language.label')}</span>
      <select
        value={i18n.resolvedLanguage}
        onChange={(e) => void i18n.changeLanguage(e.target.value as SupportedLanguage)}
        className="rounded-md border border-input bg-background px-2 py-1 text-sm"
      >
        {SUPPORTED_LANGUAGES.map((lang) => (
          <option key={lang} value={lang}>
            {t(`language.${lang}`)}
          </option>
        ))}
      </select>
    </label>
  );
}

export function TopUtilityBar() {
  const breadcrumb = useBreadcrumbValue();
  return (
    <div className="sticky top-0 z-20 flex items-center justify-between border-b border-border bg-card/90 px-6 py-3 backdrop-blur-sm">
      <span className="text-sm font-medium text-muted-foreground">{breadcrumb}</span>
      <LanguageSwitcher />
    </div>
  );
}
