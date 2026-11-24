import { useTranslations } from "next-intl";
import { setRequestLocale } from "next-intl/server";
import { use } from "react";
import { requireLocale } from "@/i18n/locale";
import { buttonVariants } from "@/components/ui/button";
import { Link } from "@/i18n/navigation";

export default function LandingPage({ params }: PageProps<"/[locale]">) {
  const locale = requireLocale(use(params).locale);
  setRequestLocale(locale);
  const t = useTranslations("Landing");

  return (
    <main className="mx-auto flex max-w-2xl flex-1 flex-col items-center justify-center gap-6 px-6 text-center">
      <h1 className="text-3xl font-semibold text-balance">{t("promise")}</h1>
      <Link href="/create" className={buttonVariants({ size: "lg" })}>
        {t("cta")}
      </Link>
      <p className="text-sm text-muted-foreground">{t("noAccount")}</p>
    </main>
  );
}
