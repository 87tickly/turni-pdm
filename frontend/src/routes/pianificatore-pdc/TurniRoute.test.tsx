import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, screen, waitFor } from "@testing-library/react";
import { Route, Routes } from "react-router-dom";

import { PianificatorePdcTurniRoute } from "@/routes/pianificatore-pdc/TurniRoute";
import { renderWithProviders } from "@/test/renderWithProviders";
import type { TurnoPdcListItem } from "@/lib/api/turniPdc";

function makeTurno(over: Partial<TurnoPdcListItem> = {}): TurnoPdcListItem {
  return {
    id: 1,
    codice: "T-G-001",
    impianto: "MILANO_GA",
    profilo: "Condotta",
    ciclo_giorni: 7,
    valido_da: "2026-04-01",
    stato: "pubblicato",
    created_at: "2026-04-01T10:00:00Z",
    n_giornate: 7,
    prestazione_totale_min: 3360,
    condotta_totale_min: 2100,
    n_violazioni: 0,
    n_dormite_fr: 0,
    is_ramo_split: false,
    split_origine_giornata: null,
    split_ramo: null,
    split_totale_rami: null,
    ...over,
  };
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("PianificatorePdcTurniRoute", () => {
  let fetchSpy: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchSpy = vi.fn();
    vi.spyOn(globalThis, "fetch").mockImplementation(fetchSpy);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  function renderRoute() {
    return renderWithProviders(
      <Routes>
        <Route path="/pianificatore-pdc/turni" element={<PianificatorePdcTurniRoute />} />
      </Routes>,
      {
        routerProps: { initialEntries: ["/pianificatore-pdc/turni"] },
        withAuth: true,
      },
    );
  }

  it("mostra titolo + tabella turni", async () => {
    fetchSpy.mockResolvedValueOnce(
      jsonResponse([
        makeTurno({ id: 1, codice: "T-G-001", impianto: "MILANO_GA" }),
        makeTurno({
          id: 2,
          codice: "T-G-002",
          impianto: "BRESCIA",
          n_violazioni: 3,
        }),
      ]),
    );

    renderRoute();

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: /Lista turni PdC/i })).toBeInTheDocument();
    });

    await waitFor(() => {
      expect(screen.getByTestId("turno-row-1")).toBeInTheDocument();
    });
    expect(screen.getByText("T-G-001")).toBeInTheDocument();
    expect(screen.getByText("T-G-002")).toBeInTheDocument();
    expect(screen.getByText("MILANO_GA")).toBeInTheDocument();
    expect(screen.getByText("BRESCIA")).toBeInTheDocument();
    // Riga con 3 violazioni mostra l'indicatore
    expect(screen.getByText("3")).toBeInTheDocument();
  });

  it("badge ramo split visualizzato per turno splittato", async () => {
    fetchSpy.mockResolvedValueOnce(
      jsonResponse([
        makeTurno({
          id: 1,
          codice: "T-G-001-G02-R1",
          is_ramo_split: true,
          split_origine_giornata: 2,
          split_ramo: 1,
          split_totale_rami: 2,
        }),
      ]),
    );

    renderRoute();

    await waitFor(() => {
      expect(screen.getByText(/Ramo 1\/2/i)).toBeInTheDocument();
    });
  });

  it("DB vuoto → empty state", async () => {
    fetchSpy.mockResolvedValueOnce(jsonResponse([]));

    renderRoute();

    await waitFor(() => {
      expect(screen.getByText(/Nessun turno PdC/i)).toBeInTheDocument();
    });
  });

  it("submit del search box → fetch con q", async () => {
    fetchSpy.mockResolvedValueOnce(jsonResponse([makeTurno()]));
    renderRoute();

    await waitFor(() => {
      expect(screen.getByTestId("turno-row-1")).toBeInTheDocument();
    });

    fetchSpy.mockResolvedValueOnce(jsonResponse([]));
    fireEvent.change(screen.getByLabelText(/Cerca turno per codice/i), {
      target: { value: "TCV" },
    });
    fireEvent.submit(screen.getByLabelText(/Cerca turno per codice/i).closest("form")!);

    await waitFor(() => {
      const callsUrls = fetchSpy.mock.calls.map((c) =>
        typeof c[0] === "string" ? c[0] : (c[0] as Request).url,
      );
      expect(callsUrls.some((u: string) => u.includes("q=TCV"))).toBe(true);
    });
  });

  it("filtro impianto → fetch con impianto param", async () => {
    fetchSpy.mockResolvedValueOnce(jsonResponse([makeTurno()]));
    renderRoute();

    await waitFor(() => {
      expect(screen.getByTestId("turno-row-1")).toBeInTheDocument();
    });

    fetchSpy.mockResolvedValueOnce(jsonResponse([]));
    fireEvent.change(screen.getByLabelText(/Filtra per impianto/i), {
      target: { value: "BRESCIA" },
    });

    await waitFor(() => {
      const callsUrls = fetchSpy.mock.calls.map((c) =>
        typeof c[0] === "string" ? c[0] : (c[0] as Request).url,
      );
      expect(callsUrls.some((u: string) => u.includes("impianto=BRESCIA"))).toBe(true);
    });
  });
});
