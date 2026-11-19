// MessageTemplate en el navegador: tipos, límites, variables y vista previa (espejo de nexus_core.messages).

export type EmbedField = { name: string; value: string; inline: boolean };
export type Embed = {
  title: string | null;
  description: string | null;
  url: string | null;
  color: number | null;
  author: { name: string | null; icon_url: string | null; url: string | null };
  thumbnail_url: string | null;
  image_url: string | null;
  footer: { text: string | null; icon_url: string | null };
  timestamp: boolean;
  fields: EmbedField[];
};
export type MessageTemplate = { content: string | null; embeds: Embed[] };

export const LIMITS = {
  content: 2000,
  title: 256,
  description: 4096,
  fields: 25,
  fieldName: 256,
  fieldValue: 1024,
  footer: 2048,
  author: 256,
  total: 6000,
};

export const VARIABLES = [
  "user",
  "user.name",
  "user.display_name",
  "user.id",
  "user.avatar",
  "user.created_at",
  "user.joined_at",
  "server",
  "server.id",
  "server.icon",
  "member_count",
  "member_count.ordinal",
  "channel",
] as const;

export const VAR_RE = /\{([a-z_]+(?:\.[a-z_]+)?)\}/g;

export function emptyEmbed(): Embed {
  return {
    title: null,
    description: null,
    url: null,
    color: null,
    author: { name: null, icon_url: null, url: null },
    thumbnail_url: null,
    image_url: null,
    footer: { text: null, icon_url: null },
    timestamp: false,
    fields: [],
  };
}

export function embedChars(e: Embed): number {
  return (
    (e.title ?? "").length +
    (e.description ?? "").length +
    (e.author.name ?? "").length +
    (e.footer.text ?? "").length +
    e.fields.reduce((n, f) => n + f.name.length + f.value.length, 0)
  );
}

export function unknownVariables(text: string | null | undefined): string[] {
  if (!text) return [];
  const out: string[] = [];
  for (const m of text.matchAll(VAR_RE)) if (!(VARIABLES as readonly string[]).includes(m[1]!)) out.push(m[1]!);
  return out;
}

export type SampleContext = {
  userId: string;
  userName: string;
  displayName: string;
  avatarUrl: string;
  serverName: string;
  serverId: string;
  serverIcon: string | null;
  memberCount: number;
  channelName: string | null;
  locale: "es" | "en";
};

function ordinal(n: number, locale: string) {
  if (locale === "es") return `${n}.º`;
  const s = n % 100 >= 10 && n % 100 <= 20 ? "th" : ({ 1: "st", 2: "nd", 3: "rd" } as Record<number, string>)[n % 10] ?? "th";
  return `${n}${s}`;
}

export function sampleValues(ctx: SampleContext): Record<string, string> {
  const date = new Intl.DateTimeFormat(ctx.locale, { dateStyle: "medium" }).format(new Date());
  return {
    user: `<@${ctx.userId}>`,
    "user.name": ctx.userName,
    "user.display_name": ctx.displayName,
    "user.id": ctx.userId,
    "user.avatar": ctx.avatarUrl,
    "user.created_at": date,
    "user.joined_at": date,
    server: ctx.serverName,
    "server.id": ctx.serverId,
    "server.icon": ctx.serverIcon ?? "",
    member_count: String(ctx.memberCount),
    "member_count.ordinal": ordinal(ctx.memberCount, ctx.locale),
    channel: ctx.channelName ? `<#channel:${ctx.channelName}>` : "",
  };
}

export function substitute(text: string | null | undefined, values: Record<string, string>): string {
  if (!text) return "";
  return text.replace(VAR_RE, (m, name: string) => values[name] ?? m);
}

/** Convierte "" en null, como espera la API. */
export function clean(t: MessageTemplate): MessageTemplate {
  const n = (v: string | null) => (v && v.trim() ? v : null);
  return {
    content: n(t.content),
    embeds: t.embeds.map((e) => ({
      ...e,
      title: n(e.title),
      description: n(e.description),
      url: n(e.url),
      thumbnail_url: n(e.thumbnail_url),
      image_url: n(e.image_url),
      author: { name: n(e.author.name), icon_url: n(e.author.icon_url), url: n(e.author.url) },
      footer: { text: n(e.footer.text), icon_url: n(e.footer.icon_url) },
      fields: e.fields.filter((f) => f.name.trim() || f.value.trim()),
    })),
  };
}

export function isEmpty(t: MessageTemplate): boolean {
  const c = clean(t);
  return !c.content && !c.embeds.some((e) => e.title || e.description || e.fields.length || e.image_url || e.thumbnail_url || e.author.name || e.footer.text);
}

const URL_RE = /^(https:\/\/\S+|(?:media|local):\/\/[0-9a-f]{32}|\{[a-z_.]+\})$/;
export function urlError(v: string | null): boolean {
  return Boolean(v && v.trim() && !URL_RE.test(v.trim()));
}
