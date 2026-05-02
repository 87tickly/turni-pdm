import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { Route, Routes } from "react-router-dom";

import { ProgrammaDettaglioRoute } from "@/routes/pianificatore-giro/ProgrammaDettaglioRoute";
import { renderWithProviders } from "@/test/renderWithProviders";
import type { ProgrammaDettaglioRead, ProgrammaRegolaAssegnazioneRead } from "@/lib/api/programmi";

function makeRegola(
  over: Partial<ProgrammaRegolaAssegnazioneRead> = {},
): ProgrammaRegolaAssegnazioneRead {
  return {
    id: 1,
    programma_id: 1287,
    filtri_json: [{ campo: "direttrice", op: "eq", valore: "TIRANO-SONDRIO-LECCO-MILANO" }],
    composizione_json: [
      { materiale_tipo_codice: "ETR526", n_pezzi: 1 },
      { materiale_tipo_codice: "ETR425", n_pezzi: 1 },
    ],
    is_composizione_manuale: false,
    materiale_tipo_codice: "ETR526",
    numero_pezzi: 1,
    priorita: 60,
    km_max_ciclo: null,
    note: null,
    created_at: "2026-04-25T10:00:00Z",
    ...over,
  };
}

function makeProgramma(over: Partial<ProgrammaDettaglioRead> = {}): ProgrammaDettaglioRead {
  return {
    id: 1287,
    azienda_id: 2,
    nome: "Test Trenord 2026",
    valido_da: "2026-01-01",
    valido_a: "2026-12-31",
    stato: "bozza",
    km_max_giornaliero: null,
    km_max_ciclo: 10000,
    n_giornate_default: 30,
    fascia_oraria_tolerance_min: 30,
    strict_options_json: {
      no_corse_residue: false,
      no_overcapacity: false,
      no_aggancio_non_validato: false,
      no_orphan_blocks: false,
      no_giro_appeso: false,
      no_km_eccesso: false,
    },
    stazioni_sosta_extra_json: ["S01440"],
    created_by_user_id: 1,
    created_at: "2026-04-25T10:00:00Z",
    updated_at: "2026-04-28T10:00:00Z",
    regole: [makeRegola()],
    ...over,
  };
}

describe("ProgrammaDettaglioRoute", () => {
  let fetchSpy: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchSpy = vi.fn();
    vi.spyOn(globalThis, "fetch").mockImplementation(fetchSpy);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  function jsonResponse(body: unknown, status = 200): Response {
    return new Response(JSON.stringify(body), {
      status,
      headers: { "Content-Type": "application/json" },
    });
  }

  function renderRoute(programmaId = 1287) {
    return renderWithProviders(
      <Routes>
        <Route
          path="/pianificatore-giro/programmi/:programmaId"
          element={<ProgrammaDettaglioRoute />}
        />
      </Routes>,
      { routerProps: { initialEntries: [`/pianificatore-giro/programmi/${programmaId}`] } },
    );
  }

  it("mostra header + configurazione + regole", async () => {
    fetchSpy.mockResolvedValueOnce(jsonResponse(makeProgramma()));

    renderRoute();

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: /Test Trenord 2026/i })).toBeInTheDocument();
    });
    expect(screen.getByText(/Bozza/i)).toBeInTheDocument();
    // Periodo appare in header e in Configurazione (due volte)
    expect(screen.getAllByText(/01\/01\/2026 → 31\/12\/2026/).length).toBeGreaterThan(0);
    // Sezione configurazione (heading h2, non il bottone "Modifica configurazione")
    expect(screen.getByRole("heading", { name: /^Configurazione$/i })).toBeInTheDocument();
    // Sprint 7.7 MR 1: "km/ciclo max" è in tono legacy (entry 86 design).
    // Verifichiamo "Fascia oraria tolerance" come campo presente nella Configurazione.
    expect(screen.getByText(/Fascia oraria tolerance/i)).toBeInTheDocument();
    // Filtri della regola — il campo backend "direttrice" è etichettato "Linea" in UI.
    // Match preciso (^Linea$) per evitare collisioni con altre stringhe contenenti "linea".
    expect(screen.getByText(/^Linea$/)).toBeInTheDocument();
    expect(screen.getByText(/TIRANO-SONDRIO-LECCO-MILANO/)).toBeInTheDocument();
    // Composizione
    expect(screen.getByText(/ETR526 × 1/)).toBeInTheDocument();
    expect(screen.getByText(/ETR425 × 1/)).toBeInTheDocument();
  });

  it("bottone Pubblica disabilitato senza regole", async () => {
    fetchSpy.mockResolvedValueOnce(jsonResponse(makeProgramma({ regole: [] })));

    renderRoute();

    await waitFor(() => {
      expect(screen.getByText(/Nessuna regola configurata/i)).toBeInTheDocument();
    });
    const pubblicaBtn = screen.getByRole("button", { name: /Pubblica/i });
    expect(pubblicaBtn).toBeDisabled();
  });

  it("programma 'attivo' mostra Archivia, regole readonly", async () => {
    fetchSpy.mockResolvedValueOnce(jsonResponse(makeProgramma({ stato: "attivo" })));

    renderRoute();

    await waitFor(() => {
      expect(screen.getByText(/Attivo/i)).toBeInTheDocument();
    });
    expect(screen.getByRole("button", { name: /Archivia/i })).toBeInTheDocument();
    // Schermata 3 design: "Nuova regola" sempre visibile ma disabled se non bozza
    const nuovaRegola = screen.getByRole("button", { name: /Nuova regola/i });
    expect(nuovaRegola).toBeDisabled();
    // No bottone "Rimuovi regola" sulle card
    expect(screen.queryByRole("button", { name: /Rimuovi regola/i })).toBeNull();
  });

  it("apre il dialog Nuova regola con FiltriEditor + ComposizioneEditor", async () => {
    fetchSpy.mockResolvedValueOnce(jsonResponse(makeProgramma({ regole: [] })));
    fetchSpy.mockResolvedValue(jsonResponse([])); // anagrafiche vuote

    renderRoute();

    await waitFor(() => {
      expect(screen.getByText(/Nessuna regola configurata/i)).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: /Aggiungi la prima regola/i }));

    const dialog = await screen.findByRole("dialog", {
      name: /Nuova regola di assegnazione/i,
    });
    expect(within(dialog).getByRole("heading", { name: /^Filtri$/i })).toBeInTheDocument();
    expect(within(dialog).getByRole("heading", { name: /^Composizione$/i })).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: /Aggiungi filtro/i })).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: /Aggiungi regola/i })).toBeInTheDocument();
  });

  it("rimuovi regola: chiede conferma + DELETE + invalida", async () => {
    const programma = makeProgramma();
    fetchSpy.mockResolvedValueOnce(jsonResponse(programma));

    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(true);

    renderRoute();

    await waitFor(() => {
      expect(screen.getByText(/Test Trenord 2026/)).toBeInTheDocument();
    });

    // DELETE response (204)
    fetchSpy.mockResolvedValueOnce(new Response(null, { status: 204 }));
    // Invalidate → re-fetch dettaglio
    fetchSpy.mockResolvedValueOnce(jsonResponse(makeProgramma({ regole: [] })));

    fireEvent.click(screen.getByRole("button", { name: /Rimuovi regola/i }));

    await waitFor(() => {
      const calls = fetchSpy.mock.calls.map((c) =>
        typeof c[0] === "string" ? c[0] : (c[0] as Request).url,
      );
      expect(calls.some((u: string) => u.includes("/api/programmi/1287/regole/1"))).toBe(true);
    });

    expect(confirmSpy).toHaveBeenCalled();
    confirmSpy.mockRestore();
  });
});
