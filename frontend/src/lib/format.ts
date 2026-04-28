/** Helpers di formattazione date/numeri condivisi tra le pagine. */

const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;

/** Formatta una data ISO `YYYY-MM-DD` in formato italiano `DD/MM/YYYY`. */
export function formatDateIt(iso: string | null | undefined): string {
  if (iso === null || iso === undefined || iso.length === 0) return "—";
  if (!DATE_RE.test(iso)) {
    // timestamp (es. created_at): teniamo solo la parte data
    return formatDateIt(iso.slice(0, 10));
  }
  const [y, m, d] = iso.split("-");
  return `${d}/${m}/${y}`;
}

/** Formatta un periodo `valido_da → valido_a` in stringa compatta. */
export function formatPeriodo(da: string, a: string): string {
  return `${formatDateIt(da)} → ${formatDateIt(a)}`;
}

/** Formatta un intero in stile italiano (separatore migliaia `.`). */
export function formatNumber(n: number | null | undefined): string {
  if (n === null || n === undefined) return "—";
  return n.toLocaleString("it-IT");
}
