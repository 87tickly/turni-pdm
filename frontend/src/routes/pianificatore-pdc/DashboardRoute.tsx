import { Link } from "react-router-dom";
import { AlertTriangle, ArrowRight, ListChecks, Workflow } from "lucide-react";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/Card";
import { Spinner } from "@/components/ui/Spinner";
import { useAuth } from "@/lib/auth/AuthContext";
import { usePianificatorePdcOverview } from "@/hooks/usePianificatorePdc";

/**
 * Dashboard home del 2° ruolo (PIANIFICATORE_PDC). Mostra KPI aggregati:
 * - n. giri materiali disponibili come sorgente
 * - turni PdC esistenti raggruppati per impianto (deposito personale)
 * - n. turni con violazioni hard di prestazione/condotta (drilldown
 *   in MR 4 quando avremo la pagina vincoli)
 * - placeholder revisioni cascading (Sprint 7.6+)
 *
 * Le altre 4 schermate del ruolo (vista giri, lista turni, editor turno,
 * revisioni cascading) sono placeholder in MR 1.
 */
export function PianificatorePdcDashboardRoute() {
  const { user } = useAuth();
  const overview = usePianificatorePdcOverview();

  return (
    <div className="flex flex-col gap-4">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">
          Dashboard Pianificatore Turno PdC
        </h1>
        <p className="text-sm text-muted-foreground">
          Benvenuto{user !== null ? `, ${user.username}` : ""}. Da qui costruisci i turni del
          personale di macchina partendo dai giri materiali pubblicati.
        </p>
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-4">
        <KpiCard
          title="Giri materiali"
          icon={Workflow}
          value={overview.data?.giri_materiali_count ?? null}
          loading={overview.isLoading}
          error={overview.isError}
          hint="Sorgente per i turni PdC"
        />
        <KpiCard
          title="Turni PdC"
          icon={ListChecks}
          value={
            overview.data === undefined
              ? null
              : overview.data.turni_pdc_per_impianto.reduce((sum, item) => sum + item.count, 0)
          }
          loading={overview.isLoading}
          error={overview.isError}
          hint={
            overview.data === undefined || overview.data.turni_pdc_per_impianto.length === 0
              ? "Nessun turno generato"
              : `Su ${overview.data.turni_pdc_per_impianto.length} impianto/i`
          }
        />
        <KpiCard
          title="Violazioni hard"
          icon={AlertTriangle}
          value={overview.data?.turni_con_violazioni_hard ?? null}
          loading={overview.isLoading}
          error={overview.isError}
          hint="Prestazione/condotta fuori cap"
          accent={
            overview.data !== undefined && overview.data.turni_con_violazioni_hard > 0
              ? "warning"
              : "neutral"
          }
        />
        <KpiCard
          title="Revisioni cascading"
          icon={Workflow}
          value={overview.data?.revisioni_cascading_attive ?? null}
          loading={overview.isLoading}
          error={overview.isError}
          hint="Disponibile da Sprint 7.6"
        />
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <ActionCard
          to="/pianificatore-pdc/giri"
          title="Vista giri materiali"
          description="Apri i giri pubblicati dal Pianificatore Giro. In sola lettura: la modifica del giro resta competenza del 1° ruolo."
          cta="Apri vista giri"
        />
        <ActionCard
          to="/pianificatore-pdc/turni"
          title="Lista turni PdC"
          description="Esplora i turni esistenti raggruppati per impianto. Filtra per stato, impianto, validità."
          cta="Apri lista turni"
        />
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Distribuzione turni per impianto</CardTitle>
          <CardDescription>
            Breakdown dei turni PdC esistenti, ordinato alfabeticamente.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {overview.isLoading ? (
            <Spinner label="Caricamento KPI…" />
          ) : overview.isError ? (
            <p className="text-sm text-destructive">
              Errore caricamento KPI: {overview.error?.message ?? "errore sconosciuto"}
            </p>
          ) : overview.data === undefined || overview.data.turni_pdc_per_impianto.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              Nessun turno PdC presente per la tua azienda.
            </p>
          ) : (
            <ul className="flex flex-col gap-1 text-sm">
              {overview.data.turni_pdc_per_impianto.map((item) => (
                <li key={item.impianto} className="flex justify-between border-b py-1.5 last:border-0">
                  <span className="font-medium">{item.impianto}</span>
                  <span className="text-muted-foreground">{item.count}</span>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

interface KpiCardProps {
  title: string;
  icon: typeof Workflow;
  value: number | null;
  loading: boolean;
  error: boolean;
  hint: string;
  accent?: "neutral" | "warning";
}

function KpiCard({
  title,
  icon: Icon,
  value,
  loading,
  error,
  hint,
  accent = "neutral",
}: KpiCardProps) {
  return (
    <Card className={accent === "warning" && (value ?? 0) > 0 ? "border-amber-500/60" : undefined}>
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
          <Icon className="h-4 w-4" aria-hidden />
          {title}
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="text-3xl font-semibold tracking-tight">
          {loading ? "…" : error ? "—" : value === null ? "—" : value}
        </div>
        <p className="mt-1 text-xs text-muted-foreground">{hint}</p>
      </CardContent>
    </Card>
  );
}

interface ActionCardProps {
  to: string;
  title: string;
  description: string;
  cta: string;
}

function ActionCard({ to, title, description, cta }: ActionCardProps) {
  return (
    <Link
      to={to}
      className="group block rounded-lg transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
    >
      <Card className="h-full transition group-hover:border-primary/50 group-hover:shadow-md">
        <CardHeader>
          <CardTitle>{title}</CardTitle>
          <CardDescription>{description}</CardDescription>
        </CardHeader>
        <CardContent className="flex items-center gap-1 text-sm font-medium text-primary">
          {cta}
          <ArrowRight className="h-4 w-4 transition group-hover:translate-x-1" aria-hidden />
        </CardContent>
      </Card>
    </Link>
  );
}
