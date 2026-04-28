import { Link } from "react-router-dom";

export function NotFoundRoute() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4">
      <div className="max-w-md text-center">
        <p className="text-sm font-semibold uppercase text-muted-foreground">Errore 404</p>
        <h1 className="mt-2 text-3xl font-semibold tracking-tight">Pagina non trovata</h1>
        <p className="mt-2 text-sm text-muted-foreground">Il percorso richiesto non esiste.</p>
        <Link to="/" className="mt-6 inline-block text-sm font-medium text-primary hover:underline">
          Torna alla home
        </Link>
      </div>
    </div>
  );
}
