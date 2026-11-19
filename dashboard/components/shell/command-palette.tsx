"use client";

import * as Dialog from "@radix-ui/react-dialog";
import { Command } from "cmdk";
import { CornerDownLeft, Search, SlidersHorizontal } from "lucide-react";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { GuildIcon } from "@/components/ui";
import { useGuild, useGuilds } from "@/lib/hooks";
import { ALL_ITEMS, canSee, findItem, isAvailable, SEARCH_OPTIONS } from "@/lib/nav";

export function useCommandPalette() {
  const [open, setOpen] = useState(false);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen((o) => !o);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
  return [open, setOpen] as const;
}

/** Lleva al campo de la página y lo resalta 2 segundos (docs/NEXUS_UI_SPEC.md §3.2). */
export function highlightField(field: string) {
  const tryFocus = (attempt = 0) => {
    const el = document.getElementById(`field-${field}`);
    if (!el) {
      if (attempt < 20) setTimeout(() => tryFocus(attempt + 1), 100);
      return;
    }
    el.scrollIntoView({ behavior: "smooth", block: "center" });
    el.classList.remove("nx-highlight");
    void el.offsetWidth;
    el.classList.add("nx-highlight");
    el.querySelector<HTMLElement>("input,select,button,textarea")?.focus({ preventScroll: true });
  };
  tryFocus();
}

export function CommandPalette({ guildId, open, onOpenChange }: { guildId: string; open: boolean; onOpenChange: (v: boolean) => void }) {
  const t = useTranslations();
  const router = useRouter();
  const { data: guilds } = useGuilds();
  const { data: guild } = useGuild(guildId);

  const go = (path: string, field?: string) => {
    onOpenChange(false);
    router.push(`/dashboard/${guildId}/${path}${field ? `#${field}` : ""}`);
    if (field) highlightField(field);
  };

  const label = (key: string) => (key === "overview" ? t("nav.overview") : t(`nav.items.${key}`));

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/60" />
        <Dialog.Content className="fixed left-1/2 top-[15vh] z-50 w-[min(640px,calc(100vw-32px))] -translate-x-1/2 overflow-hidden rounded-xl border border-border bg-sidebar shadow-2xl">
          <Dialog.Title className="sr-only">{t("palette.placeholder")}</Dialog.Title>
          <Command label={t("palette.placeholder")} className="flex flex-col">
            <div className="flex items-center gap-2 border-b border-border px-4">
              <Search className="size-4 text-muted" aria-hidden />
              <Command.Input
                placeholder={t("palette.placeholder")}
                className="min-h-12 flex-1 bg-transparent text-sm placeholder:text-muted focus:outline-none"
              />
              <kbd className="rounded border border-border px-1.5 font-mono text-[11px] text-muted">Esc</kbd>
            </div>
            <Command.List className="max-h-[50vh] overflow-y-auto p-2 [&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:py-1.5 [&_[cmdk-group-heading]]:text-[11px] [&_[cmdk-group-heading]]:font-semibold [&_[cmdk-group-heading]]:uppercase [&_[cmdk-group-heading]]:tracking-wider [&_[cmdk-group-heading]]:text-muted">
              <Command.Empty className="px-3 py-6 text-center text-muted">{t("palette.empty")}</Command.Empty>
              <Command.Group heading={t("palette.pages")}>
                {ALL_ITEMS.filter((i) => isAvailable(i) && canSee(i, guild)).map((item) => {
                  const Icon = item.icon;
                  return (
                    <Command.Item key={item.key} value={`page ${label(item.key)}`} onSelect={() => go(item.path)} className={itemCls}>
                      <Icon className="size-4 text-muted" aria-hidden />
                      <span className="flex-1">{label(item.key)}</span>
                      <CornerDownLeft className="size-3.5 text-muted opacity-0 group-data-[selected=true]:opacity-100" aria-hidden />
                    </Command.Item>
                  );
                })}
              </Command.Group>
              <Command.Group heading={t("palette.options")}>
                {SEARCH_OPTIONS.filter((o) => { const it = findItem(o.page); return !it || canSee(it, guild); }).map((o) => (
                  <Command.Item key={`${o.page}-${o.field}`} value={`option ${t(o.labelKey)} ${label(o.page)}`} onSelect={() => go(o.page, o.field)} className={itemCls}>
                    <SlidersHorizontal className="size-4 text-muted" aria-hidden />
                    <span className="flex-1">{t(o.labelKey)}</span>
                    <span className="text-[12px] text-muted">{label(o.page)}</span>
                  </Command.Item>
                ))}
              </Command.Group>
              {guilds && guilds.length > 1 && (
                <Command.Group heading={t("palette.servers")}>
                  {guilds
                    .filter((g) => g.bot_present && g.id !== guildId)
                    .map((g) => (
                      <Command.Item
                        key={g.id}
                        value={`server ${g.name}`}
                        onSelect={() => {
                          onOpenChange(false);
                          router.push(`/dashboard/${g.id}/overview`);
                        }}
                        className={itemCls}
                      >
                        <GuildIcon name={g.name} url={g.icon_url} size={20} className="rounded-md" />
                        <span className="flex-1">{g.name}</span>
                      </Command.Item>
                    ))}
                </Command.Group>
              )}
            </Command.List>
          </Command>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

const itemCls =
  "group flex min-h-10 cursor-pointer items-center gap-3 rounded-lg px-3 text-sm data-[selected=true]:bg-panel-hover";
