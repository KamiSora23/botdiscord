"use client";

import * as Dialog from "@radix-ui/react-dialog";
import { AlertCircle } from "lucide-react";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui";
import { cn } from "@/lib/utils";

/**
 * Barra de cambios sin guardar (docs/NEXUS_UI_SPEC.md §5.4): Ctrl+S, aviso al salir y
 * confirmación al navegar a otra página del dashboard.
 */
export function SaveBar({ dirty, saving, errorCount = 0, onSave, onDiscard }: {
  dirty: boolean; saving: boolean; errorCount?: number; onSave: () => void; onDiscard: () => void;
}) {
  const t = useTranslations();
  const router = useRouter();
  const [pendingHref, setPendingHref] = useState<string | null>(null);
  const saveRef = useRef(onSave);
  saveRef.current = onSave;

  useEffect(() => {
    if (!dirty) return;
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") {
        e.preventDefault();
        saveRef.current();
      }
    };
    const onUnload = (e: BeforeUnloadEvent) => {
      e.preventDefault();
    };
    const onClick = (e: MouseEvent) => {
      if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey) return;
      const a = (e.target as HTMLElement).closest("a");
      if (!a || a.target === "_blank" || !a.href) return;
      const url = new URL(a.href);
      if (url.origin !== window.location.origin || url.pathname === window.location.pathname) return;
      e.preventDefault();
      e.stopPropagation();
      setPendingHref(url.pathname + url.search + url.hash);
    };
    window.addEventListener("keydown", onKey);
    window.addEventListener("beforeunload", onUnload);
    document.addEventListener("click", onClick, true);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("beforeunload", onUnload);
      document.removeEventListener("click", onClick, true);
    };
  }, [dirty]);

  return (
    <>
      <div
        aria-hidden={!dirty}
        className={cn(
          "fixed inset-x-0 bottom-0 z-40 px-4 pb-4 transition-all lg:left-[260px] lg:px-6",
          dirty ? "translate-y-0 opacity-100" : "pointer-events-none translate-y-full opacity-0",
        )}
      >
        <div
          role="region"
          aria-live="polite"
          className={cn(
            "mx-auto flex max-w-[1232px] flex-wrap items-center gap-3 rounded-xl border px-4 py-3 shadow-2xl",
            errorCount ? "border-danger/40 bg-[#2a1a1f]" : "border-border bg-sidebar",
          )}
        >
          {errorCount > 0 && <AlertCircle className="size-4 text-danger" aria-hidden />}
          <p className="flex-1 text-sm">{errorCount > 0 ? t("save.errors", { count: errorCount }) : t("save.unsaved")}</p>
          <Button variant="ghost" onClick={onDiscard} disabled={saving}>
            {t("common.discard")}
          </Button>
          <Button onClick={onSave} loading={saving} disabled={errorCount > 0}>
            {saving ? t("common.saving") : t("common.save")}
          </Button>
        </div>
      </div>

      <ConfirmDialog
        open={pendingHref !== null}
        title={t("save.leaveTitle")}
        body={t("save.leaveBody")}
        confirmLabel={t("common.discard")}
        destructive
        onCancel={() => setPendingHref(null)}
        onConfirm={() => {
          const href = pendingHref;
          setPendingHref(null);
          onDiscard();
          if (href) setTimeout(() => router.push(href), 0);
        }}
      />
    </>
  );
}

export function ConfirmDialog({ open, title, body, confirmLabel, cancelLabel, destructive, onConfirm, onCancel, extra }: {
  open: boolean; title: string; body: string; confirmLabel: string; cancelLabel?: string; destructive?: boolean;
  onConfirm: () => void; onCancel: () => void; extra?: React.ReactNode;
}) {
  const t = useTranslations("common");
  return (
    <Dialog.Root open={open} onOpenChange={(o) => !o && onCancel()}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/60" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-50 w-[min(440px,calc(100vw-32px))] -translate-x-1/2 -translate-y-1/2 rounded-xl border border-border bg-sidebar p-6 shadow-2xl">
          <Dialog.Title className="text-lg font-semibold">{title}</Dialog.Title>
          <Dialog.Description className="mt-2 text-muted">{body}</Dialog.Description>
          <div className="mt-6 flex flex-wrap justify-end gap-2">
            <Button variant="secondary" onClick={onCancel}>
              {cancelLabel ?? t("cancel")}
            </Button>
            {extra}
            <Button variant={destructive ? "danger" : "primary"} onClick={onConfirm}>
              {confirmLabel}
            </Button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
