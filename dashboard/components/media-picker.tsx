"use client";

import * as Dialog from "@radix-ui/react-dialog";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ImagePlus, Trash2, Upload, X } from "lucide-react";
import { useTranslations } from "next-intl";
import { useParams } from "next/navigation";
import { createContext, useContext, useRef, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui";
import { api, errorText } from "@/lib/api";
import { cn } from "@/lib/utils";

export type MediaPlace = { type: string; name: string };
export type MediaItem = { id: string; url: string; filename: string; content_type: string; size: number; created_at: string; used_in: MediaPlace[] };
export type MediaList = {
  items: MediaItem[]; can_edit: boolean;
  usage: { count: number; bytes: number; max_count: number; max_bytes: number; max_file: number; unused_ttl_days: number };
};

const MEDIA_RE = /^media:\/\/([0-9a-f]{32})$/;
const TYPES = ["image/png", "image/jpeg", "image/gif", "image/webp"];

// --- Imágenes «solo para este envío»: viven en memoria del navegador (local://<id>) y nunca se guardan. ---
const LOCAL_RE = /^local:\/\/([0-9a-f]{32})$/;
const localFiles = new Map<string, { file: File; url: string }>();

/** Activo solo donde el mensaje se envía una vez (herramienta Embeds): ahí se ofrece «Solo enviar». */
export const OneOffContext = createContext(false);

export function addLocalFile(file: File): string {
  const id = Array.from(crypto.getRandomValues(new Uint8Array(16)), (b) => b.toString(16).padStart(2, "0")).join("");
  localFiles.set(id, { file, url: URL.createObjectURL(file) });
  return `local://${id}`;
}

export function localFile(v: string | null | undefined): File | null {
  const m = LOCAL_RE.exec(v ?? "");
  return (m && localFiles.get(m[1])?.file) || null;
}

export const isLocal = (v: string | null | undefined) => LOCAL_RE.test(v ?? "");

/** media://<id> → URL para verla en el panel (la API comprueba que sea de este servidor); local:// → archivo del navegador. */
export function mediaSrc(guildId: string | undefined, v: string | null | undefined): string | null {
  const l = LOCAL_RE.exec(v ?? "");
  if (l) return localFiles.get(l[1])?.url ?? null;
  const m = MEDIA_RE.exec(v ?? "");
  return m && guildId ? `/api/v1/guilds/${guildId}/media/${m[1]}` : null;
}

export const isMedia = (v: string | null | undefined) => MEDIA_RE.test(v ?? "");

export function useOptionalGuildId(): string | undefined {
  return useParams<{ guildId?: string }>()?.guildId;
}

export const mb = (b: number) => `${(b / 1024 / 1024).toFixed(b < 1024 * 1024 ? 2 : 1)} MB`;

/** Botón que abre la galería de imágenes del servidor: subir, elegir y borrar. */
export function MediaButton({ onPick, disabled }: { onPick: (url: string) => void; disabled?: boolean }) {
  const t = useTranslations("media");
  const guildId = useOptionalGuildId();
  const [open, setOpen] = useState(false);
  if (!guildId) return null;
  return (
    <Dialog.Root open={open} onOpenChange={setOpen}>
      <Dialog.Trigger asChild>
        <button type="button" disabled={disabled} title={t("open")} aria-label={t("open")}
          className="grid size-9 shrink-0 place-items-center rounded-lg border border-border bg-input text-muted hover:bg-panel-hover hover:text-text disabled:opacity-50">
          <ImagePlus className="size-4" aria-hidden />
        </button>
      </Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/60" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-50 flex max-h-[min(640px,calc(100vh-32px))] w-[min(640px,calc(100vw-32px))] -translate-x-1/2 -translate-y-1/2 flex-col rounded-xl border border-border bg-sidebar shadow-2xl">
          {open && <Gallery guildId={guildId} onPick={(u) => { onPick(u); setOpen(false); }} />}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

/** Lista, subida y borrado de las imágenes del servidor (compartido por la galería y la página Imágenes). */
export function useMedia(guildId: string, onUploaded?: (item: MediaItem) => void) {
  const t = useTranslations("media");
  const qc = useQueryClient();
  const key = ["media", guildId];
  const list = useQuery({ queryKey: key, queryFn: () => api<MediaList>(`/guilds/${guildId}/media`) });
  const refresh = () => qc.invalidateQueries({ queryKey: key });
  const upload = useMutation({
    mutationFn: (file: File) => {
      const fd = new FormData();
      fd.append("file", file);
      return api<MediaItem>(`/guilds/${guildId}/media`, { method: "POST", body: fd });
    },
    onSuccess: (item) => { refresh(); onUploaded?.(item); toast.success(t("uploaded")); },
    onError: (e) => toast.error(errorText(e, t("uploadError"))),
  });
  const remove = useMutation({
    mutationFn: (id: string) => api(`/guilds/${guildId}/media/${id}`, { method: "DELETE" }),
    onSuccess: () => { refresh(); toast.success(t("deleted")); },
    onError: (e) => toast.error(errorText(e, t("uploadError"))),
  });
  const cleanup = useMutation({
    mutationFn: () => api<{ deleted: number }>(`/guilds/${guildId}/media/cleanup`, { method: "POST" }),
    onSuccess: (r) => { refresh(); toast.success(t("cleaned", { count: r.deleted })); },
    onError: (e) => toast.error(errorText(e, t("uploadError"))),
  });
  const send = (file: File | undefined) => {
    if (!file) return;
    if (!TYPES.includes(file.type)) return void toast.error(t("badType"));
    const max = list.data?.usage.max_file ?? 8 * 1024 * 1024;
    if (file.size > max) return void toast.error(t("tooBig", { max: mb(max) }));
    upload.mutate(file);
  };
  return { list, upload, remove, cleanup, send };
}

/** Zona para subir: clic o arrastrar. */
export function UploadZone({ send, pending, maxFile }: { send: (f: File | undefined) => void; pending: boolean; maxFile?: number }) {
  const t = useTranslations("media");
  const input = useRef<HTMLInputElement>(null);
  const [drag, setDrag] = useState(false);
  return (
    <>
      <button type="button" onClick={() => input.current?.click()} disabled={pending}
        onDragOver={(e) => { e.preventDefault(); setDrag(true); }} onDragLeave={() => setDrag(false)}
        onDrop={(e) => { e.preventDefault(); setDrag(false); send(e.dataTransfer.files[0]); }}
        className={cn("flex w-full flex-col items-center gap-2 rounded-xl border-2 border-dashed p-6 text-center text-sm transition-colors",
          drag ? "border-primary bg-primary/10" : "border-border hover:bg-panel-hover")}>
        <Upload className={cn("size-6 text-muted", pending && "animate-pulse")} aria-hidden />
        <span className="font-medium">{pending ? t("uploading") : t("drop")}</span>
        <span className="text-[12px] text-muted">{t("formats", { max: mb(maxFile ?? 8 * 1024 * 1024) })}</span>
      </button>
      <input ref={input} type="file" accept={TYPES.join(",")} className="hidden" onChange={(e) => { send(e.target.files?.[0]); e.target.value = ""; }} />
    </>
  );
}

function Gallery({ guildId, onPick }: { guildId: string; onPick: (url: string) => void }) {
  const t = useTranslations("media");
  const { list, upload, remove, send } = useMedia(guildId, (item) => onPick(item.url));
  const { data, isLoading } = list;
  const oneOffAllowed = useContext(OneOffContext);
  const [oneOff, setOneOff] = useState(false);
  const sendLocal = (file: File | undefined) => {
    if (!file) return;
    if (!TYPES.includes(file.type)) return void toast.error(t("badType"));
    const max = data?.usage.max_file ?? 8 * 1024 * 1024;
    if (file.size > max) return void toast.error(t("tooBig", { max: mb(max) }));
    onPick(addLocalFile(file));
  };

  return (
    <>
      <div className="flex items-start justify-between gap-4 border-b border-border p-5">
        <div>
          <Dialog.Title className="text-lg font-semibold">{t("title")}</Dialog.Title>
          <Dialog.Description className="mt-1 text-[13px] text-muted">{t("help")}</Dialog.Description>
        </div>
        <Dialog.Close className="rounded-md p-1 text-muted hover:bg-panel-hover hover:text-text" aria-label={t("close")}>
          <X className="size-5" />
        </Dialog.Close>
      </div>
      <div className="space-y-4 overflow-y-auto p-5">
        {oneOffAllowed && (
          <div className="grid grid-cols-2 gap-1 rounded-lg border border-border bg-input p-1 text-[13px]" role="radiogroup" aria-label={t("modeLabel")}>
            {([false, true] as const).map((v) => (
              <button key={String(v)} type="button" role="radio" aria-checked={oneOff === v} onClick={() => setOneOff(v)}
                className={cn("rounded-md px-3 py-1.5 font-medium transition-colors", oneOff === v ? "bg-panel text-text shadow" : "text-muted hover:text-text")}>
                {v ? t("modeOneOff") : t("modeSave")}
              </button>
            ))}
          </div>
        )}
        {oneOff ? (
          <>
            <UploadZone send={sendLocal} pending={false} maxFile={data?.usage.max_file} />
            <p className="text-[12px] text-muted">{t("oneOffHelp")}</p>
          </>
        ) : data?.can_edit !== false && <UploadZone send={send} pending={upload.isPending} maxFile={data?.usage.max_file} />}

        {isLoading ? <p className="text-[13px] text-muted">…</p> : data && data.items.length === 0 ? (
          <p className="text-center text-[13px] text-muted">{t("empty")}</p>
        ) : (
          <ul className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            {data?.items.map((m) => (
              <li key={m.id} className="group relative overflow-hidden rounded-lg border border-border bg-panel">
                <button type="button" onClick={() => onPick(m.url)} className="block w-full" title={m.filename}>
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img src={mediaSrc(guildId, m.url)!} alt={m.filename} className="aspect-square w-full object-cover" loading="lazy" />
                  <span className="block truncate px-2 py-1 text-left text-[11px] text-muted">{m.filename}</span>
                  {m.used_in.length === 0 && <span className="absolute left-1 top-1 rounded bg-black/60 px-1.5 py-0.5 text-[10px] font-medium text-white">{t("unusedShort")}</span>}
                </button>
                <button type="button" aria-label={t("delete")} title={t("delete")} disabled={remove.isPending}
                  onClick={() => { if (window.confirm(t("confirmDelete"))) remove.mutate(m.id); }}
                  className="absolute right-1 top-1 rounded-md bg-black/60 p-1 text-white opacity-0 transition-opacity hover:bg-danger group-hover:opacity-100 focus:opacity-100">
                  <Trash2 className="size-3.5" />
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
      {data && (
        <div className="flex items-center justify-between gap-3 border-t border-border px-5 py-3 text-[12px] text-muted">
          <span>{t("usage", { count: data.usage.count, max: data.usage.max_count, used: mb(data.usage.bytes), total: mb(data.usage.max_bytes) })}</span>
          <Dialog.Close asChild><Button size="sm" variant="secondary">{t("close")}</Button></Dialog.Close>
        </div>
      )}
    </>
  );
}

/** Imagen subida elegida: miniatura + nombre corto + quitar (en lugar del campo de texto con media://…). */
export function MediaChip({ value, onClear, disabled }: { value: string; onClear: () => void; disabled?: boolean }) {
  const t = useTranslations("media");
  const guildId = useOptionalGuildId();
  const src = mediaSrc(guildId, value);
  return (
    <div className="flex min-w-0 flex-1 items-center gap-2 rounded-lg border border-border bg-input px-2 py-1.5">
      {/* eslint-disable-next-line @next/next/no-img-element */}
      {src && <img src={src} alt="" className="size-6 rounded object-cover" />}
      <span className="flex-1 truncate text-[13px]">{isLocal(value) ? `${t("oneOffImage")} · ${localFile(value)?.name ?? ""}` : t("uploadedImage")}</span>
      <button type="button" onClick={onClear} disabled={disabled} aria-label={t("remove")} title={t("remove")} className="rounded p-0.5 text-muted hover:text-text">
        <X className="size-4" />
      </button>
    </div>
  );
}
