import Link from "next/link";
import { getTranslations } from "next-intl/server";

export default async function NotFound() {
  const t = await getTranslations();
  return (
    <div className="grid min-h-[60dvh] place-items-center px-4 text-center">
      <div className="space-y-3">
        <p className="font-mono text-sm text-primary-text">404</p>
        <h1 className="text-2xl font-semibold">{t("states.notFoundTitle")}</h1>
        <p className="text-muted">{t("states.notFoundBody")}</p>
        <Link href="/" className="inline-block pt-2 text-primary-text hover:underline">
          {t("common.backHome")}
        </Link>
      </div>
    </div>
  );
}
