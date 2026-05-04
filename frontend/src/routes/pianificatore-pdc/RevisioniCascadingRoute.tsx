import { Check, GitBranch, ShieldCheck, Users } from "lucide-react";

import { cn } from "@/lib/utils";

/**
 * Sprint 7.10 MR 7.10.5 — Revisioni cascading: coming-soon onesto.
 *
 * Variante v1 dal pacchetto Anthropic Design Handoff
 * (`arturo/09-revisioni-cascading.html`): "Roadmap orizzontale + 3 card
 * descrittive". Brief §5.4: "rendere il coming soon elegante e
 * informativo (timeline, badge WIP, spiegazione del flusso futuro)".
 *
 * Niente flussi mock fittizi: la pagina è un preview narrativo onesto di
 * cosa sarà la feature e quando. La sidebar mostra già il chip "wip"
 * sull'item Rev. cascading per non illudere prima del click.
 *
 * Sprint target: 7.6 — richiede modello `revisione_provvisoria` in DB +
 * algoritmo di propagazione delta dalle revisioni di giro materiale ai
 * turni PdC che lo utilizzano.
 */
export function PianificatorePdcRevisioniCascadingRoute() {
  return (
    <div className="mx-auto flex w-full max-w-5xl flex-col gap-8 py-2">
      {/* breadcrumb */}
      <div className="text-xs text-muted-foreground">
        Home <span className="mx-1 text-muted-foreground/40">/</span> Revisioni
        cascading
      </div>

      {/* HERO */}
      <section className="relative overflow-hidden rounded-2xl border border-border bg-white px-6 pb-10 pt-8 text-center">
        <div
          className="pointer-events-none absolute inset-0 opacity-30"
          style={{
            backgroundImage:
              "linear-gradient(to right, rgba(0,98,204,0.05) 1px, transparent 1px), linear-gradient(to bottom, rgba(0,98,204,0.05) 1px, transparent 1px)",
            backgroundSize: "24px 24px",
          }}
          aria-hidden
        />
        <div className="relative">
          <span className="inline-flex items-center gap-1.5 rounded-full border border-amber-200 bg-amber-100 px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wider text-amber-800">
            <span className="inline-block h-1.5 w-1.5 animate-pulse-dot rounded-full bg-amber-500" />
            In sviluppo · Sprint 7.6
          </span>
          <h1
            className="mt-4 text-5xl font-black tracking-tight"
            style={{
              backgroundImage:
                "linear-gradient(90deg, #0062CC 0%, #B88B5C 60%, #0062CC 100%)",
              WebkitBackgroundClip: "text",
              backgroundClip: "text",
              WebkitTextFillColor: "transparent",
              color: "transparent",
            }}
          >
            Revisioni cascading
          </h1>
          <p className="mx-auto mt-4 max-w-2xl text-base leading-relaxed text-muted-foreground">
            Quando il Pianificatore Giro pubblica un cambio su un giro
            materiale, ARTURO propagherà automaticamente la revisione sui
            turni PdC che lo utilizzano e ti chiederà di validare le
            modifiche. Niente più caccia agli errori manuale.
          </p>
        </div>
      </section>

      {/* ROADMAP */}
      <section className="rounded-xl border border-border bg-white p-8">
        <div className="mb-8 flex items-baseline justify-between">
          <div>
            <h2 className="text-base font-bold tracking-tight">Roadmap</h2>
            <p className="mt-0.5 text-xs text-muted-foreground">
              Estratto dai planning di sprint
            </p>
          </div>
          <div className="text-[10px] uppercase tracking-wider text-muted-foreground/60">
            milestone
          </div>
        </div>

        <div className="relative">
          {/* Barra progress sotto le milestone */}
          <div className="absolute left-0 right-0 top-3 h-1 overflow-hidden rounded-full bg-muted">
            <div
              className="h-full"
              style={{
                width: "35%",
                background: "linear-gradient(90deg, #10b981, #0062CC)",
              }}
            />
          </div>

          <div className="relative grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-4">
            <Milestone
              state="done"
              quarter="Completato · Q1 2026"
              sprint="Sprint 7.4"
              description="Modello dati di propagazione, schema delta tra revisioni di giro materiale."
            />
            <Milestone
              state="now"
              quarter="In corso · Sprint attuale"
              sprint="Sprint 7.5"
              description="Trigger di propagazione + diff visualizer su singolo turno."
            />
            <Milestone
              state="next"
              quarter="Previsto · Q2 2026"
              sprint="Sprint 7.6"
              description="UI di validazione cascading: bulk-accept, override, audit log."
              highlight="↳ rilascio target"
            />
            <Milestone
              state="future"
              quarter="Esplorativo · Q3 2026"
              sprint="Sprint 7.8+"
              description="Auto-resolve di conflitti banali e suggerimenti AI per gli override complessi."
            />
          </div>
        </div>
      </section>

      {/* 3 CARDS DESCRITTIVE */}
      <section className="grid grid-cols-1 gap-5 md:grid-cols-3">
        <FeatureCard
          icon={GitBranch}
          eyebrow="Cosa fa"
          title="Propaga cambi tra ruoli, automaticamente."
          description="Una nuova revisione di giro materiale apre un task di validazione PdC con il diff dei blocchi commerciali interessati: minuti, treni, stazioni."
          tone="primary"
        />
        <FeatureCard
          icon={Users}
          eyebrow="Chi la usa"
          title="Pianificatore PdC, supervisori e auditor."
          description="Il PdC valida; il supervisore può forzare un override motivato; l'auditor consulta lo storico cascading."
          tone="emerald"
        />
        <FeatureCard
          icon={ShieldCheck}
          eyebrow="Quando arriva"
          title="Sprint 7.6, dopo l'algoritmo di propagazione."
          description="Il modello `revisione_provvisoria` arriva in 7.5 (in corso); l'UI di validazione cascading apre il prossimo sprint."
          tone="amber"
        />
      </section>

      {/* Footer info */}
      <div className="rounded-md border border-dashed border-border bg-white px-4 py-3 text-xs text-muted-foreground">
        Endpoint API previsto:{" "}
        <span className="font-mono text-foreground">
          GET /api/revisioni-cascading
        </span>{" "}
        — disponibile da Sprint 7.6.
      </div>
    </div>
  );
}

// ────────────────────────────────────────────────────────────────────────
// Sub-components
// ────────────────────────────────────────────────────────────────────────

interface MilestoneProps {
  state: "done" | "now" | "next" | "future";
  quarter: string;
  sprint: string;
  description: string;
  highlight?: string;
}

function Milestone({ state, quarter, sprint, description, highlight }: MilestoneProps) {
  const dotClass = {
    done: "bg-emerald-500 ring-4 ring-emerald-100 text-white",
    now: "bg-primary ring-4 ring-primary/15 text-white",
    next: "bg-white ring-2 ring-border text-muted-foreground",
    future: "bg-white ring-2 ring-border/60 text-muted-foreground/60",
  }[state];

  const quarterColor = {
    done: "text-emerald-700",
    now: "text-primary",
    next: "text-muted-foreground",
    future: "text-muted-foreground/60",
  }[state];

  const sprintColor = {
    done: "text-foreground",
    now: "text-foreground",
    next: "text-foreground/80",
    future: "text-muted-foreground",
  }[state];

  const descColor = state === "future" ? "text-muted-foreground/70" : "text-muted-foreground";

  return (
    <div className="flex flex-col items-start">
      <div
        className={cn(
          "-ml-1 mb-3 grid h-7 w-7 place-items-center rounded-full font-mono text-[11px]",
          dotClass,
        )}
      >
        {state === "done" ? <Check className="h-3.5 w-3.5" strokeWidth={3} /> : "·"}
      </div>
      <div className={cn("text-[10px] font-semibold uppercase tracking-wider", quarterColor)}>
        {quarter}
      </div>
      <div className={cn("mt-1 text-sm font-bold", sprintColor)}>{sprint}</div>
      <div className={cn("mt-1.5 text-xs", descColor)}>
        {description}
        {highlight !== undefined && (
          <span className="ml-1 font-medium text-amber-700">{highlight}</span>
        )}
      </div>
    </div>
  );
}

interface FeatureCardProps {
  icon: typeof GitBranch;
  eyebrow: string;
  title: string;
  description: string;
  tone: "primary" | "emerald" | "amber";
}

function FeatureCard({ icon: Icon, eyebrow, title, description, tone }: FeatureCardProps) {
  const iconBg = {
    primary: "bg-primary/10 text-primary",
    emerald: "bg-emerald-100 text-emerald-700",
    amber: "bg-amber-100 text-amber-800",
  }[tone];

  return (
    <div className="rounded-xl border border-border bg-white p-6">
      <div className={cn("mb-4 flex h-10 w-10 items-center justify-center rounded-lg", iconBg)}>
        <Icon className="h-5 w-5" aria-hidden />
      </div>
      <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
        {eyebrow}
      </div>
      <h3 className="mt-1.5 text-sm font-bold">{title}</h3>
      <p className="mt-2 text-xs leading-relaxed text-muted-foreground">{description}</p>
    </div>
  );
}
