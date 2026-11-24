import type { Metadata } from "next";
import { hasLocale, NextIntlClientProvider } from "next-intl";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { BRAND } from "@/config/brand";
import { UI_LOCALE_TAG } from "@/config/locales";
import { requireLocale } from "@/i18n/locale";
import { routing } from "@/i18n/routing";
import { LocaleSwitcher } from "@/components/locale-switcher";
import "../globals.css";

export function generateStaticParams() {
  return routing.locales.map((locale) => ({ locale }));
}

export async function generateMetadata({ params }: LayoutProps<"/[locale]">): Promise<Metadata> {
  const { locale } = await params;
  if (!hasLocale(routing.locales, locale)) return {};
  const t = await getTranslations({ locale, namespace: "Metadata" });
  return {
    title: t("title", { brand: BRAND.name }),
    description: t("description"),
  };
}

export default async function LocaleLayout({ children, params }: LayoutProps<"/[locale]">) {
  const locale = requireLocale((await params).locale);
  setRequestLocale(locale);

  return (
    <html lang={UI_LOCALE_TAG[locale]} className="h-full antialiased">
      <body className="flex min-h-full flex-col">
        <NextIntlClientProvider>
          <header className="flex items-center justify-between px-6 py-4">
            <span className="font-semibold">{BRAND.name}</span>
            <LocaleSwitcher />
          </header>
          {children}
        </NextIntlClientProvider>
      </body>
    </html>
  );
}
