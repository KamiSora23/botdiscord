"use client";

import * as Popover from "@radix-ui/react-popover";
import { CalendarDays, ChevronLeft, ChevronRight, Clock } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useEffect, useMemo, useRef, useState } from "react";

import { toLocalInput } from "@/lib/datetime";
import { cn } from "@/lib/utils";

/** Selector de fecha y hora con el estilo del panel. Valor: "YYYY-MM-DDTHH:mm" en la hora local del navegador. */
export function DateTimePicker({ id, value, onChange, minDate, invalid }: {
  id: string; value: string; onChange: (v: string) => void; minDate?: Date; invalid?: boolean;
}) {
  const t = useTranslations("picker");
  const locale = useLocale();
  const selected = parse(value);
  const min = minDate ?? null;
  const [open, setOpen] = useState(false);
  const [view, setView] = useState(() => {
    const base = selected ?? new Date();
    return new Date(base.getFullYear(), base.getMonth(), 1);
  });

  const fmtMonth = new Intl.DateTimeFormat(locale, { month: "long", year: "numeric" });
  const fmtLabel = new Intl.DateTimeFormat(locale, { weekday: "short", day: "numeric", month: "short", year: "numeric" });
  const fmtLong = new Intl.DateTimeFormat(locale, { weekday: "long", day: "numeric", month: "long", year: "numeric" });
  const weekdays = useMemo(() => {
    const f = new Intl.DateTimeFormat(locale, { weekday: "short" });
    return Array.from({ length: 7 }, (_, i) => f.format(new Date(2024, 0, 1 + i))); // 1 ene 2024 = lunes
  }, [locale]);

  // Rejilla del mes empezando en lunes.
  const days = useMemo(() => {
    const first = new Date(view.getFullYear(), view.getMonth(), 1);
    const offset = (first.getDay() + 6) % 7;
    return Array.from({ length: 42 }, (_, i) => new Date(view.getFullYear(), view.getMonth(), 1 - offset + i));
  }, [view]);

  const today = startOfDay(new Date());
  const minDay = min ? startOfDay(min) : null;
  const hour = selected?.getHours() ?? 9;
  const minute = selected ? selected.getMinutes() : 0;
  const isMinDay = !!(selected && minDay && sameDay(selected, minDay));

  const commit = (d: Date) => {
    // Nunca por debajo del mínimo: si la hora elegida ya pasó hoy, se sube a la próxima disponible.
    if (min && d.getTime() < min.getTime()) d = roundUp(min);
    onChange(toLocalInput(d));
  };
  const pickDay = (d: Date) => commit(new Date(d.getFullYear(), d.getMonth(), d.getDate(), hour, minute));
  const pickTime = (h: number, m: number) => {
    const base = selected ?? (min ? roundUp(min) : new Date());
    commit(new Date(base.getFullYear(), base.getMonth(), base.getDate(), h, m));
  };

  const presets: { label: string; date: Date }[] = (() => {
    const now = new Date();
    const inHour = roundUp(new Date(now.getTime() + 3_600_000));
    const tonight = new Date(now.getFullYear(), now.getMonth(), now.getDate(), 20, 0);
    const tomorrow = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1, 9, 0);
    const monday = new Date(now.getFullYear(), now.getMonth(), now.getDate() + ((8 - now.getDay()) % 7 || 7), 9, 0);
    return [
      { label: t("inHour"), date: inHour },
      { label: t("tonight"), date: tonight },
      { label: t("tomorrow"), date: tomorrow },
      { label: t("monday"), date: monday },
    ].filter((p) => !min || p.date.getTime() >= min.getTime());
  })();

  const canPrev = !minDay || new Date(view.getFullYear(), view.getMonth(), 0) >= minDay;
  const minutes = Array.from({ length: 12 }, (_, i) => i * 5);

  return (
    <Popover.Root open={open} onOpenChange={setOpen}>
      <Popover.Trigger id={id} aria-invalid={invalid}
        className={cn("flex min-h-10 w-full items-center gap-2 rounded-lg border bg-input px-3 text-left text-sm transition-colors hover:border-primary/60",
          invalid ? "border-danger" : "border-border", !selected && "text-muted")}>
        <CalendarDays className="size-4 shrink-0 text-primary-text" aria-hidden />
        <span className="flex-1 truncate">
          {selected ? <><span>{cap(fmtLabel.format(selected))}</span> · <span className="font-medium tabular-nums">{pad(hour)}:{pad(minute)}</span></> : t("choose")}
        </span>
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content align="start" sideOffset={6} collisionPadding={12}
          className="z-[60] w-[min(560px,calc(100vw-24px))] rounded-xl border border-border bg-sidebar p-4 shadow-2xl">
          {presets.length > 0 && (
            <div className="mb-4 flex flex-wrap gap-2">
              {presets.map((p) => (
                <button key={p.label} type="button" onClick={() => { commit(p.date); setView(new Date(p.date.getFullYear(), p.date.getMonth(), 1)); }}
                  className="rounded-full border border-border bg-panel px-3 py-1 text-[12px] text-text hover:border-primary hover:text-primary-text">
                  {p.label}
                </button>
              ))}
            </div>
          )}
          <div className="grid gap-4 sm:grid-cols-[1fr_180px]">
            {/* Calendario */}
            <div>
              <div className="mb-2 flex items-center justify-between">
                <span className="text-sm font-semibold">{cap(fmtMonth.format(view))}</span>
                <div className="flex gap-1">
                  <button type="button" aria-label={t("prev")} disabled={!canPrev}
                    onClick={() => setView(new Date(view.getFullYear(), view.getMonth() - 1, 1))}
                    className="grid size-8 place-items-center rounded-lg text-muted hover:bg-panel-hover hover:text-text disabled:pointer-events-none disabled:opacity-30">
                    <ChevronLeft className="size-4" />
                  </button>
                  <button type="button" aria-label={t("next")}
                    onClick={() => setView(new Date(view.getFullYear(), view.getMonth() + 1, 1))}
                    className="grid size-8 place-items-center rounded-lg text-muted hover:bg-panel-hover hover:text-text">
                    <ChevronRight className="size-4" />
                  </button>
                </div>
              </div>
              <div className="grid grid-cols-7 gap-1 text-center">
                {weekdays.map((w) => <span key={w} className="pb-1 text-[11px] font-medium uppercase text-muted">{w.replace(".", "")}</span>)}
                {days.map((d) => {
                  const outside = d.getMonth() !== view.getMonth();
                  const disabled = !!(minDay && d < minDay);
                  const isSel = !!(selected && sameDay(d, selected));
                  const isToday = sameDay(d, today);
                  return (
                    <button key={d.toISOString()} type="button" disabled={disabled} onClick={() => pickDay(d)}
                      aria-pressed={isSel} aria-label={fmtLong.format(d)}
                      className={cn("grid h-9 place-items-center rounded-lg text-[13px] tabular-nums transition-colors",
                        isSel ? "bg-primary font-semibold text-white" : "hover:bg-panel-hover",
                        !isSel && isToday && "ring-1 ring-primary/70 text-primary-text",
                        outside && !isSel && "text-muted/60",
                        disabled && "pointer-events-none text-muted/20")}>
                      {d.getDate()}
                    </button>
                  );
                })}
              </div>
            </div>
            {/* Hora */}
            <div className="flex flex-col gap-2 border-t border-border pt-3 sm:border-l sm:border-t-0 sm:pl-4 sm:pt-0">
              <span className="flex items-center gap-1.5 text-sm font-semibold"><Clock className="size-4 text-primary-text" aria-hidden />{t("time")}</span>
              <div className="grid grid-cols-2 gap-2">
                <Column label={t("hour")} items={Array.from({ length: 24 }, (_, i) => i)} value={hour}
                  disabled={(h) => isMinDay && !!min && h < min.getHours()}
                  onPick={(h) => pickTime(h, minute)} />
                <Column label={t("minute")} items={minutes} value={minute - (minute % 5)}
                  disabled={(m) => isMinDay && !!min && hour === min.getHours() && m < min.getMinutes()}
                  onPick={(m) => pickTime(hour, m)} />
              </div>
            </div>
          </div>
          <div className="mt-4 flex items-center justify-between border-t border-border pt-3">
            <span className="text-[12px] text-muted">{t("tzNote", { tz: Intl.DateTimeFormat().resolvedOptions().timeZone })}</span>
            <button type="button" onClick={() => setOpen(false)}
              className="rounded-lg bg-primary px-4 py-1.5 text-sm font-medium text-white hover:bg-primary-solid">{t("done")}</button>
          </div>
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}

function Column({ label, items, value, disabled, onPick }: {
  label: string; items: number[]; value: number; disabled: (v: number) => boolean; onPick: (v: number) => void;
}) {
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    // Centrar el valor elegido dentro de la lista (sin mover el resto de la página).
    const el = box.current?.querySelector<HTMLElement>("[data-selected=true]");
    if (box.current && el) box.current.scrollTop = el.offsetTop - box.current.clientHeight / 2 + el.clientHeight / 2;
  }, [value]);
  return (
    <div>
      <span className="mb-1 block text-center text-[11px] uppercase text-muted">{label}</span>
      <div ref={box} className="relative h-56 overflow-y-auto rounded-lg border border-border bg-panel p-1 [scrollbar-width:thin]">
        {items.map((v) => {
          const off = disabled(v);
          return (
            <button key={v} type="button" disabled={off} onClick={() => onPick(v)} data-selected={v === value}
              className={cn("block w-full rounded-md py-1.5 text-center text-sm tabular-nums",
                v === value ? "bg-primary font-semibold text-white" : "hover:bg-panel-hover",
                off && "pointer-events-none text-muted/25")}>
              {pad(v)}
            </button>
          );
        })}
      </div>
    </div>
  );
}

const pad = (n: number) => String(n).padStart(2, "0");
/** Solo la primera letra en mayúscula («martes, 17 de nov.», no «Martes, 17 De Nov.»). */
const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);
const startOfDay = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate());
const sameDay = (a: Date, b: Date) => a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
/** Siguiente múltiplo de 5 minutos. */
function roundUp(d: Date): Date {
  const r = new Date(d);
  r.setSeconds(0, 0);
  const extra = (5 - (r.getMinutes() % 5)) % 5;
  r.setMinutes(r.getMinutes() + extra);
  return r;
}
function parse(v: string): Date | null {
  const m = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})$/.exec(v);
  return m ? new Date(+m[1], +m[2] - 1, +m[3], +m[4], +m[5]) : null;
}
