import { cookies, headers } from "next/headers";
import { getRequestConfig } from "next-intl/server";

export const LOCALES = ["es", "en"] as const;
export type Locale = (typeof LOCALES)[number];
export const LOCALE_COOKIE = "NEXT_LOCALE";

function pick(value: string | undefined | null): Locale | null {
  if (!value) return null;
  const base = value.split(",")[0].split("-")[0].trim().toLowerCase();
  return (LOCALES as readonly string[]).includes(base) ? (base as Locale) : null;
}

export default getRequestConfig(async () => {
  // 1) idioma guardado en la cuenta (cookie), 2) idioma del navegador, 3) español.
  const cookieLocale = pick((await cookies()).get(LOCALE_COOKIE)?.value);
  const headerLocale = pick((await headers()).get("accept-language"));
  const locale: Locale = cookieLocale ?? headerLocale ?? "es";
  return {
    locale,
    messages: (await import(`../messages/${locale}.json`)).default,
  };
});
