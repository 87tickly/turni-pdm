import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import { Route, Routes } from "react-router-dom";

import { PianificatorePdcTurnoDettaglioRoute } from "@/routes/pianificatore-pdc/TurnoDettaglioRoute";
import { renderWithProviders } from "@/test/renderWithProviders";
import type { TurnoPdcDettaglio, TurnoPdcGiornata } from "@/lib/api/turniPdc";

/**
 * Sprint 7.3 MR 4 — verifica che i flag validazione live (per giornata)
 * e il pannello vincoli ciclo (a livello turno) siano renderizzati
 * correttamente.
 */

function makeGiornata(over: Partial<TurnoPdcGiornata> = {}): TurnoPdcGiornata {
  return {
    id: 1,
    numero_giornata: 1,
    variante_calendario: "LMXGV",
    stazione_inizio: "S001",
    stazione_fine: "S002",
    stazione_inizio_nome: "S001",
    stazione_fine_nome: "S002",
    inizio_prestazione: "08:00",
    fine_prestazione: "16:00",
    prestazione_min: 480,
    condotta_min: 240,
    refezione_min: 30,
    is_notturno: false,
    prestazione_violata: false,
    condotta_violata: false,
    refezione_mancante: false,
    blocchi: [],
    ...over,
  };
}

function makeTurno(over: Partial<TurnoPdcDettaglio> = {}): TurnoPdcDettaglio {
  return {
    id: 42,
    codice: "T-PDC-001",
    impianto: "MILANO_GA",
    profilo: "Condotta",
    ciclo_giorni: 7,
    valido_da: "2026-04-01",
    stato: "pubblicato",
    created_at: "2026-04-01T10:00:00Z",
    updated_at: "2026-04-01T10:00:00Z",
    generation_metadata_json: { giro_materiale_id: 100, fr_giornate: [] },
    giornate: [makeGiornata()],
    n_giornate_violanti: 0,
    n_violazioni_hard: 0,
    n_violazioni_soft: 0,
    validazioni_ciclo: [],
    deposito_pdc_id: null,
    deposito_pdc_codice: null,
    deposito_pdc_display: null,
    n_dormite_fr: 0,
    fr_cap_violazioni: [],
    ...over,
  };
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function renderRoute() {
  return renderWithProviders(
    <Routes>
      <Route
        path="/pianificatore-pdc/turni/:turnoId"
        element={<PianificatorePdcTurnoDettaglioRoute />}
      />
    </Routes>,
    {
      routerProps: { initialEntries: ["/pianificatore-pdc/turni/42"] },
      withAuth: true,
    },
  );
}

describe("TurnoPdc validazioni live (Sprint 7.3 MR 4)", () => {
  let fetchSpy: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchSpy = vi.fn();
    vi.spyOn(globalThis, "fetch").mockImplementation(fetchSpy);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("turno senza violazioni: nessun pannello giornate-violanti, nessun badge per giornata", async () => {
    fetchSpy.mockResolvedValueOnce(jsonResponse(makeTurno()));
    renderRoute();

    await waitFor(() => {
      expect(screen.getByText(/Giornata 1/i)).toBeInTheDocument();
    });
    expect(screen.queryByText(/Giornate violanti/i)).toBeNull();
    expect(screen.queryByTestId("badge-prestazione-violata-g1")).toBeNull();
    expect(screen.queryByTestId("badge-condotta-violata-g1")).toBeNull();
    expect(screen.queryByTestId("badge-refezione-mancante-g1")).toBeNull();
  });

  it("turno con prestazione_violata mostra badge per quella giornata", async () => {
    fetchSpy.mockResolvedValueOnce(
      jsonResponse(
        makeTurno({
          giornate: [makeGiornata({ prestazione_violata: true, prestazione_min: 600 })],
          n_giornate_violanti: 1,
          n_violazioni_hard: 1,
        }),
      ),
    );
    renderRoute();

    await waitFor(() => {
      expect(screen.getByTestId("badge-prestazione-violata-g1")).toBeInTheDocument();
    });
    expect(screen.getByText("prest. fuori cap")).toBeInTheDocument();
  });

  it("turno con condotta_violata + refezione_mancante mostra entrambi i badge", async () => {
    fetchSpy.mockResolvedValueOnce(
      jsonResponse(
        makeTurno({
          giornate: [
            makeGiornata({
              condotta_violata: true,
              condotta_min: 360,
              refezione_mancante: true,
              prestazione_min: 400,
              refezione_min: 0,
            }),
          ],
          n_giornate_violanti: 1,
          n_violazioni_hard: 1,
          n_violazioni_soft: 1,
        }),
      ),
    );
    renderRoute();

    await waitFor(() => {
      expect(screen.getByTestId("badge-condotta-violata-g1")).toBeInTheDocument();
    });
    expect(screen.getByTestId("badge-refezione-mancante-g1")).toBeInTheDocument();
  });

  it("aggregati Stats: n_giornate_violanti e n_violazioni_hard/soft visibili", async () => {
    fetchSpy.mockResolvedValueOnce(
      jsonResponse(
        makeTurno({
          n_giornate_violanti: 2,
          n_violazioni_hard: 3,
          n_violazioni_soft: 1,
        }),
      ),
    );
    renderRoute();

    await waitFor(() => {
      expect(screen.getByText(/Giornate violanti/i)).toBeInTheDocument();
    });
    expect(screen.getByText("2 / 1")).toBeInTheDocument();
    expect(screen.getByText(/Violazioni hard/i)).toBeInTheDocument();
    expect(screen.getByText(/Violazioni soft/i)).toBeInTheDocument();
  });

  it("pannello vincoli ciclo visibile se validazioni_ciclo non vuoto", async () => {
    fetchSpy.mockResolvedValueOnce(
      jsonResponse(
        makeTurno({
          validazioni_ciclo: ["riposo_settimanale_corto", "fr_oltre_3_su_28gg"],
        }),
      ),
    );
    renderRoute();

    await waitFor(() => {
      expect(screen.getByTestId("vincoli-ciclo-panel")).toBeInTheDocument();
    });
    expect(screen.getByText(/2 segnalazioni/i)).toBeInTheDocument();
    expect(screen.getByText(/riposo_settimanale_corto/)).toBeInTheDocument();
    expect(screen.getByText(/fr_oltre_3_su_28gg/)).toBeInTheDocument();
  });

  it("pannello vincoli ciclo NASCOSTO se validazioni_ciclo vuoto", async () => {
    fetchSpy.mockResolvedValueOnce(jsonResponse(makeTurno()));
    renderRoute();

    await waitFor(() => {
      expect(screen.getByText(/Giornata 1/i)).toBeInTheDocument();
    });
    expect(screen.queryByTestId("vincoli-ciclo-panel")).toBeNull();
  });
});
