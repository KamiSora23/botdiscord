import {
  Award,
  BarChart3,
  Bot,
  Bug,
  CalendarDays,
  Coins,
  Gauge,
  Gift,
  Headphones,
  Hand,
  History,
  KeyRound,
  LayoutDashboard,
  ListChecks,
  type LucideIcon,
  Megaphone,
  MessageCircleReply,
  Mic,
  Images,
  MessageSquareQuote,
  PlugZap,
  ScrollText,
  Settings,
  Shield,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  Star,
  Stethoscope,
  Tags,
  Terminal,
  Ticket,
  UserPlus,
  Users,
  Vote,
  Wand2,
} from "lucide-react";

export const CURRENT_PHASE = 8;

export type NavItem = {
  key: string; // clave de traducción en nav.items y segmento de la URL
  path: string;
  icon: LucideIcon;
  phase: number;
  module?: string; // módulo del registro (para el punto de estado)
};

export type NavGroup = { key: string; items: NavItem[] };

export const OVERVIEW: NavItem = { key: "overview", path: "overview", icon: LayoutDashboard, phase: 1 };

export const NAV_GROUPS: NavGroup[] = [
  {
    key: "general",
    items: [
      { key: "setup", path: "setup", icon: Wand2, phase: 8 },
      { key: "settings", path: "settings", icon: Settings, phase: 1 },
      { key: "welcome", path: "welcome", icon: Hand, phase: 2, module: "welcome" },
      { key: "embeds", path: "embeds", icon: MessageSquareQuote, phase: 2, module: "embeds" },
      { key: "images", path: "images", icon: Images, phase: 2 },
    ],
  },
  {
    key: "moderation",
    items: [
      { key: "moderation", path: "moderation", icon: Shield, phase: 3, module: "moderation" },
      { key: "automod", path: "automod", icon: ShieldAlert, phase: 3, module: "automod" },
      { key: "antiraid", path: "antiraid", icon: ShieldCheck, phase: 7, module: "antiraid" },
      { key: "honeypot", path: "honeypot", icon: Bug, phase: 7, module: "honeypot" },
      { key: "ai_moderation", path: "ai-moderation", icon: Sparkles, phase: 7, module: "ai_moderation" },
      { key: "logging", path: "logging", icon: ScrollText, phase: 3, module: "logging" },
    ],
  },
  {
    key: "roles",
    items: [
      { key: "autoroles", path: "autoroles", icon: UserPlus, phase: 4, module: "autoroles" },
      { key: "reaction_roles", path: "reaction-roles", icon: Tags, phase: 4, module: "reaction_roles" },
      { key: "members", path: "members", icon: Users, phase: 4 },
    ],
  },
  {
    key: "community",
    items: [
      { key: "tickets", path: "tickets", icon: Ticket, phase: 5, module: "tickets" },
      { key: "suggestions", path: "suggestions", icon: ListChecks, phase: 5, module: "suggestions" },
      { key: "starboard", path: "starboard", icon: Star, phase: 5, module: "starboard" },
      { key: "polls", path: "polls", icon: Vote, phase: 5, module: "polls" },
      { key: "giveaways", path: "giveaways", icon: Gift, phase: 5, module: "giveaways" },
      { key: "events", path: "events", icon: CalendarDays, phase: 7, module: "events" },
      { key: "custom_commands", path: "custom-commands", icon: Terminal, phase: 5, module: "custom_commands" },
      { key: "responses", path: "responses", icon: MessageCircleReply, phase: 7, module: "responses" },
    ],
  },
  {
    key: "progression",
    items: [
      { key: "levels", path: "levels", icon: Award, phase: 6, module: "levels" },
      { key: "economy", path: "economy", icon: Coins, phase: 6, module: "economy" },
    ],
  },
  {
    key: "utility",
    items: [
      { key: "scheduled_messages", path: "scheduled-messages", icon: Megaphone, phase: 5, module: "scheduled_messages" },
      { key: "integrations", path: "integrations", icon: PlugZap, phase: 7, module: "integrations" },
      { key: "tempvoice", path: "tempvoice", icon: Mic, phase: 7, module: "tempvoice" },
      { key: "voice_activity", path: "voice-activity", icon: Headphones, phase: 7, module: "voice_activity" },
      { key: "counters", path: "counters", icon: Gauge, phase: 7, module: "counters" },
      { key: "analytics", path: "analytics", icon: BarChart3, phase: 8 },
    ],
  },
  {
    key: "advanced",
    items: [
      { key: "permissions", path: "permissions", icon: KeyRound, phase: 3 },
      { key: "diagnostics", path: "diagnostics", icon: Stethoscope, phase: 1 },
      { key: "audit_log", path: "audit-log", icon: History, phase: 1 },
    ],
  },
];

export const ALL_ITEMS: NavItem[] = [OVERVIEW, ...NAV_GROUPS.flatMap((g) => g.items)];

// Secciones con editor de mensajes: con permiso en cualquiera se puede usar «Imágenes» (igual que en la API).
const IMAGE_MODULES = ["embeds", "welcome", "scheduled_messages", "events", "tickets", "reaction_roles",
  "custom_commands", "responses", "honeypot", "antiraid", "integrations", "levels"];

/** ¿Puede esta persona abrir la sección? Quien administra el servidor, todo; el resto, lo que dé «Permisos». */
export function canSee(item: NavItem, guild: { full_access?: boolean; module_levels?: Record<string, number> } | undefined): boolean {
  if (!guild || guild.full_access !== false) return true; // cargando o acceso total
  const levels = guild.module_levels ?? {};
  const lv = (m: string) => Math.max(levels["*"] ?? 0, levels[m] ?? 0);
  if (item.module) return lv(item.module) > 0;
  switch (item.key) {
    case "settings": return lv("settings") > 0;
    case "setup": return (levels["*"] ?? 0) >= 3;
    case "permissions": return false; // solo quien administra el servidor
    case "members": return lv("moderation") > 0;
    case "images": return IMAGE_MODULES.some((m) => lv(m) > 0);
    default: return true; // Overview, Analytics, Diagnóstico, Historial: lectura con cualquier permiso
  }
}

export function isAvailable(item: NavItem): boolean {
  return item.phase <= CURRENT_PHASE;
}

export function findItem(path: string): NavItem | undefined {
  return ALL_ITEMS.find((i) => i.path === path);
}

export const SHOW_UPCOMING = process.env.NEXT_PUBLIC_SHOW_UPCOMING !== "false";

export const BOT_ICON = Bot;

// Opciones concretas que encuentra la búsqueda global. `field` es el id del campo en la página.
export const SEARCH_OPTIONS: { page: string; field: string; labelKey: string }[] = [
  { page: "settings", field: "locale", labelKey: "settings.locale" },
  { page: "settings", field: "timezone", labelKey: "settings.timezone" },
  { page: "settings", field: "embed_color", labelKey: "settings.embedColor" },
  { page: "welcome", field: "join-channel", labelKey: "welcome.channel" },
  { page: "welcome", field: "join-content", labelKey: "welcome.message" },
  { page: "welcome", field: "join-delete", labelKey: "welcome.deleteAfter" },
  { page: "diagnostics", field: "permissions", labelKey: "diagnostics.permissionsTitle" },
  { page: "diagnostics", field: "intents", labelKey: "diagnostics.intentsTitle" },
];
