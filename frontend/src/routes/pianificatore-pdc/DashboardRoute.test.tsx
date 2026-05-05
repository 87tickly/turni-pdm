import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import { Route, Routes } from "react-router-dom";

import { PianificatorePdcDashboardRoute } from "@/routes/pianificatore-pdc/DashboardRoute";
import { renderWithProviders } from "@/test/renderWithProviders";
import type { PianificatorePdcOverview } from "@/lib/api/pianificatorePdc";

function makeOverview(over: Partial<PianificatorePdcOverview> = {}): PianificatorePdcOverview {
  return {
    giri_materiali_count: 17,
    turni_pdc_per_impianto: [
      { impianto: "BRESCIA", count: 4 },
      { impianto: "MILANO_GA", count: 8 },
    ],
    turni_pdc_per_deposito: [
      {
        deposito_pdc_id: 1,
        deposito_pdc_codice: "BRESCIA",
        deposito_pdc_display: "Brescia",
        count: 4,
        n_dormite_fr_totali: 0,
      },
      {
        deposito_pdc_id: 2,
        deposito_pdc_codice: "MILANO_GA",
        deposito_pdc_display: "Milano Garibaldi",
        count: 8,
        n_dormite_fr_totali: 0,
      },
    ],
    turni_con_violazioni_hard: 2,
    revisioni_cascading_attive: 0,
    dormite_fr_totali: 0,
    turni_con_fr_cap_violazioni: 0,
    depositi_pdc_totali: 25,
    ...over,
  };
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("PianificatorePdcDashboardRoute", () => {
  let fetchSpy: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchSpy = vi.fn();
    // Sprint 8.0 MR 2 (entry 167): la dashboard ora fa una fetch
    // addizionale a `/api/programmi` per il widget pipeline. I test
    // esistenti mockano solo la prima fetch (overview); con la nuova
    // fetch sarebbero default-undefined → render-error. Wrappiamo
    // ``fetchSpy`` con default sicuri: ``/api/programmi`` → ``[]``,
    // altri URL fallback al mockResolvedValueOnce / a 200 vuoto.
    vi.spyOn(globalThis, "fetch").mockImplementation((async (input, init) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
      if (url.includes("/api/programmi") && !url.includes("last-run")) {
        return jsonResponse([]);
      }
      return fetchSpy(input, init);
    }) as typeof fetch);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  function renderRoute() {
    return renderWithProviders(
      <Routes>
        <Route path="/pianificatore-pdc/dashboard" element={<PianificatorePdcDashboardRoute />} />
      </Routes>,
      {
        routerProps: { initialEntries: ["/pianificatore-pdc/dashboard"] },
        withAuth: true,
      },
    );
  }

  it("mostra titolo + KPI card con valori da overview", async () => {
    fetchSpy.mockResolvedValueOnce(jsonResponse(makeOverview()));

    renderRoute();

    await waitFor(() => {
      expect(
        screen.getByRole("heading", { name: /Dashboard Pianificatore Turno PdC/i }),
      ).toBeInTheDocument();
    });

    // KPI Giri materiali — aspetta che la fetch popoli il valore (loading "…" → "17")
    await waitFor(() => {
      expect(screen.getByText("17")).toBeInTheDocument();
    });
    // KPI Turni PdC totali (somma 4+8 = 12)
    expect(screen.getByText("12")).toBeInTheDocument();
    // Sprint 7.9 MR η: "Su N deposito/i" deriva da `turni_pdc_per_deposito`.
    expect(screen.getByText("Su 2 deposito/i")).toBeInTheDocument();
    // KPI Violazioni hard
    expect(
      screen.getByText("Prestazione/condotta fuori cap"),
    ).toBeInTheDocument();
    // KPI Revisioni cascading
    expect(screen.getByText("Disponibile da Sprint 7.6")).toBeInTheDocument();
  });

  it("renderizza il breakdown turni per impianto", async () => {
    fetchSpy.mockResolvedValueOnce(jsonResponse(makeOverview()));

    renderRoute();

    await waitFor(() => {
      expect(screen.getByText("BRESCIA")).toBeInTheDocument();
    });
    expect(screen.getByText("MILANO_GA")).toBeInTheDocument();
    expect(screen.getByText("4")).toBeInTheDocument();
    expect(screen.getByText("8")).toBeInTheDocument();
  });

  it("breakdown vuoto → messaggio nessun turno", async () => {
    fetchSpy.mockResolvedValueOnce(
      jsonResponse(
        makeOverview({
          turni_pdc_per_impianto: [],
          // Sprint 7.9 MR η: la dashboard guarda `turni_pdc_per_deposito`,
          // serve azzerare anche questo per il caso "nessun turno".
          turni_pdc_per_deposito: [],
        }),
      ),
    );

    renderRoute();

    await waitFor(() => {
      expect(
        screen.getByText(/Nessun turno PdC presente/i),
      ).toBeInTheDocument();
    });
  });

  it("link rapidi puntano alle sub-route del ruolo", async () => {
    fetchSpy.mockResolvedValueOnce(jsonResponse(makeOverview()));

    renderRoute();

    await waitFor(() => {
      expect(screen.getByText("Vista giri materiali")).toBeInTheDocument();
    });

    const linkGiri = screen.getByRole("link", { name: /Apri vista giri/i });
    expect(linkGiri).toHaveAttribute("href", "/pianificatore-pdc/giri");

    const linkTurni = screen.getByRole("link", { name: /Apri lista turni/i });
    expect(linkTurni).toHaveAttribute("href", "/pianificatore-pdc/turni");
  });

  it("error state mostra messaggio di errore", async () => {
    fetchSpy.mockResolvedValueOnce(
      new Response(JSON.stringify({ detail: "boom" }), {
        status: 500,
        headers: { "Content-Type": "application/json" },
      }),
    );

    renderRoute();

    await waitFor(() => {
      expect(screen.getByText(/Errore caricamento KPI/i)).toBeInTheDocument();
    });
  });
});
