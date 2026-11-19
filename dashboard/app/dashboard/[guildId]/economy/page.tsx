"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Coins, Pencil, Plus, ShoppingBag, Trash2, Wallet } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { toast } from "sonner";

import { ModulePage } from "@/components/module-page";
import { RoleSelect } from "@/components/multi-select";
import { Badge, Button, Card, CardHeader, EmptyState, Field, inputClass, Switch } from "@/components/ui";
import { api, errorText } from "@/lib/api";
import { useGuildId } from "@/lib/hooks";
import { useModuleConfig } from "@/lib/use-module";
import { cn } from "@/lib/utils";

type Cfg = {
  currency_name: string; currency_emoji: string; start_balance: number; daily_amount: number; work_min: number; work_max: number;
  work_cooldown_minutes: number; message_reward: number; message_cooldown_seconds: number; transfers_enabled: boolean; max_balance: number;
  weekly_amount: number; gambling_enabled: boolean; max_bet: number; rob_enabled: boolean;
};
type Item = { id?: string; name: string; description: string | null; price: number; stock: number | null; role_id: string | null; enabled: boolean };

export default function EconomyPage() {
  const t = useTranslations();
  const guildId = useGuildId();
  const qc = useQueryClient();
  const ctl = useModuleConfig<Cfg>(guildId, "economy");
  const form = ctl.form;
  const set = (p: Partial<Cfg>) => form && ctl.setForm({ ...form, ...p });
  const items = useQuery({ queryKey: ["eco-items", guildId], queryFn: () => api<{ data: Item[]; can_edit: boolean }>(`/guilds/${guildId}/economy/items`) });
  const wallets = useQuery({ queryKey: ["eco-wallets", guildId], queryFn: () => api<{ data: { user_id: string; name: string; balance: number }[]; total_supply: number }>(`/guilds/${guildId}/economy/wallets?limit=20`) });
  const [item, setItem] = useState<Item | null>(null);
  const [adjust, setAdjust] = useState({ user_id: "", amount: 100, reason: "" });

  const saveItem = useMutation({
    mutationFn: (it: Item) => {
      const body = { name: it.name, description: it.description || null, price: it.price, stock: it.stock, role_id: it.role_id, enabled: it.enabled };
      return it.id ? api(`/guilds/${guildId}/economy/items/${it.id}`, { method: "PUT", json: body }) : api(`/guilds/${guildId}/economy/items`, { method: "POST", json: body });
    },
    onSuccess: () => { setItem(null); qc.invalidateQueries({ queryKey: ["eco-items", guildId] }); toast.success(t("settings.saved")); },
    onError: (e) => toast.error(errorText(e, t("states.errorBody"))),
  });
  const delItem = useMutation({
    mutationFn: (id: string) => api(`/guilds/${guildId}/economy/items/${id}`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["eco-items", guildId] }),
  });
  const doAdjust = useMutation({
    mutationFn: () => api<{ balance: number }>(`/guilds/${guildId}/economy/wallets/${adjust.user_id}`, { method: "POST", json: { amount: adjust.amount, reason: adjust.reason || null } }),
    onSuccess: (r) => { toast.success(t("economy.adjusted", { balance: r.balance })); qc.invalidateQueries({ queryKey: ["eco-wallets", guildId] }); },
    onError: (e) => toast.error(errorText(e, t("states.errorBody"))),
  });
  const workErr = form && form.work_min > form.work_max;
  const num = (k: keyof Cfg, label: string, max = 1_000_000) => form && (
    <Field id={`eco-${k}`} label={label}><input id={`eco-${k}`} type="number" min={0} max={max} className={inputClass} value={form[k] as number} onChange={(e) => set({ [k]: Number(e.target.value) } as Partial<Cfg>)} /></Field>
  );

  return (
    <ModulePage ctl={ctl as never} title={t("nav.items.economy")} description={t("economy.description")} errorCount={workErr ? 1 : 0}>
      {form && (
        <div className="space-y-6">
          <div className="grid gap-6 lg:grid-cols-2">
            <Card>
              <CardHeader icon={Coins} title={t("economy.currency")} />
              <fieldset disabled={!ctl.canEdit} className="grid gap-4 p-5 sm:grid-cols-2">
                <Field id="eco-name" label={t("economy.currencyName")}><input id="eco-name" className={inputClass} value={form.currency_name} maxLength={30} onChange={(e) => set({ currency_name: e.target.value })} /></Field>
                <Field id="eco-emoji" label="Emoji"><input id="eco-emoji" className={cn(inputClass, "w-24 text-center")} value={form.currency_emoji} maxLength={64} onChange={(e) => set({ currency_emoji: e.target.value })} /></Field>
                {num("start_balance", t("economy.start"))}
                {num("max_balance", t("economy.max"), 1_000_000_000_000)}
                <label className="flex items-center justify-between gap-4 text-sm sm:col-span-2">{t("economy.transfers")}<Switch checked={form.transfers_enabled} label={t("economy.transfers")} onCheckedChange={(v) => set({ transfers_enabled: v })} /></label>
              </fieldset>
            </Card>
            <Card>
              <CardHeader title={t("economy.earning")} description={t("economy.earningHelp")} />
              <fieldset disabled={!ctl.canEdit} className="grid gap-4 p-5 sm:grid-cols-2">
                {num("daily_amount", t("economy.daily"))}
                {num("weekly_amount", t("economy.weekly"), 10_000_000)}
                {num("work_cooldown_minutes", t("economy.workCooldown"), 1440)}
                {num("work_min", t("economy.workMin"))}
                {num("work_max", t("economy.workMax"))}
                {workErr && <p className="text-[13px] text-danger sm:col-span-2">{t("economy.workError")}</p>}
                {num("message_reward", t("economy.messageReward"), 1000)}
                {num("message_cooldown_seconds", t("economy.messageCooldown"), 3600)}
                <label className="flex items-center justify-between gap-4 text-sm sm:col-span-2">{t("economy.gambling")}<Switch checked={form.gambling_enabled} label={t("economy.gambling")} onCheckedChange={(v) => set({ gambling_enabled: v })} /></label>
                {num("max_bet", t("economy.maxBet"), 1_000_000_000)}
                <label className="flex items-center justify-between gap-4 text-sm sm:col-span-2">{t("economy.rob")}<Switch checked={form.rob_enabled} label={t("economy.rob")} onCheckedChange={(v) => set({ rob_enabled: v })} /></label>
              </fieldset>
            </Card>
          </div>

          <Card>
            <CardHeader icon={ShoppingBag} title={t("economy.shop")} action={items.data?.can_edit && <Button size="sm" onClick={() => setItem({ name: "", description: null, price: 100, stock: null, role_id: null, enabled: true })}><Plus className="size-4" aria-hidden /> {t("economy.newItem")}</Button>} />
            {item && (
              <div className="grid gap-3 border-b border-border p-5 sm:grid-cols-2">
                <Field id="it-name" label={t("automod.name")}><input id="it-name" className={inputClass} value={item.name} maxLength={60} onChange={(e) => setItem({ ...item, name: e.target.value })} /></Field>
                <Field id="it-price" label={t("economy.price")}><input id="it-price" type="number" min={0} className={inputClass} value={item.price} onChange={(e) => setItem({ ...item, price: Number(e.target.value) })} /></Field>
                <Field id="it-desc" label={t("editor.description")}><input id="it-desc" className={inputClass} value={item.description ?? ""} maxLength={200} onChange={(e) => setItem({ ...item, description: e.target.value })} /></Field>
                <Field id="it-stock" label={t("economy.stock")} help={t("economy.stockHelp")}><input id="it-stock" type="number" min={0} className={inputClass} value={item.stock ?? ""} onChange={(e) => setItem({ ...item, stock: e.target.value === "" ? null : Number(e.target.value) })} /></Field>
                <Field id="it-role" label={t("economy.givesRole")}><RoleSelect id="it-role" guildId={guildId} value={item.role_id} onChange={(v) => setItem({ ...item, role_id: v })} /></Field>
                <div className="flex items-end gap-2">
                  <Button loading={saveItem.isPending} disabled={!item.name.trim()} onClick={() => saveItem.mutate(item)}>{t("common.save")}</Button>
                  <Button variant="ghost" onClick={() => setItem(null)}>{t("common.cancel")}</Button>
                </div>
              </div>
            )}
            {!items.data?.data.length ? <EmptyState icon={ShoppingBag} title={t("economy.shopEmpty")} /> : (
              <ul className="divide-y divide-border">
                {items.data.data.map((it) => (
                  <li key={it.id} className="flex flex-wrap items-center gap-3 px-5 py-3 text-sm">
                    <span className="font-medium">{it.name}</span>
                    <span className="text-muted">{it.price.toLocaleString()} {form.currency_emoji}</span>
                    {it.stock !== null && <Badge>{t("economy.stockLeft", { n: it.stock })}</Badge>}
                    {!it.enabled && <Badge>{t("common.disabled")}</Badge>}
                    <span className="ml-auto flex gap-1">
                      {items.data.can_edit && <Button variant="ghost" size="sm" onClick={() => setItem(it)} aria-label={t("automod.edit")}><Pencil className="size-4" /></Button>}
                      {items.data.can_edit && <Button variant="ghost" size="sm" onClick={() => it.id && delItem.mutate(it.id)} aria-label={t("automod.delete")}><Trash2 className="size-4" /></Button>}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </Card>

          <div className="grid gap-6 lg:grid-cols-2">
            <Card className="overflow-hidden">
              <CardHeader icon={Wallet} title={t("economy.richest")} description={t("economy.supply", { total: (wallets.data?.total_supply ?? 0).toLocaleString(), emoji: form.currency_emoji })} />
              {!wallets.data?.data.length ? <p className="px-5 py-6 text-center text-[13px] text-muted">{t("economy.noWallets")}</p> : (
                <ul className="divide-y divide-border">
                  {wallets.data.data.map((w, i) => (
                    <li key={w.user_id} className="flex items-center gap-3 px-5 py-2.5 text-sm">
                      <span className="w-8 font-mono text-muted">#{i + 1}</span>
                      <button type="button" className="min-w-0 flex-1 truncate text-left hover:underline" onClick={() => setAdjust({ ...adjust, user_id: w.user_id })}>{w.name}</button>
                      <span className="font-mono">{w.balance.toLocaleString()} {form.currency_emoji}</span>
                    </li>
                  ))}
                </ul>
              )}
            </Card>
            {ctl.canManage && (
              <Card className="h-fit">
                <CardHeader title={t("economy.adjust")} description={t("economy.adjustHelp")} />
                <div className="space-y-3 p-5">
                  <Field id="adj-user" label={t("economy.userId")}><input id="adj-user" className={cn(inputClass, "font-mono")} value={adjust.user_id} onChange={(e) => setAdjust({ ...adjust, user_id: e.target.value.replace(/\D/g, "") })} /></Field>
                  <Field id="adj-amount" label={t("economy.amount")} help={t("economy.amountHelp")}><input id="adj-amount" type="number" className={inputClass} value={adjust.amount} onChange={(e) => setAdjust({ ...adjust, amount: Number(e.target.value) })} /></Field>
                  <Field id="adj-reason" label={t("moderation.reason")}><input id="adj-reason" className={inputClass} value={adjust.reason} maxLength={200} onChange={(e) => setAdjust({ ...adjust, reason: e.target.value })} /></Field>
                  <Button disabled={adjust.user_id.length < 15 || !adjust.amount} loading={doAdjust.isPending} onClick={() => doAdjust.mutate()}>{t("economy.apply")}</Button>
                </div>
              </Card>
            )}
          </div>
          <p className="text-[12px] text-muted">{t("economy.disclaimer")}</p>
        </div>
      )}
    </ModulePage>
  );
}
