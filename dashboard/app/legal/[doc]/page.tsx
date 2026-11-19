import Link from "next/link";
import { notFound } from "next/navigation";
import { getLocale } from "next-intl/server";

import { LEGAL } from "../content";

export const dynamicParams = false;

export function generateStaticParams() {
  return [{ doc: "terms" }, { doc: "privacy" }];
}

export default async function LegalPage({ params }: { params: Promise<{ doc: string }> }) {
  const { doc } = await params;
  const locale = (await getLocale()) === "en" ? "en" : "es";
  const page = LEGAL[locale][doc as "terms" | "privacy"];
  if (!page) notFound();
  return (
    <div className="mx-auto max-w-3xl px-4 py-10 sm:px-6">
      <Link href="/" className="text-sm text-primary-text hover:underline">← NEXUS BOT</Link>
      <h1 className="mt-6 text-3xl font-semibold tracking-tight">{page.title}</h1>
      <p className="mt-2 text-[13px] text-muted">{page.updated}</p>
      <p className="mt-4 rounded-lg border border-warning/30 bg-warning/10 px-4 py-3 text-sm">{page.draft}</p>
      <div className="mt-8 space-y-8">
        {page.sections.map((s) => (
          <section key={s.h}>
            <h2 className="text-lg font-semibold">{s.h}</h2>
            <ul className="mt-3 list-disc space-y-2 pl-5 text-[15px] leading-relaxed text-text/90">
              {s.p.map((x) => <li key={x}>{x}</li>)}
            </ul>
          </section>
        ))}
      </div>
      <nav className="mt-12 flex gap-4 border-t border-border pt-6 text-sm">
        <Link href="/legal/terms" className="text-primary-text hover:underline">{LEGAL[locale].terms.title}</Link>
        <Link href="/legal/privacy" className="text-primary-text hover:underline">{LEGAL[locale].privacy.title}</Link>
      </nav>
    </div>
  );
}
