import { notFound } from "next/navigation";
import { isUiLocale, type UiLocale } from "@/config/locales";

/** Narrows a route param to a supported UI locale, or renders 404. */
export function requireLocale(value: string): UiLocale {
  if (!isUiLocale(value)) notFound();
  return value;
}
