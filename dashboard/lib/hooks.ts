"use client";

import { useQuery } from "@tanstack/react-query";
import { useParams } from "next/navigation";

import { api } from "./api";
import type { GuildInfo, GuildListItem, Me } from "./types";

export function useMe() {
  return useQuery({ queryKey: ["me"], queryFn: () => api<Me>("/auth/me"), staleTime: 5 * 60_000 });
}

export function useGuilds() {
  return useQuery({
    queryKey: ["guilds"],
    queryFn: () => api<{ data: GuildListItem[] }>("/guilds").then((r) => r.data),
    staleTime: 30_000,
  });
}

export function useGuildId(): string {
  const params = useParams<{ guildId: string }>();
  return params.guildId;
}

export function useGuild(guildId: string) {
  return useQuery({
    queryKey: ["guild", guildId],
    queryFn: () => api<GuildInfo>(`/guilds/${guildId}`),
    staleTime: 30_000,
  });
}
