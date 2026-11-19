"use client";

import * as Popover from "@radix-ui/react-popover";
import { Check, ChevronsUpDown, Plus, Search } from "lucide-react";
import { usePathname, useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { GuildIcon, StatusDot } from "@/components/ui";
import { useGuilds } from "@/lib/hooks";
import { cn } from "@/lib/utils";

export function GuildSwitcher({ guildId, onNavigate }: { guildId: string; onNavigate?: () => void }) {
  const t = useTranslations();
  const router = useRouter();
  const pathname = usePathname();
  const { data: guilds } = useGuilds();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const current = guilds?.find((g) => g.id === guildId);

  const select = (id: string, botPresent: boolean, invite: string | null) => {
    setOpen(false);
    if (!botPresent && invite) {
      window.open(invite, "_blank", "noopener,noreferrer");
      return;
    }
    // Conserva la sección actual: /dashboard/A/settings → /dashboard/B/settings
    const section = pathname.split("/")[3] ?? "overview";
    router.push(`/dashboard/${id}/${section}`);
    onNavigate?.();
  };

  const list = (guilds ?? []).filter((g) => g.name.toLowerCase().includes(query.toLowerCase()));

  return (
    <Popover.Root open={open} onOpenChange={setOpen}>
      <Popover.Trigger asChild>
        <button
          type="button"
          className="flex w-full items-center gap-3 rounded-xl border border-border bg-panel/60 p-2.5 text-left hover:bg-panel-hover"
        >
          <GuildIcon name={current?.name ?? "?"} url={current?.icon_url ?? null} size={36} />
          <span className="min-w-0 flex-1">
            <span className="block truncate text-sm font-medium">{current?.name ?? "…"}</span>
            <span className="text-[12px] text-muted">
              <StatusDot status={current?.bot_present ? "on" : "off"} label={current?.bot_present ? t("servers.botActive") : t("servers.notAdded")} />
            </span>
          </span>
          <ChevronsUpDown className="size-4 text-muted" aria-hidden />
        </button>
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content
          align="start"
          sideOffset={6}
          className="z-50 w-[var(--radix-popover-trigger-width)] min-w-64 rounded-xl border border-border bg-sidebar p-2 shadow-xl"
        >
          <label className="relative mb-2 block">
            <span className="sr-only">{t("servers.search")}</span>
            <Search className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted" aria-hidden />
            <input
              autoFocus
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder={t("servers.search")}
              className="min-h-9 w-full rounded-lg bg-input pl-8 pr-2 text-[13px] focus:outline-none"
            />
          </label>
          <ul className="max-h-72 space-y-0.5 overflow-y-auto">
            {list.map((g) => (
              <li key={g.id}>
                <button
                  type="button"
                  onClick={() => select(g.id, g.bot_present, g.invite_url)}
                  className={cn("flex w-full items-center gap-2.5 rounded-lg px-2 py-1.5 text-left text-sm hover:bg-panel-hover", !g.bot_present && "opacity-70")}
                >
                  <GuildIcon name={g.name} url={g.icon_url} size={28} className="rounded-lg" />
                  <span className="flex-1 truncate">{g.name}</span>
                  {g.id === guildId ? <Check className="size-4 text-primary" aria-hidden /> : !g.bot_present && <Plus className="size-4 text-muted" aria-hidden />}
                </button>
              </li>
            ))}
          </ul>
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}
