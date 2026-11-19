"use client";

import { useFormatter, useTranslations } from "next-intl";
import { useDeferredValue } from "react";

import { colorToHex } from "@/lib/utils";
import { type Embed, type MessageTemplate, sampleValues, type SampleContext, substitute } from "@/lib/messages";
import { mediaSrc, useOptionalGuildId } from "@/components/media-picker";

/* Markdown de Discord: **negrita**, *cursiva*, __subrayado__, ~~tachado~~, `código`, ```bloques```,
   ||spoiler||, > citas, # títulos, - listas, [enlaces](https://…) y menciones. */

const INLINE = new RegExp(
  [
    "(`[^`]+`)", // código
    "(\\*\\*[\\s\\S]+?\\*\\*)", // negrita
    "(__[\\s\\S]+?__)", // subrayado
    "(\\*[^*\\n]+\\*|_[^_\\n]+_)", // cursiva
    "(~~[\\s\\S]+?~~)", // tachado
    "(\\|\\|[\\s\\S]+?\\|\\|)", // spoiler
    "(\\[[^\\]]+\\]\\(https?:\\/\\/[^)\\s]+\\))", // enlace
    "(<@!?\\d+>|<#\\d+>|<#channel:[^>]+>|<@&\\d+>)", // menciones
    "(https?:\\/\\/[^\\s<]+)", // URL suelta
  ].join("|"),
);

function inline(text: string, mention: (raw: string) => string, key = "i"): React.ReactNode[] {
  const out: React.ReactNode[] = [];
  let rest = text;
  let i = 0;
  while (rest) {
    const m = INLINE.exec(rest);
    if (!m) {
      out.push(rest);
      break;
    }
    if (m.index > 0) out.push(rest.slice(0, m.index));
    const tok = m[0];
    const k = `${key}-${i++}`;
    if (m[1]) out.push(<code key={k} className="rounded bg-[#1e1f22] px-1 py-0.5 font-mono text-[85%]">{tok.slice(1, -1)}</code>);
    else if (m[2]) out.push(<strong key={k}>{inline(tok.slice(2, -2), mention, k)}</strong>);
    else if (m[3]) out.push(<u key={k}>{inline(tok.slice(2, -2), mention, k)}</u>);
    else if (m[4]) out.push(<em key={k}>{inline(tok.slice(1, -1), mention, k)}</em>);
    else if (m[5]) out.push(<s key={k}>{inline(tok.slice(2, -2), mention, k)}</s>);
    else if (m[6]) out.push(<span key={k} className="rounded bg-[#1e1f22] px-0.5 text-transparent hover:text-inherit">{inline(tok.slice(2, -2), mention, k)}</span>);
    else if (m[7]) {
      const [, label, href] = /^\[([^\]]+)\]\(([^)]+)\)$/.exec(tok)!;
      out.push(<a key={k} className="text-[#00a8fc] hover:underline" href={href} target="_blank" rel="noopener noreferrer">{label}</a>);
    } else if (m[8]) out.push(<span key={k} className="rounded bg-[#5865f2]/30 px-0.5 font-medium text-[#c9cdfb]">{mention(tok)}</span>);
    else if (m[9]) out.push(<span key={k} className="text-[#00a8fc]">{tok}</span>);
    rest = rest.slice(m.index + tok.length);
  }
  return out;
}

export function Markdown({ text, mention }: { text: string; mention: (raw: string) => string }) {
  const blocks: React.ReactNode[] = [];
  const parts = text.split(/(```[\s\S]*?```)/g);
  parts.forEach((part, pi) => {
    if (part.startsWith("```") && part.endsWith("```") && part.length >= 6) {
      const body = part.slice(3, -3).replace(/^[a-z]+\n/, "");
      blocks.push(<pre key={`c${pi}`} className="my-1 overflow-x-auto rounded border border-[#1e1f22] bg-[#2b2d31] p-2 font-mono text-[13px]">{body}</pre>);
      return;
    }
    part.split("\n").forEach((line, li) => {
      const k = `${pi}-${li}`;
      let m: RegExpExecArray | null;
      if ((m = /^(#{1,3}) (.+)$/.exec(line))) {
        const size = m[1]!.length === 1 ? "text-[20px]" : m[1]!.length === 2 ? "text-[18px]" : "text-[16px]";
        blocks.push(<div key={k} className={`${size} my-1 font-bold`}>{inline(m[2]!, mention, k)}</div>);
      } else if ((m = /^> ?(.*)$/.exec(line))) {
        blocks.push(<div key={k} className="border-l-4 border-[#4e5058] pl-3">{inline(m[1]!, mention, k)}</div>);
      } else if ((m = /^[-*] (.+)$/.exec(line))) {
        blocks.push(<div key={k} className="flex gap-2 pl-1"><span aria-hidden>•</span><span>{inline(m[1]!, mention, k)}</span></div>);
      } else {
        blocks.push(<div key={k} className="min-h-[1.375em]">{inline(line, mention, k)}</div>);
      }
    });
  });
  return <>{blocks}</>;
}

export function DiscordPreview({ template, sample, color, botName = "NEXUS", botAvatar, extraValues }: {
  template: MessageTemplate; sample: SampleContext; color: number; botName?: string; botAvatar?: string;
  extraValues?: Record<string, string>;
}) {
  const t = useTranslations("editor");
  const format = useFormatter();
  const tmpl = useDeferredValue(template);
  const values = { ...sampleValues(sample), ...extraValues };
  const mention = (raw: string) => {
    if (raw.startsWith("<#channel:")) return `#${raw.slice(10, -1)}`;
    if (raw.startsWith("<#")) return "#canal";
    if (raw.startsWith("<@&")) return "@rol";
    return `@${sample.displayName}`;
  };
  const now = format.dateTime(new Date(), { hour: "2-digit", minute: "2-digit" });
  const content = substitute(tmpl.content, values);

  return (
    <div className="rounded-xl bg-[#313338] p-4 text-[15px] leading-[1.375] text-[#dbdee1]">
      <div className="flex gap-4">
        <div className="grid size-10 shrink-0 place-items-center overflow-hidden rounded-full bg-primary-solid text-sm font-bold text-white">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          {botAvatar ? <img src={botAvatar} alt="" className="size-10" /> : "N"}
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-1.5">
            <span className="font-medium text-white">{botName}</span>
            <span className="rounded bg-[#5865f2] px-1 text-[10px] font-semibold leading-4 text-white">BOT</span>
            <span className="text-[12px] text-[#949ba4]">{now}</span>
          </div>
          {content && (
            <div className="break-words">
              <Markdown text={content} mention={mention} />
            </div>
          )}
          {tmpl.embeds.map((e, i) => (
            <EmbedView key={i} embed={e} values={values} color={e.color ?? color} mention={mention} />
          ))}
        </div>
      </div>
      <p className="mt-3 text-[11px] text-[#949ba4]">{t("previewNote")}</p>
    </div>
  );
}

function EmbedView({ embed: e, values, color, mention }: {
  embed: Embed; values: Record<string, string>; color: number; mention: (raw: string) => string;
}) {
  const format = useFormatter();
  const guildId = useOptionalGuildId();
  const s = (v: string | null) => substitute(v, values);
  const img = (v: string | null) => {
    const u = s(v);
    return u.startsWith("https://") ? u : mediaSrc(guildId, u);
  };
  const thumb = img(e.thumbnail_url);
  const image = img(e.image_url);
  const has = e.title || e.description || e.fields.length || thumb || image || e.author.name || e.footer.text;
  if (!has) return null;

  // Agrupar campos en filas como Discord (hasta 3 inline por fila).
  const rows: (typeof e.fields)[] = [];
  for (const f of e.fields) {
    const last = rows[rows.length - 1];
    if (f.inline && last && last.length < 3 && last.every((x) => x.inline)) last.push(f);
    else rows.push([f]);
  }

  return (
    <div className="mt-1 grid max-w-[520px] rounded border-l-4 bg-[#2b2d31] py-2 pl-3 pr-4" style={{ borderColor: colorToHex(color) }}>
      <div className="flex gap-4">
        <div className="min-w-0 flex-1 space-y-1.5 pt-0.5">
          {e.author.name && (
            <div className="flex items-center gap-2 text-[14px] font-semibold text-white">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              {img(e.author.icon_url) && <img src={img(e.author.icon_url)!} alt="" className="size-6 rounded-full" />}
              {s(e.author.name)}
            </div>
          )}
          {e.title && <div className="font-semibold text-white"><Markdown text={s(e.title)} mention={mention} /></div>}
          {e.description && <div className="text-[14px]"><Markdown text={s(e.description)} mention={mention} /></div>}
          {rows.map((row, ri) => (
            <div key={ri} className="grid gap-2" style={{ gridTemplateColumns: `repeat(${row.length}, minmax(0, 1fr))` }}>
              {row.map((f, fi) => (
                <div key={fi} className="min-w-0 text-[14px]">
                  <div className="font-semibold text-white">{s(f.name)}</div>
                  <div><Markdown text={s(f.value)} mention={mention} /></div>
                </div>
              ))}
            </div>
          ))}
          {/* eslint-disable-next-line @next/next/no-img-element */}
          {image && <img src={image} alt="" className="mt-2 max-h-72 rounded" />}
          {(e.footer.text || e.timestamp) && (
            <div className="flex items-center gap-2 pt-1 text-[12px] text-[#b5bac1]">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              {img(e.footer.icon_url) && <img src={img(e.footer.icon_url)!} alt="" className="size-5 rounded-full" />}
              <span>
                {s(e.footer.text)}
                {e.footer.text && e.timestamp && " • "}
                {e.timestamp && format.dateTime(new Date(), { dateStyle: "short", timeStyle: "short" })}
              </span>
            </div>
          )}
        </div>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        {thumb && <img src={thumb} alt="" className="size-20 shrink-0 rounded object-cover" />}
      </div>
    </div>
  );
}

