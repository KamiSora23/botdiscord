"use client";

import { useMutation } from "@tanstack/react-query";
import { CheckCircle2, ExternalLink, FilePlus2, Send } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { toast } from "sonner";

import { ChannelSelect, useChannels } from "@/components/channel-select";
import { DiscordPreview } from "@/components/discord-preview";
import { isLocal, localFile, OneOffContext } from "@/components/media-picker";
import { MessageEditor } from "@/components/message-editor";
import { ConfirmDialog } from "@/components/save-bar";
import { Button, Card, CardHeader, Field, PageHeader } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { useGuildId } from "@/lib/hooks";
import { clean, type Embed, emptyEmbed, isEmpty, type MessageTemplate } from "@/lib/messages";
import { useSample } from "@/lib/use-sample";

const DRAFT_KEY = (g: string) => `nexus.embed-draft.${g}`;
const ONE_OFF_PLACEHOLDER = "https://one-off.nexus.invalid/";

/** Huecos de imagen del embed: [nombre del hueco que entiende la API, leer, escribir]. */
const SLOTS: [string, (e: Embed) => string | null, (e: Embed, v: string | null) => Embed][] = [
  ["image_url", (e) => e.image_url, (e, v) => ({ ...e, image_url: v })],
  ["thumbnail_url", (e) => e.thumbnail_url, (e, v) => ({ ...e, thumbnail_url: v })],
  ["author.icon_url", (e) => e.author.icon_url, (e, v) => ({ ...e, author: { ...e.author, icon_url: v } })],
  ["footer.icon_url", (e) => e.footer.icon_url, (e, v) => ({ ...e, footer: { ...e.footer, icon_url: v } })],
];

/** Las imágenes «solo enviar» no sobreviven a recargar la página: se quitan del borrador. */
function dropMissingLocal(m: MessageTemplate): MessageTemplate {
  return { ...m, embeds: m.embeds.map((e) => SLOTS.reduce((acc, [, get, set]) => (isLocal(get(acc)) && !localFile(get(acc)) ? set(acc, null) : acc), e)) };
}

/** JSON normal, o multipart con las imágenes de un solo envío (no se guardan en el servidor). */
function sendBody(channel: string | null, msg: MessageTemplate): { json: unknown } | { body: FormData } {
  const files: [string, File][] = [];
  const embeds = msg.embeds.map((e, i) => SLOTS.reduce((acc, [slot, get, set]) => {
    const f = localFile(get(acc));
    if (!isLocal(get(acc))) return acc;
    if (i === 0 && f) files.push([slot, f]);
    return set(acc, i === 0 && f ? ONE_OFF_PLACEHOLDER + slot : null);
  }, e));
  const payload = { channel_id: channel, message: clean({ ...msg, embeds }) };
  if (!files.length) return { json: payload };
  const fd = new FormData();
  fd.append("payload", JSON.stringify(payload));
  for (const [slot, f] of files) fd.append(`file:${slot}`, f, f.name);
  return { body: fd };
}

const blank = (): MessageTemplate => ({ content: null, embeds: [{ ...emptyEmbed(), title: "", description: "" }] });

function loadDraft(guildId: string): MessageTemplate {
  try {
    const raw = localStorage.getItem(DRAFT_KEY(guildId));
    if (raw) return dropMissingLocal(JSON.parse(raw) as MessageTemplate);
  } catch {
    // sin borrador guardado
  }
  return blank();
}

export default function EmbedsPage() {
  const t = useTranslations();
  const guildId = useGuildId();
  const [msg, setMsg] = useState<MessageTemplate>(() => (typeof window === "undefined" ? { content: null, embeds: [emptyEmbed()] } : loadDraft(guildId)));
  const [channel, setChannel] = useState<string | null>(null);
  const [last, setLast] = useState<{ url: string; channel: string } | null>(null);
  const [askNew, setAskNew] = useState(false);
  // Cambia la «key» del editor para que se vacíe también lo que tenga abierto (secciones, campos).
  const [editorKey, setEditorKey] = useState(0);
  const { data: channels } = useChannels(guildId);
  const { sample, color } = useSample(guildId, channels?.find((c) => c.id === channel)?.name ?? null);

  const update = (m: MessageTemplate) => {
    setMsg(m);
    try {
      localStorage.setItem(DRAFT_KEY(guildId), JSON.stringify(m));
    } catch {
      // almacenamiento no disponible
    }
  };

  const startNew = () => {
    update(blank());
    setLast(null);
    setAskNew(false);
    setEditorKey((k) => k + 1);
  };

  const send = useMutation({
    mutationFn: () => api<{ url: string }>(`/guilds/${guildId}/embeds/send`, { method: "POST", ...sendBody(channel, msg) }),
    onSuccess: (r) => {
      setLast({ url: r.url, channel: channels?.find((c) => c.id === channel)?.name ?? "" });
      toast.success(t("embeds.sent"));
    },
    onError: (err) => toast.error(err instanceof ApiError ? (t.has(`welcome.err_${err.code}`) ? t(`welcome.err_${err.code}`) : err.message) : t("states.errorBody")),
  });

  return (
    <div className="space-y-6">
      <PageHeader title={t("nav.items.embeds")} description={t("embeds.description")} />
      <div className="grid items-start gap-6 xl:grid-cols-[minmax(0,1fr)_minmax(0,440px)]">
        <Card>
          <CardHeader title={t("embeds.compose")} action={
            <Button size="sm" variant="secondary" disabled={isEmpty(msg) && !last} onClick={() => (isEmpty(msg) ? startNew() : setAskNew(true))}>
              <FilePlus2 className="size-4" aria-hidden /> {t("embeds.new")}
            </Button>
          } />
          <div className="space-y-5 p-5">
            <Field id="embed-channel" label={t("welcome.channel")}>
              <ChannelSelect id="embed-channel" guildId={guildId} value={channel} onChange={setChannel} needEmbed />
            </Field>
            <OneOffContext.Provider value={true}>
              <MessageEditor key={editorKey} idPrefix="tool" value={msg} onChange={update} defaultColor={color} />
            </OneOffContext.Provider>
          </div>
        </Card>
        <div className="space-y-3 xl:sticky xl:top-24">
          <h2 className="text-sm font-semibold">{t("editor.preview")}</h2>
          <DiscordPreview template={msg} sample={sample} color={color} />
          <Button className="w-full" disabled={!channel || isEmpty(msg)} loading={send.isPending} onClick={() => send.mutate()}>
            <Send className="size-4" aria-hidden /> {t("embeds.send")}
          </Button>
          {last && (
            <div className="space-y-3 rounded-xl border border-success/40 bg-success/10 p-4">
              <p className="flex items-center gap-2 text-sm font-medium">
                <CheckCircle2 className="size-4 text-success" aria-hidden /> {t("embeds.sentTo", { channel: last.channel })}
              </p>
              <p className="text-[12px] text-muted">{t("embeds.afterSend")}</p>
              <div className="flex flex-wrap gap-2">
                <Button size="sm" onClick={startNew}><FilePlus2 className="size-4" aria-hidden /> {t("embeds.new")}</Button>
                <Button size="sm" variant="secondary" onClick={() => setLast(null)}>{t("embeds.keepEditing")}</Button>
                <a href={last.url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1.5 px-2 text-[13px] text-primary-text hover:underline">
                  {t("embeds.openInDiscord")} <ExternalLink className="size-3.5" aria-hidden />
                </a>
              </div>
            </div>
          )}
          <p className="text-[12px] text-muted">{t("embeds.help")}</p>
        </div>
      </div>
      <ConfirmDialog open={askNew} destructive title={t("embeds.newTitle")} body={t("embeds.newBody")}
        confirmLabel={t("embeds.new")} onCancel={() => setAskNew(false)} onConfirm={startNew} />
    </div>
  );
}
