import { LayoutDashboard, Server, ShieldCheck } from "lucide-react";
import { cookies } from "next/headers";
import Link from "next/link";
import { getTranslations } from "next-intl/server";

import { getInviteUrl } from "@/lib/server";

export default async function Landing({ searchParams }: { searchParams: Promise<{ login_error?: string }> }) {
  const t = await getTranslations("landing");
  const tc = await getTranslations("common");
  const { login_error } = await searchParams;
  const loggedIn = Boolean((await cookies()).get("nexus_session"));
  const invite = await getInviteUrl();
  const errorKey = login_error && ["denied", "state", "discord"].includes(login_error) ? login_error : null;

  const features = [
    { icon: LayoutDashboard, title: t("feature1Title"), body: t("feature1Body") },
    { icon: Server, title: t("feature2Title"), body: t("feature2Body") },
    { icon: ShieldCheck, title: t("feature3Title"), body: t("feature3Body") },
  ];

  return (
    <div className="flex min-h-dvh flex-col">
      <header className="mx-auto flex w-full max-w-6xl items-center justify-between px-4 py-5 sm:px-6">
        <div className="flex items-center gap-2.5">
          <span className="grid size-9 place-items-center rounded-xl bg-primary-solid text-sm font-bold text-white">N</span>
          <span className="text-lg font-semibold tracking-tight">NEXUS BOT</span>
        </div>
        <Link href={loggedIn ? "/dashboard" : "/login"} className="text-sm text-primary-text hover:underline">
          {loggedIn ? t("goDashboard") : t("login")}
        </Link>
      </header>

      <main className="mx-auto flex w-full max-w-6xl flex-1 flex-col items-center px-4 pb-16 pt-12 text-center sm:px-6 sm:pt-20">
        {errorKey && (
          <p role="alert" className="mb-6 rounded-lg border border-danger/30 bg-danger/10 px-4 py-2 text-sm">
            {t(`loginError.${errorKey}`)}
          </p>
        )}
        <h1 className="max-w-3xl text-balance text-4xl font-semibold tracking-tight sm:text-5xl">{t("tagline")}</h1>
        <p className="mt-5 max-w-2xl text-balance text-base text-muted sm:text-lg">{t("description")}</p>
        <div className="mt-8 flex flex-wrap justify-center gap-3">
          <Link
            href={loggedIn ? "/dashboard" : "/login"}
            className="inline-flex min-h-11 items-center rounded-lg bg-primary-solid px-5 font-medium text-white hover:bg-primary"
          >
            {loggedIn ? t("goDashboard") : t("login")}
          </Link>
          {invite && (
            <a
              href={invite}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex min-h-11 items-center rounded-lg border border-border bg-panel px-5 font-medium hover:bg-panel-hover"
            >
              {tc("invite")}
            </a>
          )}
        </div>

        <div className="mt-16 grid w-full gap-4 text-left sm:grid-cols-3">
          {features.map(({ icon: Icon, title, body }) => (
            <div key={title} className="rounded-xl border border-border bg-panel p-5">
              <div className="mb-3 grid size-10 place-items-center rounded-lg bg-primary/15">
                <Icon className="size-5 text-primary-text" aria-hidden />
              </div>
              <h2 className="font-semibold">{title}</h2>
              <p className="mt-1 text-[13px] text-muted">{body}</p>
            </div>
          ))}
        </div>
      </main>

      <footer className="flex justify-center gap-4 border-t border-border py-6 text-[12px] text-muted">
        <Link href="/legal/terms" className="hover:text-text">{t("terms")}</Link>
        <Link href="/legal/privacy" className="hover:text-text">{t("privacy")}</Link>
      </footer>
    </div>
  );
}
