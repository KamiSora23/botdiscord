"use client";

import { useQuery } from "@tanstack/react-query";
import { useLocale } from "next-intl";

import { api } from "@/lib/api";
import { useGuild, useMe } from "@/lib/hooks";
import type { SampleContext } from "@/lib/messages";
import type { GuildSettings } from "@/lib/types";

/** Datos de ejemplo para la vista previa: tú como miembro nuevo en este servidor. */
export function useSample(guildId: string, channelName: string | null): { sample: SampleContext; color: number } {
  const { data: me } = useMe();
  const { data: guild } = useGuild(guildId);
  const locale = useLocale() as "es" | "en";
  const { data: settings } = useQuery({
    queryKey: ["settings", guildId],
    queryFn: () => api<{ data: GuildSettings; can_edit: boolean }>(`/guilds/${guildId}/settings`),
  });
  return {
    color: settings?.data.embed_color ?? 0x7465f7,
    sample: {
      userId: me?.id ?? "0",
      userName: me?.username ?? "user",
      displayName: me?.global_name ?? me?.username ?? "User",
      avatarUrl: me?.avatar_url ?? "",
      serverName: guild?.name ?? "",
      serverId: guildId,
      serverIcon: guild?.icon_url ?? null,
      memberCount: (guild?.member_count ?? 0) + 1,
      channelName,
      locale: settings?.data.locale ?? locale,
    },
  };
}
