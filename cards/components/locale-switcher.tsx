import { useLocale, useTranslations } from "next-intl";
import { UI_LOCALE_TAG } from "@/config/locales";
import { Link } from "@/i18n/navigation";
import { routing } from "@/i18n/routing";
import { cn } from "@/lib/utils";

export function LocaleSwitcher() {
  const t = useTranslations("LocaleSwitcher");
  const current = useLocale();

  return (
    <nav aria-label={t("label")} className="flex gap-3 text-sm">
      {routing.locales.map((locale) => (
        <Link
          key={locale}
          href="/"
          locale={locale}
          hrefLang={UI_LOCALE_TAG[locale]}
          lang={UI_LOCALE_TAG[locale]}
          aria-current={locale === current ? "true" : undefined}
          className={cn(
            "underline-offset-4 hover:underline",
            locale === current && "font-semibold",
          )}
        >
          {t(locale)}
        </Link>
      ))}
    </nav>
  );
}
