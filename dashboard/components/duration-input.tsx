"use client";

import { useTranslations } from "next-intl";

import { inputClass } from "@/components/ui";
import { cn } from "@/lib/utils";

const UNITS = [
  { key: "minutes", seconds: 60 },
  { key: "hours", seconds: 3600 },
  { key: "days", seconds: 86400 },
] as const;

function split(seconds: number | null): { n: number; unit: number } {
  if (!seconds) return { n: 10, unit: 60 };
  for (const u of [...UNITS].reverse()) if (seconds % u.seconds === 0) return { n: seconds / u.seconds, unit: u.seconds };
  return { n: Math.round(seconds / 60), unit: 60 };
}

/** Duración como número + unidad; devuelve segundos. */
export function DurationInput({ id, value, onChange, max = 2419200, disabled }: {
  id: string; value: number | null; onChange: (s: number) => void; max?: number; disabled?: boolean;
}) {
  const t = useTranslations("duration");
  const { n, unit } = split(value);
  const invalid = Boolean(value && (value < 60 || value > max));
  return (
    <div className="flex gap-2">
      <input
        id={id}
        type="number"
        min={1}
        className={cn(inputClass, "w-24")}
        value={n}
        disabled={disabled}
        aria-invalid={invalid}
        onChange={(e) => onChange(Math.max(1, Number(e.target.value) || 1) * unit)}
      />
      <select className={cn(inputClass, "w-32")} value={unit} disabled={disabled} onChange={(e) => onChange(n * Number(e.target.value))} aria-label={t("unit")}>
        {UNITS.map((u) => (
          <option key={u.key} value={u.seconds}>
            {t(u.key)}
          </option>
        ))}
      </select>
    </div>
  );
}

export function useFormatDuration() {
  const t = useTranslations("duration");
  return (s: number | null) => {
    if (!s) return t("permanent");
    if (s % 86400 === 0) return t("nDays", { n: s / 86400 });
    if (s % 3600 === 0) return t("nHours", { n: s / 3600 });
    return t("nMinutes", { n: Math.round(s / 60) });
  };
}
