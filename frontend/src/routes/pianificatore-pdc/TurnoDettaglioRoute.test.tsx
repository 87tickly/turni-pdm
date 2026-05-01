import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import { Route, Routes } from "react-router-dom";

import { PianificatorePdcTurnoDettaglioRoute } from "@/routes/pianificatore-pdc/TurnoDettaglioRoute";
import { renderWithProviders } from "@/test/renderWithProviders";
import type { TurnoPdcDettaglio } from "@/lib/api/turniPdc";

/**
 * Sprint 7.3 MR 3 — verifica che il viewer turno PdC riusato sotto
 * `/pianificatore-pdc/turni/:turnoId` sia path-aware: il back-link
 * deve puntare a `/pianificatore-pdc/turni` (lista del 2° ruolo) e
 * non al drilldown del giro come quando è raggiunto dal 1° ruolo.
 */

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
    generation_metadata_json: {
      giro_materiale_id: 100,
      violazioni: [],
      fr_giornate: [],
    },
    giornate: [],
    ...over,
  };
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("PianificatorePdcTurnoDettaglioRoute (riuso path-aware)", () => {
  let fetchSpy: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchSpy = vi.fn();
    vi.spyOn(globalThis, "fetch").mockImplementation(fetchSpy);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("back-link punta a /pianificatore-pdc/turni quando aperto sotto path PdC", async () => {
    fetchSpy.mockResolvedValueOnce(jsonResponse(makeTurno()));

    renderWithProviders(
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

    await waitFor(() => {
      expect(screen.getByText(/Lista turni PdC/i)).toBeInTheDocument();
    });

    const backLink = screen.getByRole("link", { name: /Lista turni PdC/i });
    expect(backLink).toHaveAttribute("href", "/pianificatore-pdc/turni");
  });

  it("back-link punta a /pianificatore-giro/giri/:giroId/turni-pdc quando aperto sotto path Giro", async () => {
    fetchSpy.mockResolvedValueOnce(jsonResponse(makeTurno({ id: 42 })));

    renderWithProviders(
      <Routes>
        <Route
          path="/pianificatore-giro/turni-pdc/:turnoId"
          element={<PianificatorePdcTurnoDettaglioRoute />}
        />
      </Routes>,
      {
        routerProps: { initialEntries: ["/pianificatore-giro/turni-pdc/42"] },
        withAuth: true,
      },
    );

    await waitFor(() => {
      expect(screen.getByText(/Lista turni PdC/i)).toBeInTheDocument();
    });

    const backLink = screen.getByRole("link", { name: /Lista turni PdC/i });
    expect(backLink).toHaveAttribute("href", "/pianificatore-giro/giri/100/turni-pdc");
  });
});
