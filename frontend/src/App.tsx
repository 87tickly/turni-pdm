import { useEffect, useState } from "react";

interface HealthResponse {
  status: string;
  version: string;
}

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export function App() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    void fetch(`${API_BASE_URL}/health`)
      .then(async (r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return (await r.json()) as HealthResponse;
      })
      .then((data) => {
        if (active) setHealth(data);
      })
      .catch((err: unknown) => {
        if (active) setError(err instanceof Error ? err.message : "errore");
      });
    return () => {
      active = false;
    };
  }, []);

  return (
    <div className="flex min-h-screen items-center justify-center bg-background text-foreground">
      <div className="rounded-lg border border-border bg-white p-8 shadow-sm">
        <h1 className="mb-2 text-2xl font-semibold">Colazione</h1>
        <p className="mb-4 text-sm text-muted-foreground">
          Programma di pianificazione ferroviaria nativa — Sprint 0.2
        </p>
        <div className="rounded-md border border-border bg-secondary px-3 py-2 text-xs">
          <span className="font-medium">Backend health:</span>{" "}
          {health ? (
            <span className="text-primary">
              {health.status} (v{health.version})
            </span>
          ) : error ? (
            <span className="text-destructive">non raggiungibile ({error})</span>
          ) : (
            <span className="text-muted-foreground">controllo in corso…</span>
          )}
        </div>
      </div>
    </div>
  );
}
