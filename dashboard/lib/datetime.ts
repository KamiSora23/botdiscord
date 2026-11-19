// Fechas para los campos <input type="datetime-local"> (formato "YYYY-MM-DDTHH:mm", sin zona horaria).

/** Zona horaria del navegador, p. ej. "America/Lima". */
export function browserTimeZone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
  } catch {
    return "UTC";
  }
}

const pad = (n: number) => String(n).padStart(2, "0");

/** Fecha → "YYYY-MM-DDTHH:mm" en la hora local del navegador. */
export function toLocalInput(d: Date): string {
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

/** Ahora mismo (redondeado al minuto siguiente): valor mínimo de los campos de fecha. */
export function minLocalInput(): string {
  const d = new Date(Date.now() + 60_000);
  d.setSeconds(0, 0);
  return toLocalInput(d);
}

/** Minutos de diferencia entre UTC y ``timeZone`` en el instante ``at``. */
function offsetMinutes(at: Date, timeZone: string): number {
  const parts = Object.fromEntries(
    new Intl.DateTimeFormat("en-US", { timeZone, hourCycle: "h23", year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" })
      .formatToParts(at).map((p) => [p.type, p.value]),
  );
  const asUtc = Date.UTC(+parts.year, +parts.month - 1, +parts.day, +parts.hour, +parts.minute);
  return Math.round((asUtc - at.getTime()) / 60_000);
}

/** "YYYY-MM-DDTHH:mm" interpretado en ``timeZone`` → instante real. */
export function zonedToDate(local: string, timeZone: string): Date | null {
  const m = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})$/.exec(local);
  if (!m) return null;
  const guess = Date.UTC(+m[1], +m[2] - 1, +m[3], +m[4], +m[5]);
  try {
    // Dos pasadas para acertar también en los cambios de horario de verano.
    let ts = guess - offsetMinutes(new Date(guess), timeZone) * 60_000;
    ts = guess - offsetMinutes(new Date(ts), timeZone) * 60_000;
    return new Date(ts);
  } catch {
    return null;
  }
}

/** Convierte una hora local de ``fromTz`` a la hora local del navegador (mismo instante). */
export function toBrowserLocal(local: string, fromTz: string): string {
  if (fromTz === browserTimeZone()) return local;
  const d = zonedToDate(local, fromTz);
  return d ? toLocalInput(d) : local;
}

/** ¿La hora local del navegador ya pasó? */
export function isPastLocal(local: string): boolean {
  const d = zonedToDate(local, browserTimeZone());
  return !d || d.getTime() <= Date.now();
}
