import { Link } from "react-router-dom";

export function ForbiddenRoute() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4">
      <div className="max-w-md text-center">
        <p className="text-sm font-semibold uppercase text-muted-foreground">Errore 403</p>
        <h1 className="mt-2 text-3xl font-semibold tracking-tight">Accesso negato</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          La tua utenza non ha il ruolo necessario per accedere a questa sezione. Contatta un
          amministratore se pensi sia un errore.
        </p>
        <Link to="/" className="mt-6 inline-block text-sm font-medium text-primary hover:underline">
          Torna alla home
        </Link>
      </div>
    </div>
  );
}
