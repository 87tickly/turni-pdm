import type { ComponentType, SVGProps } from "react";
import { Link, useParams } from "react-router-dom";
import {
  Building2,
  CalendarCheck2,
  IdCard,
  ShieldCheck,
  User as UserIcon,
} from "lucide-react";

import { Card } from "@/components/ui/Card";
import { Spinner } from "@/components/ui/Spinner";
import {
  useIndisponibilita,
  usePersona,
} from "@/hooks/useGestionePersonale";
import { cn } from "@/lib/utils";

/**
 * Sprint 7.9 MR ζ — Scheda persona singola (Gestione Personale).
 *
 * Layout 2-col:
 *  - sx: card anagrafica (matricola, deposito, qualifiche, data assunzione)
 *  - dx: storico indisponibilità (ferie/malattie/ROL passate e future)
 */
export function GestionePersonalePersonaDettaglioRoute() {
  const { personaId } = useParams<{ personaId: string }>();
  const id = personaId !== undefined ? Number(personaId) : undefined;
  const persona = usePersona(id);
  const indisp = useIndisponibilita({});

  const indispDellaPersona =
    persona.data === undefined
      ? []
      : (indisp.data ?? []).filter((i) => i.persona_id === persona.data.id);

  return (
    <div className="flex flex-col gap-5">
      <div className="text-xs text-muted-foreground">
        <Link to="/gestione-personale/dashboard" className="hover:text-primary">
          Home
        </Link>
        <span className="mx-1 text-muted-foreground/40">/</span>
        <Link to="/gestione-personale/persone" className="hover:text-primary">
          Anagrafica PdC
        </Link>
        <span className="mx-1 text-muted-foreground/40">/</span>
        Scheda persona
      </div>

      {persona.isLoading ? (
        <div className="flex items-center justify-center rounded-md border border-border bg-white py-16">
          <Spinner label="Caricamento persona…" />
        </div>
      ) : persona.isError || persona.data === undefined ? (
        <p className="rounded-md border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive" role="alert">
          {persona.error?.message ?? "Persona non trovata"}
        </p>
      ) : (
        <>
          <header className="flex flex-wrap items-end justify-between gap-3">
            <div>
              <h1 className="flex items-center gap-2 text-2xl font-bold tracking-tight text-primary">
                <UserIcon className="h-6 w-6 text-primary/70" aria-hidden />
                <span className="uppercase">{persona.data.cognome}</span>{" "}
                <span className="text-foreground/80">{persona.data.nome}</span>
              </h1>
              <p className="mt-1 text-sm text-muted-foreground">
                Matricola{" "}
                <span className="font-mono text-foreground">
                  {persona.data.codice_dipendente}
                </span>{" "}
                · Profilo{" "}
                <span className="font-medium text-foreground">{persona.data.profilo}</span>
              </p>
            </div>
            <StatoBadge tipo={persona.data.indisponibilita_oggi} />
          </header>

          <section className="grid grid-cols-1 gap-4 lg:grid-cols-3">
            {/* Anagrafica (col 1) */}
            <Card className="flex flex-col gap-3 p-5 lg:col-span-1">
              <h2 className="text-sm font-semibold text-primary">Anagrafica</h2>
              <DettaglioRow
                icon={IdCard}
                label="Matricola"
                value={persona.data.codice_dipendente}
                mono
              />
              <DettaglioRow
                icon={Building2}
                label="Deposito"
                value={
                  persona.data.depot_codice !== null
                    ? `${persona.data.depot_codice} · ${persona.data.depot_display_name ?? ""}`
                    : "—"
                }
                href={
                  persona.data.depot_codice !== null
                    ? `/gestione-personale/depositi/${encodeURIComponent(persona.data.depot_codice)}`
                    : undefined
                }
              />
              <DettaglioRow
                icon={CalendarCheck2}
                label="Assunto"
                value={
                  persona.data.data_assunzione !== null
                    ? new Date(persona.data.data_assunzione).toLocaleDateString("it-IT", {
                        day: "2-digit",
                        month: "long",
                        year: "numeric",
                      })
                    : "—"
                }
              />
              <DettaglioRow
                icon={ShieldCheck}
                label="Stato"
                value={persona.data.is_matricola_attiva ? "Attivo" : "Disattivato"}
              />
              {persona.data.qualifiche.length > 0 && (
                <DettaglioRow
                  icon={ShieldCheck}
                  label="Qualifiche"
                  value={persona.data.qualifiche.join(", ")}
                />
              )}
            </Card>

            {/* Storico indisponibilità (col 2-3) */}
            <Card className="flex flex-col gap-3 p-5 lg:col-span-2">
              <div className="flex items-baseline justify-between">
                <h2 className="text-sm font-semibold text-primary">
                  Storico indisponibilità
                </h2>
                <span className="text-xs text-muted-foreground">
                  {indispDellaPersona.length} voce/i
                </span>
              </div>
              {indisp.isLoading ? (
                <div className="flex items-center justify-center py-12">
                  <Spinner label="Caricamento storico…" />
                </div>
              ) : indispDellaPersona.length === 0 ? (
                <p className="py-8 text-center text-sm text-muted-foreground">
                  Nessuna indisponibilità registrata.
                </p>
              ) : (
                <ul className="flex flex-col divide-y divide-border/60">
                  {indispDellaPersona.map((i) => (
                    <li
                      key={i.id}
                      className="flex items-center justify-between gap-3 py-2.5 text-sm"
                    >
                      <div className="flex flex-col">
                        <span className="font-medium text-foreground">{i.tipo}</span>
                        <span className="text-xs text-muted-foreground">
                          {formatRange(i.data_inizio, i.data_fine)} · {i.giorni_totali}{" "}
                          {i.giorni_totali === 1 ? "giorno" : "giorni"}
                        </span>
                      </div>
                      {i.is_approvato ? (
                        <span className="text-[10px] font-semibold uppercase tracking-wider text-emerald-700">
                          approvata
                        </span>
                      ) : (
                        <span className="text-[10px] font-semibold uppercase tracking-wider text-amber-700">
                          in attesa
                        </span>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </Card>
          </section>

          <p className="text-[11px] text-muted-foreground">
            Sezione email/contatti, calendario assegnazioni e segnalazioni operative —{" "}
            <span className="text-muted-foreground">in arrivo</span>.
          </p>
        </>
      )}
    </div>
  );
}

function formatRange(from: string, to: string): string {
  const f = new Date(from).toLocaleDateString("it-IT", { day: "2-digit", month: "short" });
  const t = new Date(to).toLocaleDateString("it-IT", { day: "2-digit", month: "short", year: "numeric" });
  return `${f} → ${t}`;
}

function StatoBadge({ tipo }: { tipo: string | null }) {
  if (tipo === null) {
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-100 px-3 py-1 text-xs font-semibold text-emerald-800">
        <span className="inline-block h-2 w-2 rounded-full bg-emerald-500" aria-hidden />
        In servizio oggi
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full bg-amber-100 px-3 py-1 text-xs font-semibold text-amber-800">
      <span className="inline-block h-2 w-2 rounded-full bg-amber-500" aria-hidden />
      Oggi: {tipo}
    </span>
  );
}

interface DettaglioRowProps {
  icon: ComponentType<SVGProps<SVGSVGElement>>;
  label: string;
  value: string;
  mono?: boolean;
  href?: string;
}

function DettaglioRow({ icon: Icon, label, value, mono = false, href }: DettaglioRowProps) {
  const valueClass = cn(
    "text-sm",
    mono === true && "font-mono",
    href !== undefined ? "text-primary hover:underline" : "text-foreground",
  );
  return (
    <div className="flex items-start gap-3">
      <Icon className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground/60" aria-hidden />
      <div className="flex flex-col">
        <span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
          {label}
        </span>
        {href !== undefined ? (
          <Link to={href} className={valueClass}>
            {value}
          </Link>
        ) : (
          <span className={valueClass}>{value}</span>
        )}
      </div>
    </div>
  );
}

