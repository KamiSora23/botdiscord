import { LocaleSync } from "@/components/locale-sync";
import { AppShell } from "@/components/shell/app-shell";

export default async function GuildLayout({ children, params }: { children: React.ReactNode; params: Promise<{ guildId: string }> }) {
  const { guildId } = await params;
  return (
    <>
      <LocaleSync />
      <AppShell guildId={guildId}>{children}</AppShell>
    </>
  );
}
