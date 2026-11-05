// The API uses company-local wall-clock times without a timezone ("2026-11-10T09:00:00").
// These helpers keep everything in that format and never convert through UTC.

const pad = (n: number) => String(n).padStart(2, "0");

export function isoDate(d: Date): string {
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

export function localDateTime(date: string, time: string): string {
  return `${date}T${time.slice(0, 5)}`;
}

export function parseLocal(value: string): Date {
  const [d, t = "00:00"] = value.split("T");
  const [y, m, day] = d.split("-").map(Number);
  const [hh, mm] = t.split(":").map(Number);
  return new Date(y, m - 1, day, hh, mm);
}

export function startOfWeek(d: Date): Date {
  const copy = new Date(d.getFullYear(), d.getMonth(), d.getDate());
  const offset = (copy.getDay() + 6) % 7; // Monday = 0
  copy.setDate(copy.getDate() - offset);
  return copy;
}

export function addDays(d: Date, days: number): Date {
  const copy = new Date(d);
  copy.setDate(copy.getDate() + days);
  return copy;
}

export function hhmm(value: string): string {
  const t = value.includes("T") ? value.split("T")[1] : value;
  return t.slice(0, 5);
}

/** "09:00 to 09:30", "23:00 to 07:00 (+1)", or "10:00 to Wed, 11 Nov, 11:00" for longer spans. */
export function timeRange(start: string, end: string): string {
  const s = parseLocal(start);
  const e = parseLocal(end);
  const days = Math.round(
    (new Date(e.getFullYear(), e.getMonth(), e.getDate()).getTime() -
      new Date(s.getFullYear(), s.getMonth(), s.getDate()).getTime()) / 86_400_000,
  );
  if (days === 0) return `${hhmm(start)} to ${hhmm(end)}`;
  if (days === 1) return `${hhmm(start)} to ${hhmm(end)} (+1)`;
  const endDay = e.toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short" });
  return `${hhmm(start)} to ${endDay}, ${hhmm(end)}`;
}

export function dayLabel(d: Date): { weekday: string; day: string } {
  return {
    weekday: d.toLocaleDateString(undefined, { weekday: "short" }),
    day: d.toLocaleDateString(undefined, { day: "numeric", month: "short" }),
  };
}

export function rangeLabel(start: Date, end: Date): string {
  const opts: Intl.DateTimeFormatOptions = { day: "numeric", month: "short" };
  return `${start.toLocaleDateString(undefined, opts)} to ${end.toLocaleDateString(undefined, { ...opts, year: "numeric" })}`;
}

export function hoursBetween(start: string, end: string): number {
  return (parseLocal(end).getTime() - parseLocal(start).getTime()) / 3_600_000;
}
