"use client";

import { useRouter } from "next/navigation";
import { useLocale } from "next-intl";
import { useEffect } from "react";

import { useMe } from "@/lib/hooks";

export function setLocaleCookie(locale: string) {
  document.cookie = `NEXT_LOCALE=${locale}; path=/; max-age=31536000; samesite=lax`;
}

/** Aplica el idioma guardado en la cuenta (users.locale) al dashboard. */
export function LocaleSync() {
  const { data: me } = useMe();
  const locale = useLocale();
  const router = useRouter();
  useEffect(() => {
    if (me && me.locale !== locale) {
      setLocaleCookie(me.locale);
      router.refresh();
    }
  }, [me, locale, router]);
  return null;
}
