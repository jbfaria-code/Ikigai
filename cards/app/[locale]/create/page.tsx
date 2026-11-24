import { useTranslations } from "next-intl";
import { setRequestLocale } from "next-intl/server";
import { use } from "react";
import { requireLocale } from "@/i18n/locale";

export default function CreatePage({ params }: PageProps<"/[locale]/create">) {
  const locale = requireLocale(use(params).locale);
  setRequestLocale(locale);
  const t = useTranslations("Create");

  return (
    <main className="mx-auto flex max-w-2xl flex-1 flex-col gap-4 px-6 py-12">
      <h1 className="text-2xl font-semibold">{t("title")}</h1>
      <p className="text-muted-foreground">{t("comingSoon")}</p>
    </main>
  );
}
