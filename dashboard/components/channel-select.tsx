"use client";

import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, Hash, Megaphone } from "lucide-react";
import { useTranslations } from "next-intl";

import { inputClass, Tooltip } from "@/components/ui";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

export type Channel = {
  id: string;
  name: string;
  type: "text" | "voice" | "category" | "announcement" | "forum";
  parent_id: string | null;
  position: number;
  bot_can_view: boolean;
  bot_can_send: boolean;
  bot_can_embed: boolean;
};

export function useChannels(guildId: string) {
  return useQuery({
    queryKey: ["channels", guildId],
    queryFn: () => api<{ data: Channel[] }>(`/guilds/${guildId}/channels`).then((r) => r.data),
    staleTime: 30_000,
  });
}

/** Selector de canales de texto agrupado por categoría, con aviso si el bot no puede escribir. */
export function ChannelSelect({ id, guildId, value, onChange, needEmbed = false, invalid, disabled, noneLabel, compact }: {
  id: string; guildId: string; value: string | null; onChange: (v: string | null) => void; needEmbed?: boolean;
  invalid?: boolean; disabled?: boolean; noneLabel?: string; compact?: boolean;
}) {
  const t = useTranslations("editor");
  const { data: channels, isPending } = useChannels(guildId);
  const text = (channels ?? []).filter((c) => c.type === "text" || c.type === "announcement");
  const categories = (channels ?? []).filter((c) => c.type === "category").sort((a, b) => a.position - b.position);
  const groups = [
    { id: null as string | null, name: null as string | null, items: text.filter((c) => !c.parent_id) },
    ...categories.map((cat) => ({ id: cat.id, name: cat.name, items: text.filter((c) => c.parent_id === cat.id) })),
  ].filter((g) => g.items.length);
  const selected = text.find((c) => c.id === value);
  const problem = selected && (!selected.bot_can_send ? t("botCannotSend") : needEmbed && !selected.bot_can_embed ? t("botCannotEmbed") : null);

  return (
    <div className="flex items-center gap-2">
      <div className="relative flex-1">
        {selected?.type === "announcement" ? (
          <Megaphone className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted" aria-hidden />
        ) : (
          <Hash className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted" aria-hidden />
        )}
        <select
          id={id}
          className={cn(inputClass, "pl-9", compact && "min-h-8 py-1 text-[13px]")}
          value={value ?? ""}
          disabled={disabled || isPending}
          aria-invalid={invalid}
          onChange={(e) => onChange(e.target.value || null)}
        >
          <option value="">{isPending ? "…" : noneLabel ?? t("chooseChannel")}</option>
          {value && !selected && !isPending && <option value={value}>{t("deletedChannel")}</option>}
          {groups.map((g) => (
            <optgroup key={g.id ?? "none"} label={g.name ?? "—"}>
              {g.items
                .sort((a, b) => a.position - b.position)
                .map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.bot_can_send ? "" : "⚠ "}#{c.name}
                  </option>
                ))}
            </optgroup>
          ))}
        </select>
      </div>
      {problem && (
        <Tooltip content={problem}>
          <span className="grid size-10 place-items-center rounded-lg border border-warning/40 bg-warning/10" role="img" aria-label={problem}>
            <AlertTriangle className="size-4 text-warning" />
          </span>
        </Tooltip>
      )}
    </div>
  );
}
