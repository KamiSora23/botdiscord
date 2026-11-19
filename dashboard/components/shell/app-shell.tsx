"use client";

import * as Dialog from "@radix-ui/react-dialog";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronRight, Lock, Menu, Search, ServerOff, UserPlus, X } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { CommandPalette, useCommandPalette } from "@/components/shell/command-palette";
import { Sidebar } from "@/components/shell/sidebar";
import { Card, EmptyState, ErrorState, GuildIcon, LinkButton, Notice, Skeleton } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { useGuild } from "@/lib/hooks";
import { canSee, findItem } from "@/lib/nav";

export function AppShell({ guildId, children }: { guildId: string; children: React.ReactNode }) {
  const t = useTranslations();
  const pathname = usePathname();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [paletteOpen, setPaletteOpen] = useCommandPalette();
  const guild = useGuild(guildId);
  const section = pathname.split("/")[3] ?? "overview";
  const item = findItem(section);
  const sectionLabel = item ? (item.key === "overview" ? t("nav.overview") : t(`nav.items.${item.key}`)) : null;

  return (
    <div className="min-h-dvh lg:grid lg:grid-cols-[260px_1fr]">
      <aside className="sticky top-0 hidden h-dvh self-start border-r border-border bg-sidebar lg:block">
        <Sidebar guildId={guildId} />
      </aside>

      <Dialog.Root open={mobileOpen} onOpenChange={setMobileOpen}>
        <Dialog.Portal>
          <Dialog.Overlay className="fixed inset-0 z-40 bg-black/60 lg:hidden" />
          <Dialog.Content className="fixed inset-y-0 left-0 z-50 w-[min(300px,85vw)] border-r border-border bg-sidebar lg:hidden">
            <Dialog.Title className="sr-only">NEXUS</Dialog.Title>
            <Dialog.Close className="absolute right-3 top-4 grid size-9 place-items-center rounded-lg text-muted hover:bg-panel-hover" aria-label={t("common.close")}>
              <X className="size-5" />
            </Dialog.Close>
            <Sidebar guildId={guildId} onNavigate={() => setMobileOpen(false)} />
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>

      <div className="min-w-0">
        <header className="sticky top-0 z-30 flex h-16 items-center gap-3 border-b border-border bg-bg/85 px-4 backdrop-blur sm:px-6">
          <button
            type="button"
            className="grid size-10 place-items-center rounded-lg text-muted hover:bg-panel-hover lg:hidden"
            onClick={() => setMobileOpen(true)}
            aria-label={t("nav.openMenu")}
          >
            <Menu className="size-5" />
          </button>
          <nav aria-label="breadcrumb" className="flex min-w-0 flex-1 items-center gap-1.5 text-sm text-muted">
            <Link href="/dashboard" className="hidden hover:text-text sm:inline">
              {t("nav.dashboard")}
            </Link>
            <ChevronRight className="hidden size-3.5 sm:block" aria-hidden />
            <span className="hidden max-w-48 truncate sm:inline">{guild.data?.name ?? "…"}</span>
            {sectionLabel && (
              <>
                <ChevronRight className="hidden size-3.5 sm:block" aria-hidden />
                <span className="truncate font-medium text-text">{sectionLabel}</span>
              </>
            )}
          </nav>
          <button
            type="button"
            onClick={() => setPaletteOpen(true)}
            className="flex min-h-10 items-center gap-2 rounded-lg border border-border bg-panel px-3 text-sm text-muted hover:text-text"
          >
            <Search className="size-4" aria-hidden />
            <span className="hidden md:inline">{t("common.search")}</span>
            <kbd className="hidden rounded border border-border px-1.5 font-mono text-[11px] md:inline">Ctrl K</kbd>
          </button>
        </header>

        <main className="mx-auto w-full max-w-[1280px] px-4 py-6 sm:px-6 lg:py-8">
          <GuildGate guildId={guildId} guild={guild}>
            {item && !canSee(item, guild.data) ? (
              <EmptyState icon={Lock} title={t("states.noAccessTitle")} body={t("states.noAccessBody")}
                action={<LinkButton href={`/dashboard/${guildId}/overview`} variant="secondary">{t("nav.overview")}</LinkButton>} />
            ) : children}
          </GuildGate>
        </main>
      </div>

      <CommandPalette guildId={guildId} open={paletteOpen} onOpenChange={setPaletteOpen} />
    </div>
  );
}

function GuildGate({ guildId, guild, children }: { guildId: string; guild: ReturnType<typeof useGuild>; children: React.ReactNode }) {
  const t = useTranslations("states");
  const qc = useQueryClient();

  // Al volver de la ventana de invitación, comprobar si el bot ya entró.
  useEffect(() => {
    if (guild.data?.bot_present !== false) return;
    const onFocus = () => {
      qc.invalidateQueries({ queryKey: ["guild", guildId] });
      qc.invalidateQueries({ queryKey: ["guilds"] });
    };
    window.addEventListener("focus", onFocus);
    const timer = setInterval(onFocus, 5000);
    return () => {
      window.removeEventListener("focus", onFocus);
      clearInterval(timer);
    };
  }, [guild.data?.bot_present, guildId, qc]);

  if (guild.isPending) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-10 w-64" />
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-28" />
          ))}
        </div>
        <Skeleton className="h-72" />
      </div>
    );
  }
  if (guild.isError) {
    const err = guild.error;
    if (err instanceof ApiError && err.code === "guild_not_found") {
      return (
        <Card>
          <EmptyState
            icon={ServerOff}
            title={t("noAccessTitle")}
            body={t("noAccessBody")}
            action={
              <LinkButton href="/dashboard" variant="secondary">
                <BackLabel />
              </LinkButton>
            }
          />
        </Card>
      );
    }
    return <ErrorState error={err} onRetry={() => guild.refetch()} />;
  }
  const g = guild.data;
  if (!g.bot_present) {
    return (
      <Card>
        <EmptyState
          icon={UserPlus}
          title={t("botMissingTitle", { name: g.name })}
          body={t("botMissingBody")}
          action={
            g.invite_url ? (
              <LinkButton href={g.invite_url} target="_blank" rel="noopener noreferrer">
                <GuildIcon name={g.name} url={g.icon_url} size={20} className="rounded-md" />
                <InviteLabel />
              </LinkButton>
            ) : null
          }
        />
      </Card>
    );
  }
  return (
    <>
      <BotOfflineBanner />
      {children}
    </>
  );
}

function InviteLabel() {
  const t = useTranslations("common");
  return <>{t("invite")}</>;
}

function BackLabel() {
  const t = useTranslations("servers");
  return <>← {t("title")}</>;
}

function BotOfflineBanner() {
  const t = useTranslations("states");
  const { data } = useQuery({
    queryKey: ["health"],
    queryFn: () => api<{ bot: "online" | "offline" }>("/health"),
    refetchInterval: 30_000,
  });
  if (!data || data.bot === "online") return null;
  return (
    <div className="mb-6">
      <Notice tone="warning">{t("botOffline")}</Notice>
    </div>
  );
}
