import { useMemo, useState } from "react";
import { Link, useLocation, useParams } from "react-router-dom";
import {
  AlertCircle,
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  Bed,
  Moon,
} from "lucide-react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/Dialog";
import { Spinner } from "@/components/ui/Spinner";
import { useTurnoPdcDettaglio } from "@/hooks/useTurniPdc";
import { ApiError } from "@/lib/api/client";
import type {
  TurnoPdcBlocco,
  TurnoPdcDettaglio,
  TurnoPdcGiornata,
} from "@/lib/api/turniPdc";
import { cn } from "@/lib/utils";

/**
 * Sprint 7.10 MR 7.10.7 — Visualizzatore Gantt turno PdC, ricalcato
 * sulla grammatica del Gantt giro materiale (1° ruolo) con palette
 * dedicata al dominio PdC.
 *
 * Pattern condiviso col Gantt giro:
 * - Card con toolbar in cima (info asse + giornate count)
 * - Scroll wrapper con sticky AxisHeader (24 tick orari + corner sx/dx)
 * - Per ogni giornata: header row con numero/badge + single-line
 *   `ticks-bg` con blocchi posizionati assolutamente
 * - Sticky-left "Giornata N" + sticky-right "Prest/Cond"
 * - Legenda in fondo, sempre visibile
 * - 1h = 40px, TIMELINE_WIDTH_PX = 960 (densità coerente)
 *
 * Distinzioni deliberate (brief §5.5):
 * - **Asse default 00→23** (giornata umana del PdC), non 04→04 che è il
 *   ciclo commerciale del materiale rotabile. Toggle 00↔04 disponibile
 *   in toolbar per allineare visivamente al Gantt giro quando serve.
 * - **Palette pastello dedicata per tipo evento PdC**: CONDOTTA blu
 *   primary, VETTURA sky, REFEZ emerald, ACC amber, CV orange, PK/SCOMP
 *   secondary, PRESA/FINE slate, DORMITA viola. Niente classi `.seg-*`
 *   del Gantt giro (rosso commerciale), niente `.night-band`.
 *
 * Aggiunte rispetto al MR 7.10.6:
 * - Mini-mappa fishbone giornate (click → scroll #giornata-N)
 * - Toggle asse 00↔04 funzionale
 * - Legenda chip orizzontali sempre visibile
 * - Path-aware back-link preservato
 * - Tutti i badge violazione live + testid preservati
 */
export function TurnoPdcDettaglioRoute() {
  const { turnoId: turnoIdParam } = useParams<{ turnoId: string }>();
  const turnoId = turnoIdParam !== undefined ? Number(turnoIdParam) : undefined;
  const location = useLocation();
  const isPdcRoute = location.pathname.startsWith("/pianificatore-pdc");
  const query = useTurnoPdcDettaglio(turnoId);

  const [oraOffset, setOraOffset] = useState<0 | 4>(0);
  // MR 7.11.6: blocco selezionato per il Dialog dettagli. null = chiuso.
  const [blockDetail, setBlockDetail] = useState<{
    blocco: TurnoPdcBlocco;
    giornataNumero: number;
  } | null>(null);

  if (turnoId === undefined || Number.isNaN(turnoId)) {
    return <ErrorBlock message="ID turno PdC non valido nell'URL." />;
  }

  if (query.isLoading) {
    return (
      <Card className="grid place-items-center p-16">
        <Spinner label="Caricamento turno PdC…" />
      </Card>
    );
  }

  if (query.isError) {
    const msg =
      query.error instanceof ApiError ? query.error.message : (query.error as Error).message;
    return <ErrorBlock message={msg} onRetry={() => void query.refetch()} />;
  }

  if (query.data === undefined) {
    return <ErrorBlock message="Turno PdC non trovato." />;
  }

  const turno = query.data;
  const meta = turno.generation_metadata_json;
  const giroId = meta.giro_materiale_id ?? null;
  const validazioniCiclo = turno.validazioni_ciclo;
  const frGiornate = meta.fr_giornate ?? [];

  return (
    <div className="flex flex-col gap-5">
      <Link
        to={
          isPdcRoute
            ? "/pianificatore-pdc/turni"
            : giroId !== null
              ? `/pianificatore-giro/giri/${giroId}/turni-pdc`
              : "/pianificatore-giro/programmi"
        }
        className="inline-flex w-fit items-center gap-1 text-sm text-muted-foreground hover:text-primary"
      >
        <ArrowLeft className="h-3.5 w-3.5" aria-hidden /> Lista turni PdC
      </Link>

      <Header turno={turno} />
      <Stats turno={turno} />

      {(validazioniCiclo.length > 0 || frGiornate.length > 0) && (
        <Avvisi validazioniCiclo={validazioniCiclo} frGiornate={frGiornate} />
      )}

      <GanttPdc
        turno={turno}
        oraOffset={oraOffset}
        onToggleOffset={() => setOraOffset((v) => (v === 0 ? 4 : 0))}
        onSelectBlocco={(blocco, giornataNumero) =>
          setBlockDetail({ blocco, giornataNumero })
        }
        selectedBloccoId={blockDetail?.blocco.id ?? null}
      />

      {/* Sequenza blocchi per giornata sotto al Gantt: dato di dettaglio
          che il pianificatore consulta dopo aver letto il Gantt sopra. */}
      <section className="flex flex-col gap-4">
        <h2 className="text-lg font-semibold tracking-tight">
          Sequenze blocchi per giornata
        </h2>
        <div className="flex flex-col gap-3">
          {turno.giornate.map((g) => (
            <BlocchiPanel key={g.id} giornata={g} />
          ))}
        </div>
      </section>

      {/* MR 7.11.6: Dialog dettagli blocco. Aperto cliccando un blocco
          nella timeline o una riga della sequenza blocchi. */}
      <BloccoDetailDialog
        detail={blockDetail}
        onClose={() => setBlockDetail(null)}
      />
    </div>
  );
}

// ────────────────────────────────────────────────────────────────────────
// Header turno + Stats aggregate
// ────────────────────────────────────────────────────────────────────────

function Header({ turno }: { turno: TurnoPdcDettaglio }) {
  const meta = turno.generation_metadata_json;
  return (
    <header className="flex flex-col gap-1">
      <div className="flex flex-wrap items-center gap-2">
        <h1 className="text-2xl font-semibold tracking-tight">{turno.codice}</h1>
        {turno.deposito_pdc_codice !== null ? (
          <Badge variant="outline" title={turno.deposito_pdc_display ?? ""}>
            Deposito {turno.deposito_pdc_codice}
          </Badge>
        ) : (
          <Badge variant="outline">{turno.impianto}</Badge>
        )}
        <Badge variant="secondary">{turno.profilo}</Badge>
        {typeof meta.giro_numero_turno === "string" && (
          <span className="text-xs text-muted-foreground">
            ← derivato da {meta.giro_numero_turno}
          </span>
        )}
      </div>
      <p className="text-sm text-muted-foreground">
        #{turno.id} · ciclo {turno.ciclo_giorni} giorn{turno.ciclo_giorni === 1 ? "o" : "i"} ·
        valido da {turno.valido_da} · stato {turno.stato}
      </p>
    </header>
  );
}

function Stats({ turno }: { turno: TurnoPdcDettaglio }) {
  const totPrestazione = turno.giornate.reduce((s, g) => s + g.prestazione_min, 0);
  const totCondotta = turno.giornate.reduce((s, g) => s + g.condotta_min, 0);
  const totRefezione = turno.giornate.reduce((s, g) => s + g.refezione_min, 0);
  const hasViolazioni = turno.n_violazioni_hard > 0 || turno.n_violazioni_soft > 0;
  const hasFr = turno.n_dormite_fr > 0 || turno.fr_cap_violazioni.length > 0;
  return (
    <div className="flex flex-col gap-3">
      <div className="grid grid-cols-2 gap-3 rounded-md border border-border bg-white p-4 md:grid-cols-4">
        <Stat label="Prestazione totale" value={formatHM(totPrestazione)} />
        <Stat label="Condotta totale" value={formatHM(totCondotta)} />
        <Stat label="Refezione totale" value={formatHM(totRefezione)} />
        <Stat label="Giornate" value={String(turno.giornate.length)} />
      </div>
      {hasFr && (
        <div
          className={cn(
            "grid grid-cols-1 gap-3 rounded-md border p-4 md:grid-cols-3",
            turno.fr_cap_violazioni.length > 0
              ? "border-red-300 bg-red-50"
              : "border-amber-300 bg-amber-50",
          )}
        >
          <Stat label="Dormite FR" value={String(turno.n_dormite_fr)} />
          <Stat
            label="Cap FR violati"
            value={String(turno.fr_cap_violazioni.length)}
          />
          <Stat
            label="Sede PdC"
            value={
              turno.deposito_pdc_codice !== null
                ? turno.deposito_pdc_codice
                : "(legacy)"
            }
          />
        </div>
      )}
      {hasViolazioni && (
        <div className="grid grid-cols-1 gap-3 rounded-md border border-amber-300 bg-amber-50 p-4 md:grid-cols-3">
          <Stat
            label="Giornate violanti"
            value={`${turno.n_giornate_violanti} / ${turno.giornate.length}`}
          />
          <Stat label="Violazioni hard" value={String(turno.n_violazioni_hard)} />
          <Stat label="Violazioni soft" value={String(turno.n_violazioni_soft)} />
        </div>
      )}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
        {label}
      </span>
      <span className="text-base font-semibold tabular-nums text-foreground">{value}</span>
    </div>
  );
}

function Avvisi({
  validazioniCiclo,
  frGiornate,
}: {
  validazioniCiclo: string[];
  frGiornate: { giornata: number; stazione: string; ore: number }[];
}) {
  return (
    <div className="flex flex-col gap-2">
      {validazioniCiclo.length > 0 && (
        <details
          className="rounded-md border border-amber-300 bg-amber-50 text-sm text-amber-900"
          data-testid="vincoli-ciclo-panel"
        >
          <summary className="flex cursor-pointer items-center gap-2 px-3 py-2 font-medium">
            <AlertTriangle className="h-4 w-4" aria-hidden /> Vincoli ciclo:{" "}
            {validazioniCiclo.length} segnalazion
            {validazioniCiclo.length === 1 ? "e" : "i"}
          </summary>
          <ul className="space-y-1 px-4 pb-3 font-mono text-xs">
            {validazioniCiclo.map((v, i) => (
              <li key={i}>· {v}</li>
            ))}
          </ul>
          <p className="border-t border-amber-200 px-3 py-2 text-xs italic">
            Tag prodotti dal builder durante il calcolo (NORMATIVA-PDC §11
            riposo intra-ciclo / §11.4 settimanale / §10.6 FR).
          </p>
        </details>
      )}
      {frGiornate.length > 0 && (
        <div className="flex flex-col gap-1 rounded-md border border-violet-200 bg-violet-50 px-3 py-2 text-sm text-violet-900">
          <div className="flex items-center gap-2 font-medium">
            <Bed className="h-4 w-4" aria-hidden /> {frGiornate.length} dormit
            {frGiornate.length === 1 ? "a" : "e"} fuori residenza (FR)
          </div>
          <ul className="space-y-0.5 pl-6 text-xs">
            {frGiornate.map((fr, i) => (
              <li key={i}>
                Giornata {fr.giornata}: pernotto a{" "}
                <span className="font-mono">{fr.stazione}</span> · {fr.ore.toFixed(1)}h
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

// ────────────────────────────────────────────────────────────────────────
// Gantt PdC — single-line per giornata, asse 00→23 (toggle 04→04)
// Pattern condiviso col Gantt giro materiale, palette PdC dedicata.
// ────────────────────────────────────────────────────────────────────────

const TIMELINE_WIDTH_PX = 960; // 1h = 40px (coerente col Gantt giro)
const GIORNATA_LABEL_COL_PX = 110;
const STATS_COL_PX = 140;
// Sprint 7.11 MR 7.11.4: row height aumentata da 56 a 80 per ospitare il
// layout multi-line dei blocchi CONDOTTA/VETTURA (stazioni sopra + treno
// centro + orari sotto), coerente col CommercialeBlocco del Gantt giro.
const TIMELINE_ROW_HEIGHT_PX = 80;
const HEADER_AXIS_HEIGHT_PX = 36;
const AXIS_TOTAL_MIN = 24 * 60;

interface GanttPdcProps {
  turno: TurnoPdcDettaglio;
  oraOffset: 0 | 4;
  onToggleOffset: () => void;
  onSelectBlocco: (blocco: TurnoPdcBlocco, giornataNumero: number) => void;
  selectedBloccoId: number | null;
}

function GanttPdc({
  turno,
  oraOffset,
  onToggleOffset,
  onSelectBlocco,
  selectedBloccoId,
}: GanttPdcProps) {
  const innerWidth = GIORNATA_LABEL_COL_PX + TIMELINE_WIDTH_PX + STATS_COL_PX;

  return (
    <Card className="overflow-hidden">
      {/* Toolbar: titolo + fishbone + asse info + toggle */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border bg-muted/40 px-4 py-2.5 text-xs">
        <div className="flex items-center gap-3 text-muted-foreground">
          <span className="font-medium uppercase tracking-wide text-foreground">
            Gantt turno PdC
          </span>
          <span className="text-border">·</span>
          <span>
            {turno.giornate.length} giornat
            {turno.giornate.length === 1 ? "a" : "e"}
          </span>
          <span className="text-border">·</span>
          <Fishbone giornate={turno.giornate} />
        </div>
        <div className="flex items-center gap-3 text-muted-foreground/80">
          <span>
            Asse {oraOffset === 0 ? "00:00 → 23:59 (giornata umana)" : "04:00 → 04:00 (ciclo)"} ·
            1h = 40px
          </span>
          <div className="inline-flex rounded-md border border-border bg-white p-0.5">
            <button
              type="button"
              onClick={() => oraOffset !== 0 && onToggleOffset()}
              className={cn(
                "rounded px-2 py-0.5 font-mono text-[10px] font-semibold transition-colors",
                oraOffset === 0
                  ? "bg-primary text-primary-foreground"
                  : "text-muted-foreground hover:text-foreground",
              )}
              aria-pressed={oraOffset === 0}
            >
              00→23
            </button>
            <button
              type="button"
              onClick={() => oraOffset !== 4 && onToggleOffset()}
              className={cn(
                "rounded px-2 py-0.5 font-mono text-[10px] font-semibold transition-colors",
                oraOffset === 4
                  ? "bg-primary text-primary-foreground"
                  : "text-muted-foreground hover:text-foreground",
              )}
              aria-pressed={oraOffset === 4}
            >
              04→04
            </button>
          </div>
        </div>
      </div>

      {/* Scroll wrapper */}
      <div className="relative overflow-auto" style={{ maxHeight: "640px" }}>
        <div className="relative" style={{ width: `${innerWidth}px` }}>
          <AxisHeader oraOffset={oraOffset} />

          {turno.giornate.map((g) => (
            <GiornataRow
              key={g.id}
              giornata={g}
              oraOffset={oraOffset}
              onSelectBlocco={(b) => onSelectBlocco(b, g.numero_giornata)}
              selectedBloccoId={selectedBloccoId}
            />
          ))}
        </div>
      </div>

      {/* Legenda sempre visibile */}
      <Legenda />
    </Card>
  );
}

function AxisHeader({ oraOffset }: { oraOffset: 0 | 4 }) {
  const hourTicks = useMemo(
    () => Array.from({ length: 24 }, (_, i) => (i + oraOffset) % 24),
    [oraOffset],
  );
  return (
    <div
      className="sticky top-0 z-30 flex border-b border-border bg-white"
      style={{ height: HEADER_AXIS_HEIGHT_PX }}
    >
      {/* Corner sx (sopra label giornata) */}
      <div
        className="sticky left-0 z-40 flex items-end border-r border-border bg-white px-3 pb-1.5 text-[10px] uppercase tracking-wider text-muted-foreground"
        style={{ width: GIORNATA_LABEL_COL_PX }}
      >
        Giornata
      </div>
      {/* 24 tick orari */}
      <div className="relative" style={{ width: TIMELINE_WIDTH_PX }}>
        <div className="absolute inset-0 flex">
          {hourTicks.map((h, i) => (
            <div
              key={`${h}-${i}`}
              className="relative border-l border-border/40 first:border-l-0"
              style={{ width: 40 }}
            >
              <span
                className={cn(
                  "absolute left-1 top-1 font-mono text-[10px] tabular-nums",
                  i % 2 === 0 ? "text-foreground" : "text-muted-foreground/70",
                )}
              >
                {String(h).padStart(2, "0")}
              </span>
            </div>
          ))}
        </div>
      </div>
      {/* Corner dx (sopra Per/Cond) */}
      <div
        className="sticky right-0 z-40 flex border-l border-border bg-white"
        style={{ width: STATS_COL_PX }}
      >
        <div className="flex w-1/2 items-end justify-center border-r border-border pb-1.5 text-[10px] uppercase tracking-wider text-muted-foreground">
          Prest.
        </div>
        <div className="flex w-1/2 items-end justify-center pb-1.5 text-[10px] uppercase tracking-wider text-muted-foreground">
          Cond.
        </div>
      </div>
    </div>
  );
}

function GiornataRow({
  giornata,
  oraOffset,
  onSelectBlocco,
  selectedBloccoId,
}: {
  giornata: TurnoPdcGiornata;
  oraOffset: 0 | 4;
  onSelectBlocco: (b: TurnoPdcBlocco) => void;
  selectedBloccoId: number | null;
}) {
  const inizio = giornata.inizio_prestazione ?? "?";
  const fine = giornata.fine_prestazione ?? "?";
  const hasViolazioneHard =
    giornata.prestazione_violata || giornata.condotta_violata;

  return (
    <div
      id={`giornata-${giornata.numero_giornata}`}
      className="relative flex border-b border-border scroll-mt-4"
    >
      {/* Sticky-left: numero + badge violazioni + variante calendario */}
      <div
        className={cn(
          "sticky left-0 z-20 flex flex-col justify-center gap-1 border-r border-border px-3 py-2",
          hasViolazioneHard ? "bg-amber-50/60" : "bg-white",
        )}
        style={{ width: GIORNATA_LABEL_COL_PX }}
      >
        <div className="flex items-center gap-1.5">
          <span className="text-sm font-bold text-foreground">
            G{giornata.numero_giornata}
          </span>
          {giornata.is_notturno && (
            <Moon className="h-3 w-3 text-violet-600" aria-hidden />
          )}
        </div>
        <Badge variant="outline" className="w-fit text-[9px]">
          {giornata.variante_calendario}
        </Badge>
        <div className="font-mono text-[10px] tabular-nums text-muted-foreground">
          {inizio} → {fine}
        </div>
        {(giornata.prestazione_violata || giornata.condotta_violata || giornata.refezione_mancante) && (
          <div className="flex flex-wrap gap-0.5">
            {giornata.prestazione_violata && (
              <Badge
                variant="warning"
                className="gap-0.5 text-[8px]"
                data-testid={`badge-prestazione-violata-g${giornata.numero_giornata}`}
              >
                <AlertTriangle className="h-2.5 w-2.5" aria-hidden /> prest. fuori cap
              </Badge>
            )}
            {giornata.condotta_violata && (
              <Badge
                variant="warning"
                className="gap-0.5 text-[8px]"
                data-testid={`badge-condotta-violata-g${giornata.numero_giornata}`}
              >
                <AlertTriangle className="h-2.5 w-2.5" aria-hidden /> cond. fuori cap
              </Badge>
            )}
            {giornata.refezione_mancante && (
              <Badge
                variant="outline"
                className="gap-0.5 border-amber-400 text-[8px] text-amber-800"
                data-testid={`badge-refezione-mancante-g${giornata.numero_giornata}`}
              >
                <AlertTriangle className="h-2.5 w-2.5" aria-hidden /> refez. mancante
              </Badge>
            )}
          </div>
        )}
      </div>

      {/* Timeline single-line con ticks-bg */}
      <div
        className="ticks-bg relative"
        style={{ width: TIMELINE_WIDTH_PX, height: TIMELINE_ROW_HEIGHT_PX }}
      >
        {/* Linea base centrata sottile per agganciare visivamente i blocchi */}
        <div
          className="pointer-events-none absolute left-0 right-0 h-px bg-border"
          style={{ top: TIMELINE_ROW_HEIGHT_PX / 2 }}
        />

        {giornata.blocchi.map((b) => (
          <BloccoSegment
            key={b.id}
            blocco={b}
            oraOffset={oraOffset}
            onSelect={() => onSelectBlocco(b)}
            isSelected={selectedBloccoId === b.id}
          />
        ))}
      </div>

      {/* Sticky-right: prestazione + condotta in due celle */}
      <div
        className="sticky right-0 z-20 flex border-l border-border bg-white"
        style={{ width: STATS_COL_PX }}
      >
        <div
          className={cn(
            "flex w-1/2 flex-col items-center justify-center border-r border-border font-mono text-xs tabular-nums",
            giornata.prestazione_violata ? "text-amber-700" : "text-foreground",
          )}
        >
          {formatHM(giornata.prestazione_min)}
        </div>
        <div
          className={cn(
            "flex w-1/2 flex-col items-center justify-center font-mono text-xs tabular-nums",
            giornata.condotta_violata ? "text-amber-700" : "text-foreground",
          )}
        >
          {formatHM(giornata.condotta_min)}
        </div>
      </div>
    </div>
  );
}

// ────────────────────────────────────────────────────────────────────────
// Fishbone navigazione
// ────────────────────────────────────────────────────────────────────────

function Fishbone({ giornate }: { giornate: TurnoPdcGiornata[] }) {
  if (giornate.length === 0) {
    return <span className="text-muted-foreground/60">no giornate</span>;
  }
  return (
    <ol className="flex items-center gap-1">
      {giornate.map((g) => {
        const hard = g.prestazione_violata || g.condotta_violata;
        const soft = g.refezione_mancante;
        const tone = hard ? "hard" : soft ? "soft" : "ok";
        const dotClass = {
          hard: "bg-amber-500 ring-1 ring-amber-200 text-white",
          soft: "bg-amber-200 ring-1 ring-amber-100 text-amber-900",
          ok: "bg-emerald-500 ring-1 ring-emerald-100 text-white",
        }[tone];
        const tooltip = hard
          ? `G${g.numero_giornata}: violazione hard`
          : soft
            ? `G${g.numero_giornata}: violazione soft`
            : `G${g.numero_giornata}: ok`;
        return (
          <li key={g.id}>
            <a
              href={`#giornata-${g.numero_giornata}`}
              className={cn(
                "grid h-4 w-4 place-items-center rounded-full font-mono text-[8px] font-bold transition-transform hover:scale-110",
                dotClass,
              )}
              title={tooltip}
              aria-label={tooltip}
            >
              {g.numero_giornata}
            </a>
          </li>
        );
      })}
    </ol>
  );
}

// ────────────────────────────────────────────────────────────────────────
// Blocchi sulla timeline
// ────────────────────────────────────────────────────────────────────────

function BloccoSegment({
  blocco,
  oraOffset,
  onSelect,
  isSelected,
}: {
  blocco: TurnoPdcBlocco;
  oraOffset: 0 | 4;
  onSelect: () => void;
  isSelected: boolean;
}) {
  const inizio = parseTimeToMin(blocco.ora_inizio);
  const fine = parseTimeToMin(blocco.ora_fine);
  if (inizio === null || fine === null) return null;

  const offsetMin = oraOffset * 60;
  const startPx = minToPx(inizio, offsetMin);
  let endPx = minToPx(fine, offsetMin);
  if (endPx <= startPx) {
    // Cross-mezzanotte (es. DORMITA 22:00→06:00): estende oltre il bordo
    // destro mantenendo la durata reale, coerente col Gantt giro materiale.
    endPx = minToPx(fine + AXIS_TOTAL_MIN, offsetMin);
  }
  const widthPx = Math.max(6, endPx - startPx);

  const tipo = blocco.tipo_evento;
  const tooltip = bloccoTooltip(blocco);

  // CONDOTTA / VETTURA — layout multi-line ricco (stazioni sopra, treno
  // dentro, orari sotto), coerente col CommercialeBlocco del Gantt giro.
  // Per gli altri tipi (REFEZ/ACC/CV/PK/SCOMP/PRESA/FINE/DORMITA), blocco
  // semplice a unica riga con label centrale.
  if (tipo === "CONDOTTA" || tipo === "VETTURA") {
    return (
      <CommercialBlock
        blocco={blocco}
        startPx={startPx}
        widthPx={widthPx}
        tooltip={tooltip}
        onSelect={onSelect}
        isSelected={isSelected}
      />
    );
  }

  return (
    <SimpleBlock
      blocco={blocco}
      startPx={startPx}
      widthPx={widthPx}
      tooltip={tooltip}
      onSelect={onSelect}
      isSelected={isSelected}
    />
  );
}

/**
 * Blocco "ricco" multi-line per CONDOTTA / VETTURA — i tipi di blocco che
 * portano effettivamente l'utente da A a B e meritano un layout esplicito
 * con stazioni e orari, coerente col CommercialeBlocco del Gantt giro.
 *
 * Soglie scalate a 40px/h: ≥47px mostra stazioni, ≥33px mostra orari.
 */
function CommercialBlock({
  blocco,
  startPx,
  widthPx,
  tooltip,
  onSelect,
  isSelected,
}: {
  blocco: TurnoPdcBlocco;
  startPx: number;
  widthPx: number;
  tooltip: string;
  onSelect: () => void;
  isSelected: boolean;
}) {
  const showStazioni = widthPx >= 47;
  const showOrari = widthPx >= 33;
  const stazioneDa = stazioneShort(blocco.stazione_da_nome ?? blocco.stazione_da_codice);
  const stazioneA = stazioneShort(blocco.stazione_a_nome ?? blocco.stazione_a_codice);

  const isCondotta = blocco.tipo_evento === "CONDOTTA";
  // Palette: CONDOTTA = blu primary (cuore del lavoro PdC), VETTURA =
  // sky-200 (passeggero). Centrale colorato + bordi laterali (etichette
  // stazione, orari) trasparenti su sfondo timeline.
  const stazioniColor = isCondotta ? "text-primary" : "text-sky-700";
  const centerBg = isCondotta
    ? "bg-primary text-primary-foreground"
    : "bg-sky-200 text-sky-900";

  const arrow = "→";
  const treno =
    blocco.numero_treno !== null && blocco.numero_treno.length > 0
      ? blocco.numero_treno
      : blocco.tipo_evento;

  return (
    <button
      type="button"
      onClick={onSelect}
      title={tooltip}
      aria-pressed={isSelected}
      aria-label={`${blocco.tipo_evento} ${treno} — apri dettagli`}
      className={cn(
        "absolute cursor-pointer overflow-visible text-left transition focus:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-1",
        isSelected && "z-10",
      )}
      style={{
        left: `${startPx}px`,
        width: `${widthPx}px`,
        top: 6,
        height: TIMELINE_ROW_HEIGHT_PX - 12,
      }}
    >
      {/* Riga 1: stazione_da | stazione_a */}
      {showStazioni ? (
        <div
          className={cn(
            "flex justify-between gap-1 font-mono text-[10px] font-semibold leading-none",
            stazioniColor,
          )}
        >
          <span className="min-w-0 flex-1 truncate text-left">{stazioneDa}</span>
          <span className="min-w-0 flex-1 truncate text-right">{stazioneA}</span>
        </div>
      ) : (
        <div className="h-[10px]" aria-hidden />
      )}

      {/* Riga 2: barra colorata centrata con treno+freccia */}
      <div
        className={cn(
          "relative mt-1.5 flex h-7 items-center justify-center rounded-sm shadow-sm transition",
          centerBg,
          isSelected && "ring-2 ring-amber-400 ring-offset-1",
        )}
      >
        <span className="truncate px-1 font-mono text-[11px] font-semibold tabular-nums">
          {arrow} {treno}
        </span>
      </div>

      {/* Riga 3: ora_inizio | ora_fine */}
      {showOrari ? (
        <div className="mt-1 flex justify-between gap-1 font-mono text-[9px] leading-none tabular-nums text-muted-foreground">
          <span className="truncate">{formatTimeShort(blocco.ora_inizio)}</span>
          <span className="truncate">{formatTimeShort(blocco.ora_fine)}</span>
        </div>
      ) : (
        <div className="mt-1 h-[9px]" aria-hidden />
      )}
    </button>
  );
}

/**
 * Blocco semplice per REFEZ / ACC / CV / PK / SCOMP / PRESA / FINE /
 * DORMITA — eventi accessori che non hanno la stessa rilevanza
 * spaziale di una corsa. Layout a unica riga, label centrale, altezza
 * media (più alto dei "thin" del MR precedente per continuità verticale
 * col CommercialBlock h-7 + offset 6+1.5 = 14.5).
 */
function SimpleBlock({
  blocco,
  startPx,
  widthPx,
  tooltip,
  onSelect,
  isSelected,
}: {
  blocco: TurnoPdcBlocco;
  startPx: number;
  widthPx: number;
  tooltip: string;
  onSelect: () => void;
  isSelected: boolean;
}) {
  const tipo = blocco.tipo_evento;
  const colorClass = colorForTipoEvento(tipo);
  const label = bloccoLabel(blocco);
  const isShort = widthPx < 24;

  // PRESA / FINE / PK / SCOMP — eventi "fermi": barra sottile h-3 sulla
  // mid-line, segnale visivo che non c'è movimento commerciale.
  const isThin = tipo === "PRESA" || tipo === "FINE" || tipo === "PK" || tipo === "SCOMP";

  if (isThin) {
    return (
      <button
        type="button"
        onClick={onSelect}
        title={tooltip}
        aria-label={tooltip}
        aria-pressed={isSelected}
        className={cn(
          "absolute flex items-center justify-center rounded-sm transition focus:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-1",
          colorClass,
          isSelected && "ring-2 ring-amber-400 ring-offset-1",
        )}
        style={{
          left: `${startPx}px`,
          width: `${widthPx}px`,
          top: TIMELINE_ROW_HEIGHT_PX / 2 - 5,
          height: 10,
        }}
      />
    );
  }

  // REFEZ / ACC / CV / DORMITA — eventi con durata significativa che
  // meritano un blocco di altezza media (h-7 = 28px) ma a singola
  // riga, allineato col centro della timeline.
  const top = (TIMELINE_ROW_HEIGHT_PX - 28) / 2;
  return (
    <button
      type="button"
      onClick={onSelect}
      title={tooltip}
      aria-pressed={isSelected}
      aria-label={`${tipo} — apri dettagli`}
      className={cn(
        "absolute flex items-center justify-center overflow-hidden rounded text-left shadow-sm transition focus:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-1",
        colorClass,
        isSelected && "ring-2 ring-amber-400 ring-offset-1",
      )}
      style={{
        left: `${startPx}px`,
        width: `${widthPx}px`,
        top,
        height: 28,
      }}
    >
      {!isShort && (
        <span className="truncate px-1.5 text-[11px] font-semibold leading-none">
          {label}
        </span>
      )}
    </button>
  );
}

/**
 * Palette per tipo_evento PdC. Niente .seg-* del Gantt giro: lì il rosso
 * carica semantica "commerciale" che qui non esiste. Qui i colori
 * mappano la natura del lavoro PdC.
 */
function colorForTipoEvento(tipo: string): string {
  switch (tipo) {
    case "CONDOTTA":
      return "bg-primary text-primary-foreground"; // blu ARTURO — cuore del lavoro
    case "VETTURA":
      return "bg-sky-200 text-sky-900"; // PdC come passeggero
    case "REFEZ":
      return "bg-emerald-200 text-emerald-900"; // pausa pasto
    case "ACCp":
    case "ACCa":
      return "bg-amber-200 text-amber-900"; // accessori treno
    case "CVp":
    case "CVa":
      return "bg-orange-300 text-orange-900"; // cambio volante
    case "PK":
    case "SCOMP":
      return "bg-slate-200 text-slate-700"; // parking / comparto
    case "PRESA":
    case "FINE":
      return "bg-slate-400 text-slate-50"; // presa/fine servizio (più scuro)
    case "DORMITA":
      return "bg-violet-300 text-violet-900"; // FR pernotto
    default:
      return "bg-muted text-muted-foreground";
  }
}

function bloccoLabel(b: TurnoPdcBlocco): string {
  if (b.tipo_evento === "CONDOTTA" && b.numero_treno !== null && b.numero_treno.length > 0) {
    return b.numero_treno;
  }
  if (b.tipo_evento === "DORMITA") return "FR";
  return b.tipo_evento;
}

function bloccoTooltip(b: TurnoPdcBlocco): string {
  const da = stazioneLabel(b.stazione_da_nome, b.stazione_da_codice);
  const a = stazioneLabel(b.stazione_a_nome, b.stazione_a_codice);
  const treno = b.numero_treno !== null ? `\nTreno ${b.numero_treno}` : "";
  const note = b.accessori_note !== null ? `\n${b.accessori_note}` : "";
  const durata = b.durata_min !== null ? ` (${b.durata_min}')` : "";
  return `${b.tipo_evento}${durata} · ${b.ora_inizio ?? "?"} → ${b.ora_fine ?? "?"}\n${da} → ${a}${treno}${note}`;
}

function stazioneLabel(nome: string | null, codice: string | null): string {
  if (nome !== null && nome.length > 0) return nome;
  if (codice !== null && codice.length > 0) return codice;
  return "—";
}

/**
 * Versione short del nome stazione per i blocchi multi-line del Gantt.
 * Pattern condiviso col Gantt giro: nomi corti pass-through, nomi
 * 2-parole tengono la parte distintiva (es. "MILANO ROGOREDO" → "ROGOREDO"),
 * fallback troncamento a 8 char + ellipsis.
 */
function stazioneShort(label: string | null): string {
  if (label === null) return "—";
  const trimmed = label.trim();
  if (trimmed.length === 0) return "—";
  if (trimmed.length <= 9) return trimmed;
  const parole = trimmed.split(/\s+/);
  if (parole.length >= 2) {
    const last = parole[parole.length - 1];
    if (last.length >= 3 && last.length <= 12) return last;
  }
  return trimmed.substring(0, 8) + "…";
}

/** "HH:MM" → "HH MM" (font mono, separator visivo, no `:`). */
function formatTimeShort(t: string | null): string {
  if (t === null) return "— —";
  const m = t.match(/^(\d{2}):(\d{2})/);
  if (m === null) return t;
  return `${m[1]} ${m[2]}`;
}

// ────────────────────────────────────────────────────────────────────────
// Legenda chip orizzontali
// ────────────────────────────────────────────────────────────────────────

function Legenda() {
  return (
    <div className="flex flex-wrap items-center gap-1.5 border-t border-border bg-muted/30 px-4 py-2.5">
      <span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
        Legenda
      </span>
      <LegendaChip label="Condotta" colorClass="bg-primary text-primary-foreground" />
      <LegendaChip label="Vettura" colorClass="bg-sky-200 text-sky-900" />
      <LegendaChip label="Refez" colorClass="bg-emerald-200 text-emerald-900" />
      <LegendaChip label="ACCp / ACCa" colorClass="bg-amber-200 text-amber-900" />
      <LegendaChip label="CV" colorClass="bg-orange-300 text-orange-900" />
      <LegendaChip label="PK / S.COMP" colorClass="bg-slate-200 text-slate-700" />
      <LegendaChip label="Presa / Fine" colorClass="bg-slate-400 text-slate-50" />
      <LegendaChip label="FR" colorClass="bg-violet-300 text-violet-900" />
    </div>
  );
}

function LegendaChip({ label, colorClass }: { label: string; colorClass: string }) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide",
        colorClass,
      )}
    >
      {label}
    </span>
  );
}

// ────────────────────────────────────────────────────────────────────────
// Sequenza blocchi tabella per giornata (sotto il Gantt)
// ────────────────────────────────────────────────────────────────────────

function BlocchiPanel({ giornata }: { giornata: TurnoPdcGiornata }) {
  const refMissing =
    giornata.refezione_mancante ||
    (giornata.refezione_min === 0 && giornata.prestazione_min > 6 * 60);

  return (
    <details className="overflow-hidden rounded-md border border-border bg-white text-xs">
      <summary className="flex cursor-pointer items-center justify-between gap-2 px-3 py-2 font-medium text-foreground">
        <span className="flex items-center gap-2">
          <span className="font-bold">Giornata {giornata.numero_giornata}</span>
          <Badge variant="outline" className="text-[9px]">
            {giornata.variante_calendario}
          </Badge>
          <span className="text-muted-foreground">
            ({giornata.blocchi.length} blocch
            {giornata.blocchi.length === 1 ? "i" : "i"})
          </span>
        </span>
        <span className="font-mono text-[11px] text-muted-foreground">
          {formatHM(giornata.prestazione_min)} prest · {formatHM(giornata.condotta_min)} cond
          {refMissing && (
            <span className="ml-2 text-amber-700">· refez. mancante</span>
          )}
        </span>
      </summary>
      {giornata.blocchi.length === 0 ? (
        <p className="px-3 pb-3 text-xs italic text-muted-foreground">
          Nessun blocco in questa giornata.
        </p>
      ) : (
        <table className="w-full">
          <thead className="bg-secondary/40 text-[10px] uppercase tracking-wider text-muted-foreground">
            <tr>
              <th className="px-2 py-1 text-left">#</th>
              <th className="px-2 py-1 text-left">Tipo</th>
              <th className="px-2 py-1 text-left">Treno</th>
              <th className="px-2 py-1 text-left">Da</th>
              <th className="px-2 py-1 text-left">A</th>
              <th className="px-2 py-1 text-left">Inizio</th>
              <th className="px-2 py-1 text-left">Fine</th>
              <th className="px-2 py-1 text-right">Min</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {giornata.blocchi.map((b) => (
              <tr key={b.id} className="hover:bg-muted/30">
                <td className="px-2 py-1 font-mono text-muted-foreground">{b.seq}</td>
                <td className="px-2 py-1">
                  <BloccoTipoBadge tipo={b.tipo_evento} />
                </td>
                <td className="px-2 py-1">
                  <TrenoCell blocco={b} />
                </td>
                <td className="px-2 py-1">
                  <StazioneCell nome={b.stazione_da_nome} codice={b.stazione_da_codice} />
                </td>
                <td className="px-2 py-1">
                  <StazioneCell nome={b.stazione_a_nome} codice={b.stazione_a_codice} />
                </td>
                <td className="px-2 py-1 tabular-nums">{b.ora_inizio ?? "—"}</td>
                <td className="px-2 py-1 tabular-nums">{b.ora_fine ?? "—"}</td>
                <td className="px-2 py-1 text-right tabular-nums">{b.durata_min ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </details>
  );
}

function TrenoCell({ blocco }: { blocco: TurnoPdcBlocco }) {
  if (blocco.numero_treno === null) return <span>—</span>;
  const idx = blocco.numero_treno_variante_indice;
  const tot = blocco.numero_treno_variante_totale;
  const showVariante = idx !== null && tot !== null && tot > 1;
  return (
    <div className="flex flex-col leading-tight">
      <span className="font-mono font-medium">{blocco.numero_treno}</span>
      {showVariante && (
        <span
          className="text-[10px] text-muted-foreground"
          title={`Questa corsa ha ${tot} varianti (origini/orari/periodi diversi)`}
        >
          variante {idx}/{tot}
        </span>
      )}
    </div>
  );
}

function StazioneCell({ nome, codice }: { nome: string | null; codice: string | null }) {
  if (nome === null && codice === null) return <span>—</span>;
  return (
    <div className="flex flex-col leading-tight">
      <span className="font-medium">{nome ?? codice}</span>
      {nome !== null && codice !== null && (
        <span className="font-mono text-[10px] text-muted-foreground">{codice}</span>
      )}
    </div>
  );
}

function BloccoTipoBadge({ tipo }: { tipo: string }) {
  switch (tipo) {
    case "CONDOTTA":
      return <Badge variant="default">condotta</Badge>;
    case "VETTURA":
      return <Badge variant="secondary">vettura</Badge>;
    case "REFEZ":
      return <Badge variant="success">refez</Badge>;
    case "ACCp":
      return <Badge variant="warning">ACCp</Badge>;
    case "ACCa":
      return <Badge variant="warning">ACCa</Badge>;
    case "PK":
      return <Badge variant="outline">PK</Badge>;
    case "SCOMP":
      return <Badge variant="outline">S.COMP</Badge>;
    case "PRESA":
      return <Badge variant="outline">presa</Badge>;
    case "FINE":
      return <Badge variant="outline">fine</Badge>;
    case "CVp":
      return <Badge variant="warning">CVp</Badge>;
    case "CVa":
      return <Badge variant="warning">CVa</Badge>;
    case "DORMITA":
      return <Badge variant="secondary">FR</Badge>;
    default:
      return <Badge variant="outline">{tipo}</Badge>;
  }
}

// ────────────────────────────────────────────────────────────────────────
// Helpers
// ────────────────────────────────────────────────────────────────────────

function parseTimeToMin(t: string | null): number | null {
  if (t === null || t.length === 0) return null;
  const parts = t.split(":");
  if (parts.length < 2) return null;
  const h = Number.parseInt(parts[0], 10);
  const m = Number.parseInt(parts[1], 10);
  if (Number.isNaN(h) || Number.isNaN(m)) return null;
  return h * 60 + m;
}

/** Minuti da 00:00 → pixel sulla timeline shiftata di `offsetMin`. */
function minToPx(min: number, offsetMin: number): number {
  let rel = min - offsetMin;
  if (rel < 0) rel += AXIS_TOTAL_MIN;
  return (rel / AXIS_TOTAL_MIN) * TIMELINE_WIDTH_PX;
}

function formatHM(min: number): string {
  if (min === 0) return "0h00";
  const h = Math.floor(min / 60);
  const m = min % 60;
  return `${h}h${m.toString().padStart(2, "0")}`;
}

// ────────────────────────────────────────────────────────────────────────
// Dialog dettagli blocco (MR 7.11.6)
// ────────────────────────────────────────────────────────────────────────

interface BloccoDetailDialogProps {
  detail: { blocco: TurnoPdcBlocco; giornataNumero: number } | null;
  onClose: () => void;
}

function BloccoDetailDialog({ detail, onClose }: BloccoDetailDialogProps) {
  const open = detail !== null;
  const blocco = detail?.blocco;
  const giornataNumero = detail?.giornataNumero;

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) onClose(); }}>
      <DialogContent className="max-w-xl">
        {blocco !== undefined && giornataNumero !== undefined && (
          <>
            <DialogHeader>
              <div className="flex items-center gap-2">
                <span
                  className={cn(
                    "inline-flex items-center rounded px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide",
                    colorForTipoEvento(blocco.tipo_evento),
                  )}
                >
                  {blocco.tipo_evento}
                </span>
                <DialogTitle className="text-base">
                  {bloccoTitolo(blocco)}
                </DialogTitle>
              </div>
              <DialogDescription>
                Giornata {giornataNumero} · Blocco #{blocco.seq}
              </DialogDescription>
            </DialogHeader>

            <div className="flex flex-col gap-3 text-sm">
              {/* Stazioni */}
              <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-2 rounded-md border border-border bg-muted/30 p-3">
                <div className="text-left">
                  <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                    Da
                  </div>
                  <div className="font-semibold text-foreground">
                    {blocco.stazione_da_nome ?? blocco.stazione_da_codice ?? "—"}
                  </div>
                  {blocco.stazione_da_nome !== null && blocco.stazione_da_codice !== null && (
                    <div className="font-mono text-[10px] text-muted-foreground">
                      {blocco.stazione_da_codice}
                    </div>
                  )}
                </div>
                <ArrowRight className="h-5 w-5 text-muted-foreground" aria-hidden />
                <div className="text-right">
                  <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                    A
                  </div>
                  <div className="font-semibold text-foreground">
                    {blocco.stazione_a_nome ?? blocco.stazione_a_codice ?? "—"}
                  </div>
                  {blocco.stazione_a_nome !== null && blocco.stazione_a_codice !== null && (
                    <div className="font-mono text-[10px] text-muted-foreground">
                      {blocco.stazione_a_codice}
                    </div>
                  )}
                </div>
              </div>

              {/* Orari + durata */}
              <div className="grid grid-cols-3 gap-2 rounded-md border border-border bg-white p-3">
                <DetailField label="Inizio" value={blocco.ora_inizio ?? "—"} mono />
                <DetailField label="Fine" value={blocco.ora_fine ?? "—"} mono />
                <DetailField
                  label="Durata"
                  value={blocco.durata_min !== null ? `${blocco.durata_min} min` : "—"}
                  mono
                />
              </div>

              {/* Treno */}
              {blocco.numero_treno !== null && (
                <div className="grid grid-cols-2 gap-2 rounded-md border border-border bg-white p-3">
                  <DetailField label="Treno" value={blocco.numero_treno} mono />
                  {blocco.numero_treno_variante_indice !== null &&
                    blocco.numero_treno_variante_totale !== null &&
                    blocco.numero_treno_variante_totale > 1 && (
                      <DetailField
                        label="Variante"
                        value={`${blocco.numero_treno_variante_indice}/${blocco.numero_treno_variante_totale}`}
                        mono
                      />
                    )}
                </div>
              )}

              {/* Note accessori */}
              {blocco.accessori_note !== null && blocco.accessori_note.length > 0 && (
                <div className="rounded-md border border-amber-300 bg-amber-50 p-3">
                  <div className="text-[10px] font-semibold uppercase tracking-wider text-amber-800">
                    Note accessori
                  </div>
                  <p className="mt-1 text-sm text-amber-900">{blocco.accessori_note}</p>
                  {blocco.is_accessori_maggiorati && (
                    <Badge variant="warning" className="mt-2 text-[9px]">
                      accessori maggiorati
                    </Badge>
                  )}
                </div>
              )}

              {/* Riferimenti tecnici */}
              <div className="grid grid-cols-3 gap-2 rounded-md border border-border bg-muted/20 p-3 text-xs">
                <DetailField label="Fonte orario" value={blocco.fonte_orario} small />
                {blocco.corsa_commerciale_id !== null && (
                  <DetailField
                    label="Corsa comm."
                    value={`#${blocco.corsa_commerciale_id}`}
                    mono
                    small
                  />
                )}
                {blocco.giro_blocco_id !== null && (
                  <DetailField
                    label="Giro blocco"
                    value={`#${blocco.giro_blocco_id}`}
                    mono
                    small
                  />
                )}
                {blocco.corsa_materiale_vuoto_id !== null && (
                  <DetailField
                    label="Vuoto"
                    value={`#${blocco.corsa_materiale_vuoto_id}`}
                    mono
                    small
                  />
                )}
              </div>
            </div>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}

function DetailField({
  label,
  value,
  mono = false,
  small = false,
}: {
  label: string;
  value: string;
  mono?: boolean;
  small?: boolean;
}) {
  return (
    <div className="flex flex-col gap-0.5">
      <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
        {label}
      </div>
      <div
        className={cn(
          small ? "text-xs" : "text-sm",
          mono && "font-mono tabular-nums",
          "font-medium text-foreground",
        )}
      >
        {value}
      </div>
    </div>
  );
}

function bloccoTitolo(b: TurnoPdcBlocco): string {
  if (b.tipo_evento === "CONDOTTA" && b.numero_treno !== null && b.numero_treno.length > 0) {
    return `Treno ${b.numero_treno}`;
  }
  if (b.tipo_evento === "VETTURA" && b.numero_treno !== null && b.numero_treno.length > 0) {
    return `Vettura su ${b.numero_treno}`;
  }
  if (b.tipo_evento === "DORMITA") return "Dormita FR";
  if (b.tipo_evento === "REFEZ") return "Refezione";
  if (b.tipo_evento === "PRESA") return "Presa servizio";
  if (b.tipo_evento === "FINE") return "Fine servizio";
  if (b.tipo_evento === "CVp") return "Cambio volante (partenza)";
  if (b.tipo_evento === "CVa") return "Cambio volante (arrivo)";
  if (b.tipo_evento === "ACCp") return "Accessori partenza";
  if (b.tipo_evento === "ACCa") return "Accessori arrivo";
  if (b.tipo_evento === "PK") return "Parking";
  if (b.tipo_evento === "SCOMP") return "S.COMP";
  return b.tipo_evento;
}

function ErrorBlock({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div
      role="alert"
      className="flex items-start gap-3 rounded-md border border-destructive/30 bg-destructive/5 p-4"
    >
      <AlertCircle className="mt-0.5 h-5 w-5 text-destructive" aria-hidden />
      <div className="flex flex-1 flex-col gap-2">
        <p className="text-sm font-medium text-destructive">{message}</p>
        {onRetry !== undefined && (
          <Button variant="outline" size="sm" onClick={onRetry} className="self-start">
            Riprova
          </Button>
        )}
      </div>
    </div>
  );
}
