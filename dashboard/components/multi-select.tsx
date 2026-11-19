"use client";

import * as Popover from "@radix-ui/react-popover";
import { useQuery } from "@tanstack/react-query";
import { Check, ChevronDown, Hash, Search, X } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { useChannels } from "@/components/channel-select";
import { inputClass } from "@/components/ui";
import { api } from "@/lib/api";
import { cn, colorToHex } from "@/lib/utils";

export type Role = { id: string; name: string; color: number; position: number; managed: boolean; is_everyone: boolean; bot_can_assign: boolean };

export function useRoles(guildId: string) {
  return useQuery({
    queryKey: ["roles", guildId],
    queryFn: () => api<{ data: Role[] }>(`/guilds/${guildId}/roles`).then((r) => r.data),
    staleTime: 30_000,
  });
}

type Option = { id: string; label: string; color?: string; icon?: "hash" };

function MultiSelect({ id, options, value, onChange, placeholder, disabled }: {
  id: string; options: Option[]; value: string[]; onChange: (v: string[]) => void; placeholder: string; disabled?: boolean;
}) {
  const t = useTranslations("common");
  const [q, setQ] = useState("");
  const selected = options.filter((o) => value.includes(o.id));
  const list = options.filter((o) => o.label.toLowerCase().includes(q.toLowerCase()));
  const toggle = (oid: string) => onChange(value.includes(oid) ? value.filter((v) => v !== oid) : [...value, oid]);
  return (
    <Popover.Root>
      <div className={cn(inputClass, "flex min-h-10 flex-wrap items-center gap-1.5 py-1.5", disabled && "opacity-60")}>
        {selected.map((o) => (
          <span key={o.id} className="inline-flex items-center gap-1 rounded-md bg-panel-hover px-2 py-0.5 text-[13px]">
            {o.icon === "hash" ? <Hash className="size-3 text-muted" aria-hidden /> : <span className="size-2 rounded-full" style={{ background: o.color ?? "var(--nx-text-muted)" }} aria-hidden />}
            {o.label}
            {!disabled && (
              <button type="button" onClick={() => toggle(o.id)} aria-label={`${t("close")} ${o.label}`} className="text-muted hover:text-text">
                <X className="size-3" />
              </button>
            )}
          </span>
        ))}
        <Popover.Trigger id={id} disabled={disabled} className="ml-auto flex flex-1 items-center justify-end gap-1 text-[13px] text-muted">
          {selected.length === 0 && <span className="flex-1 text-left">{placeholder}</span>}
          <ChevronDown className="size-4" aria-hidden />
        </Popover.Trigger>
      </div>
      <Popover.Portal>
        <Popover.Content align="start" sideOffset={6} className="z-50 w-[var(--radix-popover-trigger-width)] min-w-64 rounded-xl border border-border bg-sidebar p-2 shadow-xl">
          <label className="relative mb-2 block">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted" aria-hidden />
            <input autoFocus value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("search")} className="min-h-9 w-full rounded-lg bg-input pl-8 pr-2 text-[13px] focus:outline-none" />
          </label>
          <ul className="max-h-64 overflow-y-auto" role="listbox" aria-multiselectable>
            {list.map((o) => (
              <li key={o.id} role="option" aria-selected={value.includes(o.id)}>
                <button type="button" onClick={() => toggle(o.id)} className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm hover:bg-panel-hover">
                  {o.icon === "hash" ? <Hash className="size-4 text-muted" aria-hidden /> : <span className="size-2.5 rounded-full" style={{ background: o.color ?? "var(--nx-text-muted)" }} aria-hidden />}
                  <span className="flex-1 truncate">{o.label}</span>
                  {value.includes(o.id) && <Check className="size-4 text-primary" aria-hidden />}
                </button>
              </li>
            ))}
          </ul>
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}

export function RoleMultiSelect({ id, guildId, value, onChange, disabled }: {
  id: string; guildId: string; value: string[]; onChange: (v: string[]) => void; disabled?: boolean;
}) {
  const t = useTranslations("editor");
  const { data } = useRoles(guildId);
  const options = (data ?? [])
    .filter((r) => !r.is_everyone && !r.managed)
    .map((r) => ({ id: r.id, label: r.name, color: r.color ? colorToHex(r.color) : undefined }));
  return <MultiSelect id={id} options={options} value={value} onChange={onChange} placeholder={t("chooseRoles")} disabled={disabled} />;
}

export function ChannelMultiSelect({ id, guildId, value, onChange, disabled }: {
  id: string; guildId: string; value: string[]; onChange: (v: string[]) => void; disabled?: boolean;
}) {
  const t = useTranslations("editor");
  const { data } = useChannels(guildId);
  const options = (data ?? [])
    .filter((c) => c.type === "text" || c.type === "announcement" || c.type === "forum" || c.type === "voice")
    .map((c) => ({ id: c.id, label: c.name, icon: "hash" as const }));
  return <MultiSelect id={id} options={options} value={value} onChange={onChange} placeholder={t("chooseChannels")} disabled={disabled} />;
}

export function RoleSelect({ id, guildId, value, onChange, disabled, allowNone = true }: {
  id: string; guildId: string; value: string | null; onChange: (v: string | null) => void; disabled?: boolean; allowNone?: boolean;
}) {
  const t = useTranslations("editor");
  const { data } = useRoles(guildId);
  return (
    <select id={id} className={inputClass} value={value ?? ""} disabled={disabled} onChange={(e) => onChange(e.target.value || null)}>
      {allowNone && <option value="">{t("chooseRole")}</option>}
      {(data ?? [])
        .filter((r) => !r.is_everyone && !r.managed)
        .map((r) => (
          <option key={r.id} value={r.id}>
            {r.name}
          </option>
        ))}
    </select>
  );
}
