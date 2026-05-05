/**
 * Acronimi compatti delle stazioni per il Gantt giro materiale.
 *
 * Pattern (decisione utente 2026-05-05, entry TN-UPDATE 141):
 *   - Capoluogo + qualifica → sigla provincia camelcase + iniziali maiuscole
 *     parole successive. Es. "MILANO PORTA GARIBALDI" → "MiPG".
 *   - Stazione monoparola = sigla provincia camelcase. Es. "LECCO" → "Lc".
 *   - Eccezioni risolte una a una (collisioni Como/Colico/Codogno, ecc.).
 *
 * Quando il chiamante vuole il nome PIENO (prima/ultima stazione del
 * giro), bypassa questa mappa e mostra il nome originale.
 */

const STAZIONI_ACRONIMI: Record<string, string> = {
  // Milano
  "MILANO CENTRALE": "MiC",
  "MILANO PORTA GARIBALDI": "MiPG",
  "MILANO CADORNA": "MiCa",
  "MILANO ROGOREDO": "MiRo",
  "MILANO LAMBRATE": "MiLa",
  "MILANO BOVISA": "MiBo",
  "MILANO BOVISA POLITECNICO": "MiBP",
  "MILANO PORTA ROMANA": "MiPR",
  "MILANO PORTA VITTORIA": "MiPV",
  "MILANO GRECO PIRELLI": "MiGP",
  "MILANO REPUBBLICA": "MiRe",
  "MILANO PORTA VENEZIA": "MiPVe",
  "MILANO DATEO": "MiDa",
  "MILANO FORLANINI": "MiFo",
  "MILANO PORTELLO": "MiPo",
  "MILANO ROMOLO": "MiRm",
  "MILANO CERTOSA": "MiCer",
  "MILANO SAN CRISTOFORO": "MiSC",
  "MILANO TIBALDI BOCCONI": "MiTi",
  "MILANO VILLAPIZZONE": "MiVP",
  "MILANO SAN ROCCO": "MiSR",
  "MILANO GRECO": "MiGr",
  // Direttrice Tirano (S.Sondrio/V.Tellina)
  LECCO: "Lc",
  "LECCO MAGGIANICO": "LcMa",
  "LECCO PESCARENICO": "LcPe",
  COLICO: "Cli",
  MORBEGNO: "Mor",
  SONDRIO: "So",
  TIRANO: "Ti",
  CHIAVENNA: "Cv",
  // Direttrice Como/Chiasso
  COMO: "Co",
  "COMO LAGO": "CoL",
  "COMO SAN GIOVANNI": "CoSG",
  CHIASSO: "Chi",
  "CAMNAGO LENTATE": "Cam",
  CARNATE: "Ca",
  "CARNATE USMATE": "CaU",
  SEVESO: "Sv",
  "MEDA": "Md",
  // Direttrice Bergamo
  BERGAMO: "Bg",
  "PONTE SAN PIETRO": "PSP",
  TREVIGLIO: "Tv",
  "TREVIGLIO CENTRO": "TvC",
  ALBANO: "Alb",
  // Direttrice Brescia
  BRESCIA: "Bs",
  ROVATO: "Ro",
  "PALAZZOLO SULL'OGLIO": "PsO",
  CHIARI: "Cha",
  ISEO: "Is",
  // Mantova/Cremona/Piacenza
  MANTOVA: "Mn",
  CREMONA: "Cr",
  PIACENZA: "Pc",
  PARMA: "Pr",
  LODI: "Lo",
  CODOGNO: "Cdg",
  // Domodossola/Malpensa
  DOMODOSSOLA: "Do",
  ARONA: "Ar",
  GALLARATE: "Ga",
  "BUSTO ARSIZIO": "Ba",
  "BUSTO ARSIZIO NORD": "BaN",
  "MALPENSA AEROPORTO T1": "MxpT1",
  "MALPENSA AEROPORTO T2": "MxpT2",
  "MALPENSA AEROPORTO": "Mxp",
  RHO: "Rh",
  "RHO FIERA": "RhF",
  "RHO FIERA EXPO": "RhF",
  // Varese/Laveno/Svizzera
  VARESE: "Va",
  "VARESE NORD": "VaN",
  LAVENO: "Lv",
  "LAVENO MOMBELLO": "LvM",
  "PORTO CERESIO": "PCe",
  MENDRISIO: "Me",
  LUGANO: "Lu",
  BELLINZONA: "Bl",
  // Brianza/Monza
  MONZA: "Mz",
  DESIO: "De",
  SEREGNO: "Se",
  LISSONE: "Li",
  // Pavia/Voghera
  PAVIA: "Pv",
  VOGHERA: "Vg",
  // Cremona-Brescia
  TREVIGLIO_OVEST: "TvO",
  // Sprint 7.10 MR α.8 frontend (entry 162): acronimi Piemonte
  // richiesti dall'utente. La sigla provincia (VC, AL, NO, AT, BI)
  // è preferita al pattern algoritmico capoluogo+iniziali perché è
  // immediatamente riconoscibile per il pianificatore.
  VERCELLI: "VC",
  ALESSANDRIA: "AL",
  NOVARA: "NO",
  ASTI: "AT",
  BIELLA: "BI",
  TORINO: "TO",
  "TORINO PORTA NUOVA": "TOpn",
  "TORINO PORTA SUSA": "TOps",
  // Sedi materiali (a volte come stazione)
  "MILANO FIORENZA": "FIO",
  "MILANO NOVATE": "NOV",
};

/**
 * Acronimo fallback algoritmico per stazioni non mappate.
 * - 1 parola: prima lettera maiuscola + seconda minuscola (es. "ARESE" → "Ar")
 * - 2+ parole: prima parola camelcase 2-char, parole successive prima
 *   lettera maiuscola (es. "ARESE LAINATE" → "ArL")
 */
function fallbackAcronimo(nomeUpper: string): string {
  const parts = nomeUpper.split(/\s+/).filter((p) => p.length > 0);
  if (parts.length === 0) return "?";
  const first = parts[0];
  const firstAbbr = (first[0] ?? "") + (first[1]?.toLowerCase() ?? "");
  if (parts.length === 1) return firstAbbr;
  const restAbbr = parts
    .slice(1)
    .map((p) => p[0] ?? "")
    .join("");
  return firstAbbr + restAbbr;
}

/**
 * Restituisce l'acronimo compatto della stazione.
 * Lookup in mappa hardcoded → fallback algoritmico.
 * Per il nome pieno (prima/ultima stazione del giro), il chiamante deve
 * NON usare questa funzione e mostrare direttamente il nome originale.
 */
export function stazioneAcronimo(nome: string | null | undefined): string {
  if (nome === null || nome === undefined) return "—";
  const trimmed = nome.trim();
  if (trimmed.length === 0) return "—";
  const upper = trimmed.toUpperCase();
  const mapped = STAZIONI_ACRONIMI[upper];
  if (mapped !== undefined) return mapped;
  return fallbackAcronimo(upper);
}
