/**
 * Schema dichiarativo dei filtri regola — sorgente unica di verità per
 * l'editor regola del frontend. Allineato a `colazione.schemas.programmi`
 * (CAMPI_AMMESSI + _CAMPO_OP_COMPATIBILI).
 *
 * Ordine: campi principali in alto (linea, categoria, stazioni),
 * campi avanzati in basso (codice servizio, numero_treno, ecc.).
 *
 * Nota terminologia (Sprint 7.6 MR 1): il campo backend si chiama
 * ancora `direttrice` (dato PdE Trenord) ma in UI lo presentiamo come
 * "Linea" — il pianificatore ragiona in termini di linee commerciali
 * (es. "TIRANO-SONDRIO-LECCO-MILANO"), non di direttrici tecniche.
 * Il `codice_linea` (S1, RE3, R23…) è il codice di servizio
 * commerciale e resta avanzato.
 */

export const CAMPI_REGOLA = [
  "direttrice",
  "categoria",
  "codice_origine",
  "codice_destinazione",
  "giorno_tipo",
  "fascia_oraria",
  "is_treno_garantito_feriale",
  "is_treno_garantito_festivo",
  "codice_linea",
  "numero_treno",
  "rete",
] as const;

export type CampoRegola = (typeof CAMPI_REGOLA)[number];

export const OP_PER_CAMPO: Record<CampoRegola, ReadonlyArray<string>> = {
  direttrice: ["eq", "in"],
  categoria: ["eq", "in"],
  codice_origine: ["eq", "in"],
  codice_destinazione: ["eq", "in"],
  giorno_tipo: ["eq", "in"],
  fascia_oraria: ["between", "gte", "lte"],
  is_treno_garantito_feriale: ["eq"],
  is_treno_garantito_festivo: ["eq"],
  codice_linea: ["eq", "in"],
  numero_treno: ["eq", "in"],
  rete: ["eq", "in"],
};

export const LABEL_CAMPO: Record<CampoRegola, string> = {
  direttrice: "Linea",
  categoria: "Categoria",
  codice_origine: "Stazione di origine",
  codice_destinazione: "Stazione di destinazione",
  giorno_tipo: "Giorno tipo",
  fascia_oraria: "Fascia oraria",
  is_treno_garantito_feriale: "Treno garantito (feriale)",
  is_treno_garantito_festivo: "Treno garantito (festivo)",
  codice_linea: "Codice servizio (avanzato)",
  numero_treno: "Numero treno (avanzato)",
  rete: "Rete (avanzato)",
};

/**
 * Hint sotto-label di ogni campo (mostrato in piccolo sotto la select
 * "Campo" come spiegazione contestuale per il pianificatore).
 */
export const HINT_CAMPO: Partial<Record<CampoRegola, string>> = {
  direttrice: "Es. TIRANO-SONDRIO-LECCO-MILANO. Puoi sceglierne più di una.",
  categoria: "Es. REG, RE, R, MET, S, INT.",
  codice_origine: "Codice stazione di partenza della corsa.",
  codice_destinazione: "Codice stazione di arrivo della corsa.",
  giorno_tipo: "Tipo di giorno calendario (feriale/sabato/festivo).",
  fascia_oraria: "Filtra le corse per orario di partenza.",
  is_treno_garantito_feriale: "Servizi minimi garantiti nei feriali.",
  is_treno_garantito_festivo: "Servizi minimi garantiti nei festivi.",
  codice_linea: "Codice di servizio commerciale: S1, RE3, R23…",
  numero_treno: "Numero treno PdE (es. 2413).",
  rete: "Rete RFI/concessa (avanzato).",
};

export const LABEL_OP: Record<string, string> = {
  eq: "uguale a",
  in: "tra le opzioni",
  between: "compreso tra",
  gte: "≥",
  lte: "≤",
};

export const GIORNI_TIPO = ["feriale", "sabato", "festivo"] as const;
export type GiornoTipo = (typeof GIORNI_TIPO)[number];

/** Valori comuni per `categoria` (Trenord). Lista di hint per autocomplete:
 * non blocca input liberi (la categoria può estendersi via dato). */
export const CATEGORIE_COMUNI = ["REG", "RE", "R", "MET", "S", "INT"] as const;

/**
 * Riga di filtro in editing. `valore` è sempre stringa per uniformità
 * UI; al submit viene parsata in base a (campo, op).
 */
export interface FiltroRow {
  id: string;
  campo: CampoRegola;
  op: string;
  valore: string;
}

/** Riga di composizione in editing. */
export interface ComposizioneRow {
  id: string;
  materiale_tipo_codice: string;
  n_pezzi: number;
}

/** Genera un id locale per le righe (non persiste). */
export function makeRowId(): string {
  return `r-${Math.random().toString(36).slice(2, 10)}`;
}

/**
 * Converte una FiltroRow in payload backend (`{campo, op, valore}` con
 * `valore` tipizzato in base all'op). Lancia Error se il valore è
 * malformato.
 */
export function rowToPayload(row: FiltroRow): { campo: string; op: string; valore: unknown } {
  const { campo, op, valore } = row;

  if (op === "in") {
    const items = valore
      .split(",")
      .map((s) => s.trim())
      .filter((s) => s.length > 0);
    if (items.length === 0) {
      throw new Error(`Filtro "${LABEL_CAMPO[campo]}": specifica almeno un valore`);
    }
    return { campo, op, valore: items };
  }

  if (op === "between") {
    const items = valore
      .split(",")
      .map((s) => s.trim())
      .filter((s) => s.length > 0);
    if (items.length !== 2) {
      throw new Error(
        `Filtro "${LABEL_CAMPO[campo]}": "compreso tra" richiede esattamente 2 valori (es. 04:00, 15:59)`,
      );
    }
    return { campo, op, valore: items };
  }

  // op = eq | gte | lte → valore scalare
  if (campo === "is_treno_garantito_feriale" || campo === "is_treno_garantito_festivo") {
    return { campo, op, valore: valore === "true" };
  }
  if (valore.trim().length === 0) {
    throw new Error(`Filtro "${LABEL_CAMPO[campo]}": specifica un valore`);
  }
  return { campo, op, valore: valore.trim() };
}

/** Inverso di rowToPayload: payload backend → FiltroRow per editing. */
export function payloadToRow(payload: { campo: string; op: string; valore: unknown }): FiltroRow {
  const { campo, op, valore } = payload;
  let valoreStr: string;
  if (Array.isArray(valore)) {
    valoreStr = valore.map((v) => String(v)).join(", ");
  } else if (typeof valore === "boolean") {
    valoreStr = valore ? "true" : "false";
  } else {
    valoreStr = String(valore);
  }
  return { id: makeRowId(), campo: campo as CampoRegola, op, valore: valoreStr };
}
