"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { KeyRound, Plus, Trash2 } from "lucide-react";
import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { SaveBar } from "@/components/save-bar";
import { Button, Card, CardHeader, EmptyState, ErrorState, inputClass, Notice, PageHeader, Skeleton } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { useGuildId } from "@/lib/hooks";
import { cn, colorToHex } from "@/lib/utils";

type Row = { role_id: string; module: string; level: number };
type Data = { rows: Row[]; modules: string[]; roles: { id: string; name: string; color: number; position: number }[] };

export default function PermissionsPage() {
  const t = useTranslations();
  const guildId = useGuildId();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["permissions", guildId], queryFn: () => api<Data>(`/guilds/${guildId}/permissions`) });
  const [rows, setRows] = useState<Row[] | null>(null);
  const [addRole, setAddRole] = useState("");
  useEffect(() => {
    if (q.data && rows === null) setRows(q.data.rows);
  }, [q.data, rows]);

  const save = useMutation({
    mutationFn: () => api<{ rows: Row[] }>(`/guilds/${guildId}/permissions`, { method: "PUT", json: { rows: (rows ?? []).filter((r) => r.level > 0) } }),
    onSuccess: (res) => {
      qc.setQueryData<Data>(["permissions", guildId], (old) => (old ? { ...old, rows: res.rows } : old));
      setRows(res.rows);
      toast.success(t("settings.saved"));
    },
    onError: (e) => toast.error(e instanceof ApiError ? e.message : t("states.errorBody")),
  });

  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (q.isPending || !rows) return <Skeleton className="h-96" />;

  const data = q.data;
  const roleIds = [...new Set(rows.map((r) => r.role_id))];
  const level = (role: string, mod: string) => rows.find((r) => r.role_id === role && r.module === mod)?.level ?? 0;
  const setLevel = (role: string, mod: string, lv: number) =>
    setRows([...rows.filter((r) => !(r.role_id === role && r.module === mod)), ...(lv ? [{ role_id: role, module: mod, level: lv }] : [])]);
  const dirty = JSON.stringify([...rows].sort(cmp)) !== JSON.stringify([...data.rows].sort(cmp));
  const modLabel = (m: string) => (m === "*" ? t("permissions.all") : m === "settings" ? t("nav.items.settings") : t.has(`nav.items.${m}`) ? t(`nav.items.${m}`) : m);

  return (
    <div className="space-y-6 pb-28">
      <PageHeader title={t("nav.items.permissions")} description={t("permissions.description")} />
      <Notice tone="info" icon={KeyRound}>{t("permissions.managersNote")}</Notice>
      <Card className="overflow-hidden">
        <CardHeader
          title={t("permissions.matrix")}
          description={t("permissions.levelsHelp")}
          action={
            <div className="flex gap-2">
              <select className={cn(inputClass, "w-48")} value={addRole} onChange={(e) => setAddRole(e.target.value)} aria-label={t("permissions.addRole")}>
                <option value="">{t("permissions.addRole")}</option>
                {data.roles.filter((r) => !roleIds.includes(r.id)).map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}
              </select>
              <Button size="sm" variant="secondary" disabled={!addRole} onClick={() => { setLevel(addRole, "*", 1); setAddRole(""); }}>
                <Plus className="size-4" aria-hidden />
              </Button>
            </div>
          }
        />
        {roleIds.length === 0 ? (
          <EmptyState icon={KeyRound} title={t("permissions.empty")} body={t("permissions.emptyBody")} />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[640px] text-left text-sm">
              <thead className="border-b border-border text-[12px] uppercase tracking-wider text-muted">
                <tr>
                  <th className="sticky left-0 bg-panel px-4 py-3 font-semibold">{t("permissions.role")}</th>
                  {data.modules.map((m) => <th key={m} className="px-3 py-3 font-semibold">{modLabel(m)}</th>)}
                  <th className="px-3 py-3"><span className="sr-only">{t("automod.delete")}</span></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {roleIds.map((rid) => {
                  const role = data.roles.find((r) => r.id === rid);
                  return (
                    <tr key={rid}>
                      <td className="sticky left-0 bg-panel px-4 py-2">
                        <span className="inline-flex items-center gap-2">
                          <span className="size-2.5 rounded-full" style={{ background: role?.color ? colorToHex(role.color) : "var(--nx-text-muted)" }} aria-hidden />
                          {role?.name ?? rid}
                        </span>
                      </td>
                      {data.modules.map((m) => (
                        <td key={m} className="px-3 py-2">
                          <select aria-label={`${role?.name} · ${modLabel(m)}`} className={cn(inputClass, "min-h-8 w-28 px-2 text-[13px]", level(rid, m) && "border-primary/50")} value={level(rid, m)} onChange={(e) => setLevel(rid, m, Number(e.target.value))}>
                            {[0, 1, 2, 3].map((lv) => <option key={lv} value={lv}>{t(`permissions.level_${lv}`)}</option>)}
                          </select>
                        </td>
                      ))}
                      <td className="px-3 py-2">
                        <button type="button" className="grid size-8 place-items-center rounded-md text-muted hover:text-danger" aria-label={t("automod.delete")} onClick={() => setRows(rows.filter((r) => r.role_id !== rid))}>
                          <Trash2 className="size-4" />
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>
      <SaveBar dirty={dirty} saving={save.isPending} onSave={() => save.mutate()} onDiscard={() => setRows(data.rows)} />
    </div>
  );
}

function cmp(a: Row, b: Row) {
  return (a.role_id + a.module).localeCompare(b.role_id + b.module);
}
