// Tipos de las respuestas de la API (docs/NEXUS_API_SPEC.md §6).

export type Me = {
  id: string;
  username: string;
  global_name: string | null;
  avatar_url: string;
  locale: "es" | "en";
  timezone: string;
};

export type GuildListItem = {
  id: string;
  name: string;
  icon_url: string | null;
  member_count: number | null;
  bot_present: boolean;
  access: "full";
  invite_url: string | null;
};

export type GuildInfo = {
  id: string;
  name: string;
  icon_url: string | null;
  member_count: number;
  bot_present: boolean;
  access_level: number;
  /** Administra el servidor en Discord: ve todo el panel. */
  full_access?: boolean;
  /** Nivel por sección que le dan sus roles en «Permisos» ({módulo: 1..3}, «*» = todas). */
  module_levels?: Record<string, number>;
  invite_url: string | null;
};

export type ModuleState = {
  module: string;
  category: string;
  available: boolean;
  phase: number;
  toggleable: boolean;
  enabled: boolean;
};

export type AuditEntry = {
  id: string;
  actor: { id: string; name: string | null; avatar_url: string } | null;
  source: "dashboard" | "bot" | "system";
  action: string;
  module: string | null;
  changes: Record<string, { old: unknown; new: unknown }> | null;
  created_at: string;
};

export type Alert = { code: string; severity?: string; permission?: string; intent?: string; module?: string; channel_id?: string };

export type BotStatus = {
  online: boolean;
  latency_ms: number | null;
  last_heartbeat: string | null;
};

export type Overview = {
  guild: GuildInfo;
  bot: BotStatus;
  stats: {
    member_count: number;
    joined_7d: number;
    left_7d: number;
    commands_7d: number;
    modules_enabled: number;
    modules_total: number;
  };
  chart: { day: string; members_joined: number; members_left: number; commands_used: number }[];
  modules: ModuleState[];
  alerts: Alert[];
  recent_activity: AuditEntry[];
};

export type GuildSettings = {
  locale: "es" | "en";
  timezone: string;
  embed_color: number;
  version: number;
  updated_at: string;
  updated_by: string | null;
};

export type Diagnostics = {
  permissions: { permission: string; granted: boolean; required_by: string[] }[];
  intents: { guild_members: boolean | null; message_content: boolean | null };
  issues: Alert[];
  invite_url: string | null;
};

export type Session = {
  id: string;
  current: boolean;
  created_at: string;
  last_seen_at: string;
  ip: string | null;
  user_agent: string | null;
};
