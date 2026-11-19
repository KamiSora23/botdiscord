"use client";

import { ChevronDown, Plus, Trash2 } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { isLocal, isMedia, MediaButton, MediaChip } from "@/components/media-picker";
import { Button, Field, inputClass, Switch } from "@/components/ui";
import { VariableInput } from "@/components/variable-input";
import { type Embed, embedChars, emptyEmbed, LIMITS, type MessageTemplate, urlError } from "@/lib/messages";
import { cn, colorToHex, hexToColor } from "@/lib/utils";

function Section({ title, defaultOpen = false, children }: { title: string; defaultOpen?: boolean; children: React.ReactNode }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="border-t border-border first:border-t-0">
      <button type="button" onClick={() => setOpen(!open)} aria-expanded={open} className="flex w-full items-center justify-between py-3 text-left text-sm font-medium">
        {title}
        <ChevronDown className={cn("size-4 text-muted transition-transform", !open && "-rotate-90")} aria-hidden />
      </button>
      {open && <div className="space-y-3 pb-4">{children}</div>}
    </div>
  );
}

function UrlField({ id, label, value, onChange, image }: {
  id: string; label: string; value: string | null; onChange: (v: string | null) => void; image?: boolean;
}) {
  const t = useTranslations("editor");
  const bad = urlError(value) || (!image && (isMedia(value) || isLocal(value)));
  return (
    <Field id={id} label={label} error={bad ? t("invalidUrl") : undefined} help={image ? t("imageHelp") : t("urlHelp")}>
      <div className="flex gap-2">
        {image && (isMedia(value) || isLocal(value)) ? <MediaChip value={value!} onClear={() => onChange(null)} /> : (
          <input id={id} className={cn(inputClass, "font-mono text-[13px]")} value={value ?? ""} placeholder="https://… / {user.avatar}" aria-invalid={bad} onChange={(e) => onChange(e.target.value || null)} />
        )}
        {image && <MediaButton onPick={(u) => onChange(u)} />}
      </div>
    </Field>
  );
}

/** Editor de MessageTemplate (docs/NEXUS_UI_SPEC.md §5.2). `idPrefix` hace únicos los ids de los campos. */
export function MessageEditor({ value, onChange, idPrefix, defaultColor, disabled, extraVariables }: {
  value: MessageTemplate; onChange: (v: MessageTemplate) => void; idPrefix: string; defaultColor: number; disabled?: boolean;
  extraVariables?: readonly string[];
}) {
  const t = useTranslations("editor");
  const embed = value.embeds[0];
  const setEmbed = (patch: Partial<Embed>) => onChange({ ...value, embeds: [{ ...embed!, ...patch }] });
  const total = embed ? embedChars(embed) : 0;

  return (
    <fieldset disabled={disabled} className="space-y-4">
      <Field id={`${idPrefix}-content`} label={t("content")}>
        <VariableInput extraVariables={extraVariables} id={`${idPrefix}-content`} value={value.content ?? ""} onChange={(v) => onChange({ ...value, content: v || null })} max={LIMITS.content} multiline rows={3} placeholder={t("contentPlaceholder")} />
      </Field>

      {!embed ? (
        <Button type="button" variant="secondary" onClick={() => onChange({ ...value, embeds: [emptyEmbed()] })}>
          <Plus className="size-4" aria-hidden /> {t("addEmbed")}
        </Button>
      ) : (
        <div className="rounded-xl border border-border bg-bg/40">
          <div className="flex items-center gap-3 border-b border-border px-4 py-3">
            <span className="h-6 w-1 rounded-full" style={{ background: colorToHex(embed.color ?? defaultColor) }} aria-hidden />
            <span className="flex-1 text-sm font-semibold">Embed</span>
            <label className="flex items-center gap-2 text-[13px] text-muted">
              {t("color")}
              <input
                type="color"
                value={colorToHex(embed.color ?? defaultColor).toLowerCase()}
                onChange={(e) => setEmbed({ color: hexToColor(e.target.value) })}
                className="h-8 w-10 cursor-pointer rounded border border-border bg-input p-0.5"
              />
            </label>
            {embed.color !== null && (
              <button type="button" className="text-[12px] text-muted hover:text-text" onClick={() => setEmbed({ color: null })}>
                {t("useServerColor")}
              </button>
            )}
            <button type="button" onClick={() => onChange({ ...value, embeds: [] })} className="grid size-8 place-items-center rounded-md text-muted hover:bg-panel-hover hover:text-danger" aria-label={t("removeEmbed")}>
              <Trash2 className="size-4" />
            </button>
          </div>
          <div className="px-4">
            <Section title={t("author")}>
              <Field id={`${idPrefix}-author`} label={t("authorName")}>
                <VariableInput extraVariables={extraVariables} id={`${idPrefix}-author`} value={embed.author.name ?? ""} onChange={(v) => setEmbed({ author: { ...embed.author, name: v || null } })} max={LIMITS.author} />
              </Field>
              <UrlField id={`${idPrefix}-author-icon`} label={t("authorIcon")} image value={embed.author.icon_url} onChange={(v) => setEmbed({ author: { ...embed.author, icon_url: v } })} />
            </Section>
            <Section title={t("titleDescription")} defaultOpen>
              <Field id={`${idPrefix}-title`} label={t("title")}>
                <VariableInput extraVariables={extraVariables} id={`${idPrefix}-title`} value={embed.title ?? ""} onChange={(v) => setEmbed({ title: v || null })} max={LIMITS.title} />
              </Field>
              <Field id={`${idPrefix}-description`} label={t("description")}>
                <VariableInput extraVariables={extraVariables} id={`${idPrefix}-description`} value={embed.description ?? ""} onChange={(v) => setEmbed({ description: v || null })} max={LIMITS.description} multiline rows={5} />
              </Field>
              <UrlField id={`${idPrefix}-url`} label={t("titleUrl")} value={embed.url} onChange={(v) => setEmbed({ url: v })} />
            </Section>
            <Section title={t("images")}>
              <UrlField id={`${idPrefix}-thumb`} label={t("thumbnail")} image value={embed.thumbnail_url} onChange={(v) => setEmbed({ thumbnail_url: v })} />
              <UrlField id={`${idPrefix}-image`} label={t("image")} image value={embed.image_url} onChange={(v) => setEmbed({ image_url: v })} />
            </Section>
            <Section title={t("fields", { count: embed.fields.length })}>
              {embed.fields.map((f, i) => (
                <div key={i} className="space-y-2 rounded-lg border border-border p-3">
                  <div className="flex items-center justify-between">
                    <span className="text-[13px] font-medium text-muted">#{i + 1}</span>
                    <div className="flex items-center gap-3">
                      <label className="flex items-center gap-2 text-[13px]">
                        <Switch checked={f.inline} label={t("inline")} onCheckedChange={(v) => setEmbed({ fields: embed.fields.map((x, j) => (j === i ? { ...x, inline: v } : x)) })} />
                        {t("inline")}
                      </label>
                      <button type="button" onClick={() => setEmbed({ fields: embed.fields.filter((_, j) => j !== i) })} className="grid size-8 place-items-center rounded-md text-muted hover:text-danger" aria-label={t("removeField")}>
                        <Trash2 className="size-4" />
                      </button>
                    </div>
                  </div>
                  <VariableInput extraVariables={extraVariables} id={`${idPrefix}-f${i}-name`} placeholder={t("fieldName")} value={f.name} onChange={(v) => setEmbed({ fields: embed.fields.map((x, j) => (j === i ? { ...x, name: v } : x)) })} max={LIMITS.fieldName} />
                  <VariableInput extraVariables={extraVariables} id={`${idPrefix}-f${i}-value`} placeholder={t("fieldValue")} value={f.value} multiline rows={2} onChange={(v) => setEmbed({ fields: embed.fields.map((x, j) => (j === i ? { ...x, value: v } : x)) })} max={LIMITS.fieldValue} />
                </div>
              ))}
              {embed.fields.length < LIMITS.fields && (
                <Button type="button" variant="secondary" size="sm" onClick={() => setEmbed({ fields: [...embed.fields, { name: "", value: "", inline: false }] })}>
                  <Plus className="size-4" aria-hidden /> {t("addField")}
                </Button>
              )}
            </Section>
            <Section title={t("footerTimestamp")}>
              <Field id={`${idPrefix}-footer`} label={t("footer")}>
                <VariableInput extraVariables={extraVariables} id={`${idPrefix}-footer`} value={embed.footer.text ?? ""} onChange={(v) => setEmbed({ footer: { ...embed.footer, text: v || null } })} max={LIMITS.footer} />
              </Field>
              <UrlField id={`${idPrefix}-footer-icon`} label={t("footerIcon")} image value={embed.footer.icon_url} onChange={(v) => setEmbed({ footer: { ...embed.footer, icon_url: v } })} />
              <label className="flex items-center gap-3 text-sm">
                <Switch checked={embed.timestamp} label={t("timestamp")} onCheckedChange={(v) => setEmbed({ timestamp: v })} />
                {t("timestamp")}
              </label>
            </Section>
          </div>
          <div className={cn("border-t border-border px-4 py-2 text-right text-[12px] tabular-nums", total > LIMITS.total ? "text-danger" : "text-muted")}>
            {t("total", { count: total, max: LIMITS.total })}
          </div>
        </div>
      )}
    </fieldset>
  );
}
