import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/Card";
import { useAuth } from "@/lib/auth/AuthContext";

export function DashboardRoute() {
  const { user } = useAuth();

  return (
    <div className="flex flex-col gap-4">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Dashboard Pianificatore Giro</h1>
        <p className="text-sm text-muted-foreground">
          Benvenuto{user !== null ? `, ${user.username}` : ""}. Da qui costruisci e gestisci i giri
          materiale a partire dal Programma di Esercizio.
        </p>
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Programmi materiale</CardTitle>
            <CardDescription>
              Lista dei programmi della tua azienda con stato (bozza, attivo, archiviato) e regole
              di assegnazione materiale.
            </CardDescription>
          </CardHeader>
          <CardContent className="text-sm text-muted-foreground">
            Sub 6.2 — in arrivo. Per ora la voce è raggiungibile da menu.
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Giri generati</CardTitle>
            <CardDescription>
              Convogli pianificati con km/giorno, n. giornate, motivo di chiusura.
            </CardDescription>
          </CardHeader>
          <CardContent className="text-sm text-muted-foreground">
            Sub 6.4 — visibile dopo aver aperto un programma.
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Visualizzatore Gantt</CardTitle>
            <CardDescription>
              Replica il PDF Trenord di un giro: giornate, blocchi commerciali, vuoti.
            </CardDescription>
          </CardHeader>
          <CardContent className="text-sm text-muted-foreground">Sub 6.5 — in arrivo.</CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Editor regole</CardTitle>
            <CardDescription>
              Configura quali corse vengono coperte da quali composizioni materiali.
            </CardDescription>
          </CardHeader>
          <CardContent className="text-sm text-muted-foreground">
            Sub 6.3 — in arrivo, raggiungibile da dettaglio programma.
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
