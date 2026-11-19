"use client";

import * as SwitchPrimitive from "@radix-ui/react-switch";
import * as TooltipPrimitive from "@radix-ui/react-tooltip";
import { AlertTriangle, Lock, RefreshCw, type LucideIcon } from "lucide-react";
import Image from "next/image";
import { useTranslations } from "next-intl";
import { forwardRef } from "react";

import { ApiError } from "@/lib/api";
import { cn, initials } from "@/lib/utils";

// --- Botones -----------------------------------------------------------------

type ButtonProps = React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "ghost" | "danger";
  size?: "sm" | "md";
  loading?: boolean;
};

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = "primary", size = "md", loading, className, children, disabled, ...props },
  ref,
) {
  return (
    <button
      ref={ref}
      disabled={disabled || loading}
      className={cn(
        "inline-flex min-h-10 items-center justify-center gap-2 rounded-lg font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50",
        size === "sm" ? "min-h-8 px-3 text-[13px]" : "px-4 text-sm",
        variant === "primary" && "bg-primary-solid text-white hover:bg-primary",
        variant === "secondary" && "border border-border bg-input text-text hover:bg-panel-hover",
        variant === "ghost" && "text-muted hover:bg-panel-hover hover:text-text",
        variant === "danger" && "bg-danger/90 text-white hover:bg-danger",
        className,
      )}
      {...props}
    >
      {loading && <RefreshCw className="size-4 animate-spin" aria-hidden />}
      {children}
    </button>
  );
});

export function LinkButton({
  className,
  variant = "primary",
  ...props
}: React.AnchorHTMLAttributes<HTMLAnchorElement> & { variant?: "primary" | "secondary" }) {
  return (
    <a
      className={cn(
        "inline-flex min-h-10 items-center justify-center gap-2 rounded-lg px-4 text-sm font-medium transition-colors",
        variant === "primary" ? "bg-primary-solid text-white hover:bg-primary" : "border border-border bg-input hover:bg-panel-hover",
        className,
      )}
      {...props}
    />
  );
}

// --- Contenedores ------------------------------------------------------------

export function Card({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("rounded-xl border border-border bg-panel", className)} {...props} />;
}

export function CardHeader({ title, description, action, icon: Icon }: {
  title: React.ReactNode; description?: React.ReactNode; action?: React.ReactNode; icon?: LucideIcon;
}) {
  return (
    <div className="flex items-start justify-between gap-4 border-b border-border px-5 py-4">
      <div className="flex min-w-0 items-start gap-3">
        {Icon && <Icon className="mt-0.5 size-4 shrink-0 text-primary" aria-hidden />}
        <div className="min-w-0">
          <h2 className="text-base font-semibold">{title}</h2>
          {description && <p className="mt-0.5 text-[13px] text-muted">{description}</p>}
        </div>
      </div>
      {action}
    </div>
  );
}

export function PageHeader({ title, description, action }: {
  title: React.ReactNode; description?: React.ReactNode; action?: React.ReactNode;
}) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
        {description && <p className="mt-1 text-muted">{description}</p>}
      </div>
      {action}
    </div>
  );
}

// --- Estados -----------------------------------------------------------------

export function Badge({ tone = "neutral", className, ...props }: React.HTMLAttributes<HTMLSpanElement> & {
  tone?: "neutral" | "primary" | "success" | "warning" | "danger";
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide",
        tone === "neutral" && "bg-input text-muted",
        tone === "primary" && "bg-primary/15 text-primary-text",
        tone === "success" && "bg-success/15 text-success",
        tone === "warning" && "bg-warning/15 text-warning",
        tone === "danger" && "bg-danger/15 text-danger",
        className,
      )}
      {...props}
    />
  );
}

export function StatusDot({ status, label }: { status: "on" | "off" | "warn"; label?: string }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span
        aria-hidden
        className={cn(
          "size-2 rounded-full",
          status === "on" && "bg-success",
          status === "off" && "bg-muted/50",
          status === "warn" && "bg-warning",
        )}
      />
      {label ? <span>{label}</span> : null}
    </span>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("animate-pulse rounded-lg bg-input/70", className)} aria-hidden />;
}

export function EmptyState({ icon: Icon, title, body, action }: {
  icon: LucideIcon; title: string; body?: string; action?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 px-6 py-14 text-center">
      <div className="grid size-12 place-items-center rounded-xl bg-input">
        <Icon className="size-6 text-muted" aria-hidden />
      </div>
      <h3 className="text-base font-semibold">{title}</h3>
      {body && <p className="max-w-md text-muted">{body}</p>}
      {action}
    </div>
  );
}

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const t = useTranslations();
  const api = error instanceof ApiError ? error : null;
  const body = api?.code === "api_unavailable" || !api ? t("states.apiDown") : api.message;
  return (
    <Card>
      <EmptyState
        icon={AlertTriangle}
        title={t("states.errorTitle")}
        body={body}
        action={
          <div className="flex flex-col items-center gap-2">
            {onRetry && (
              <Button variant="secondary" onClick={onRetry}>
                {t("common.retry")}
              </Button>
            )}
            {api && <code className="font-mono text-[11px] text-muted">{api.code}</code>}
          </div>
        }
      />
    </Card>
  );
}

export function Notice({ tone = "warning", icon: Icon = AlertTriangle, children, action }: {
  tone?: "warning" | "danger" | "info"; icon?: LucideIcon; children: React.ReactNode; action?: React.ReactNode;
}) {
  return (
    <div
      role="status"
      className={cn(
        "flex flex-wrap items-center gap-3 rounded-xl border px-4 py-3 text-sm",
        tone === "warning" && "border-warning/30 bg-warning/10",
        tone === "danger" && "border-danger/30 bg-danger/10",
        tone === "info" && "border-primary/30 bg-primary/10",
      )}
    >
      <Icon
        className={cn("size-4 shrink-0", tone === "warning" && "text-warning", tone === "danger" && "text-danger", tone === "info" && "text-primary-text")}
        aria-hidden
      />
      <div className="min-w-0 flex-1">{children}</div>
      {action}
    </div>
  );
}

export function ReadOnlyNotice() {
  const t = useTranslations("states");
  return (
    <Notice tone="info" icon={Lock}>
      {t("readOnly")}
    </Notice>
  );
}

// --- Formularios -------------------------------------------------------------

export function Field({ id, label, help, error, children }: {
  id: string; label: string; help?: React.ReactNode; error?: string; children: React.ReactNode;
}) {
  return (
    <div id={`field-${id}`} className="scroll-mt-24 space-y-1.5 p-1">
      <label htmlFor={id} className="block text-[13px] font-medium">
        {label}
      </label>
      {children}
      {error ? (
        <p id={`${id}-error`} className="text-[13px] text-danger">
          {error}
        </p>
      ) : help ? (
        <p id={`${id}-help`} className="text-[13px] text-muted">
          {help}
        </p>
      ) : null}
    </div>
  );
}

export const inputClass =
  "w-full min-h-10 rounded-lg border border-border bg-input px-3 text-sm text-text placeholder:text-muted/70 focus:border-primary focus:outline-none disabled:opacity-60 aria-[invalid=true]:border-danger";

export function Switch({ checked, onCheckedChange, label, disabled }: {
  checked: boolean; onCheckedChange: (v: boolean) => void; label: string; disabled?: boolean;
}) {
  return (
    <SwitchPrimitive.Root
      checked={checked}
      onCheckedChange={onCheckedChange}
      disabled={disabled}
      aria-label={label}
      className="relative h-6 w-11 shrink-0 rounded-full bg-input transition-colors data-[state=checked]:bg-primary-solid disabled:opacity-50"
    >
      <SwitchPrimitive.Thumb className="block size-5 translate-x-0.5 rounded-full bg-white transition-transform data-[state=checked]:translate-x-[22px]" />
    </SwitchPrimitive.Root>
  );
}

export function Tooltip({ content, children }: { content: React.ReactNode; children: React.ReactNode }) {
  return (
    <TooltipPrimitive.Root>
      <TooltipPrimitive.Trigger asChild>{children}</TooltipPrimitive.Trigger>
      <TooltipPrimitive.Portal>
        <TooltipPrimitive.Content
          sideOffset={6}
          className="z-50 max-w-xs rounded-lg border border-border bg-sidebar px-3 py-2 text-[13px] text-text shadow-lg"
        >
          {content}
        </TooltipPrimitive.Content>
      </TooltipPrimitive.Portal>
    </TooltipPrimitive.Root>
  );
}

// --- Imágenes de Discord -------------------------------------------------------

export function GuildIcon({ name, url, size = 40, className }: { name: string; url: string | null; size?: number; className?: string }) {
  if (url) {
    return (
      <Image src={url} alt="" width={size} height={size} className={cn("shrink-0 rounded-xl", className)} unoptimized />
    );
  }
  return (
    <div
      aria-hidden
      style={{ width: size, height: size, fontSize: Math.max(11, size / 3) }}
      className={cn("grid shrink-0 place-items-center rounded-xl bg-input font-semibold text-muted", className)}
    >
      {initials(name)}
    </div>
  );
}

export function Avatar({ url, size = 32, className }: { url: string; size?: number; className?: string }) {
  return <Image src={url} alt="" width={size} height={size} className={cn("shrink-0 rounded-full", className)} unoptimized />;
}
