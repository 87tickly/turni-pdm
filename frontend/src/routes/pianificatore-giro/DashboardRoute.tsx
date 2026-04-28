import { Link } from "react-router-dom";
import { ArrowRight, ListOrdered, Play } from "lucide-react";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/Card";
import { useAuth } from "@/lib/auth/AuthContext";

export function DashboardRoute() {
  const { user } = useAuth();

  return (
    <div className="flex flex-col gap-4">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Dashboard Pianificatore Giro</h1>
        <p className="text-sm text-muted-foreground">
          Benvenuto{user !== null ? `, ${user.username}` : ""}. Da qui costruisci il programma di
          esercizio, configuri le regole di assegnazione materiale e generi i giri.
        </p>
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <ActionCard
          to="/pianificatore-giro/programmi"
          title="Programmi materiale"
          description="Crea e gestisci i programmi della tua azienda. Ogni programma definisce un periodo di validità + le regole di assegnazione corse → composizione materiale."
          cta="Apri lista programmi"
        />

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Play className="h-4 w-4" aria-hidden /> Genera giri
            </CardTitle>
            <CardDescription>
              Quando un programma è in stato <em>attivo</em>, lancia il builder per costruire i
              convogli (giri materiale) sui giorni e sulla sede selezionati.
            </CardDescription>
          </CardHeader>
          <CardContent className="text-sm text-muted-foreground">
            Apri un programma dalla lista → bottone <strong>"Genera giri"</strong>.
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <ListOrdered className="h-4 w-4" aria-hidden /> Giri persistiti
            </CardTitle>
            <CardDescription>
              Lista dei giri generati con km/giorno, n. giornate, motivo di chiusura (naturale / km
              cap / safety n_giornate).
            </CardDescription>
          </CardHeader>
          <CardContent className="text-sm text-muted-foreground">
            Visibile da dettaglio programma → <strong>"Giri generati"</strong>.
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Visualizzatore Gantt</CardTitle>
            <CardDescription>
              Replica il PDF Trenord di un giro: giornate, blocchi commerciali, vuoti tecnici,
              rientro 9NNNN.
            </CardDescription>
          </CardHeader>
          <CardContent className="text-sm text-muted-foreground">In arrivo (Sub 6.5).</CardContent>
        </Card>
      </div>
    </div>
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
          {cta} <ArrowRight className="h-4 w-4 transition group-hover:translate-x-1" aria-hidden />
        </CardContent>
      </Card>
    </Link>
  );
}
