"use client";

import { Hourglass } from "lucide-react";
import { notFound, useParams } from "next/navigation";
import { useTranslations } from "next-intl";

import { Card, EmptyState, LinkButton } from "@/components/ui";
import { findItem, isAvailable } from "@/lib/nav";

// Páginas de módulos que llegan en fases posteriores.
export default function SoonPage() {
  const t = useTranslations();
  const { guildId, section } = useParams<{ guildId: string; section: string }>();
  const item = findItem(section);
  if (!item || isAvailable(item)) notFound();
  return (
    <Card>
      <EmptyState
        icon={Hourglass}
        title={t("soonPage.title", { name: t(`nav.items.${item.key}`) })}
        body={t("soonPage.body", { phase: item.phase })}
        action={
          <LinkButton href={`/dashboard/${guildId}/overview`} variant="secondary">
            {t("nav.overview")}
          </LinkButton>
        }
      />
    </Card>
  );
}
