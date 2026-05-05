import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, screen, waitFor } from "@testing-library/react";
import { Route, Routes } from "react-router-dom";

import { GestionePersonaleAssegnaPersoneRoute } from "@/routes/gestione-personale/AssegnaPersoneRoute";
import { renderWithProviders } from "@/test/renderWithProviders";

/**
 * Sub-MR 2.bis-b (Sprint 8.0) — Test del drilldown auto-assegna.
 *
 * Mock minimal: `fetch` viene wrappato per servire le response mock per
 * `/api/programmi/:id` (dettaglio), `/api/persone` (dropdown), e le
 * chiamate POST a `/auto-assegna-persone` e `/assegna-manuale`.
 */

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const programmaPdcConfermato = {
  id: 42,
  azienda_id: 1,
  nome: "Programma test",
  valido_da: "2026-05-04",
  valido_a: "2026-05-08",
  stato: "attivo",
  stato_pipeline_pdc: "PDC_CONFERMATO",
  stato_manutenzione: "IN_LAVORAZIONE",
  km_max_giornaliero: null,
  km_max_ciclo: null,
  n_giornate_default: 1,
  n_giornate_min: 4,
  n_giornate_max: 12,
  fascia_oraria_tolerance_min: 30,
  strict_options_json: {
    no_corse_residue: false,
    no_overcapacity: false,
    no_aggancio_non_validato: false,
    no_orphan_blocks: false,
    no_giro_appeso: false,
    no_km_eccesso: false,
  },
  stazioni_sosta_extra_json: [],
  created_at: "2026-04-01T00:00:00+00:00",
  updated_at: "2026-04-01T00:00:00+00:00",
  regole: [],
};

const programmaInLavorazione = {
  ...programmaPdcConfermato,
  id: 7,
  stato_pipeline_pdc: "PDE_IN_LAVORAZIONE",
};

describe("GestionePersonaleAssegnaPersoneRoute", () => {
  beforeEach(() => {
    vi.spyOn(globalThis, "fetch").mockImplementation((async (input) => {
      const url =
        typeof input === "string"
          ? input
          : input instanceof URL
            ? input.href
            : input.url;
      if (url.endsWith("/api/programmi/42")) {
        return jsonResponse(programmaPdcConfermato);
      }
      if (url.endsWith("/api/programmi/7")) {
        return jsonResponse(programmaInLavorazione);
      }
      if (url.includes("/api/persone")) {
        return jsonResponse([]);
      }
      throw new Error(`unexpected fetch: ${url}`);
    }) as typeof fetch);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  function renderRoute(programmaId: number) {
    return renderWithProviders(
      <Routes>
        <Route
          path="/gestione-personale/programmi/:programmaId/assegna"
          element={<GestionePersonaleAssegnaPersoneRoute />}
        />
      </Routes>,
      {
        routerProps: {
          initialEntries: [
            `/gestione-personale/programmi/${programmaId}/assegna`,
          ],
        },
        withAuth: true,
      },
    );
  }

  it("mostra header con nome programma + validità + badge stato", async () => {
    renderRoute(42);
    // Programma test appare in breadcrumb + h1: matchiamo l'h1.
    await waitFor(() => {
      expect(
        screen.getByRole("heading", { level: 1, name: "Programma test" }),
      ).toBeInTheDocument();
    });
    expect(screen.getByText(/2026-05-04/)).toBeInTheDocument();
    expect(screen.getByText(/2026-05-08/)).toBeInTheDocument();
    expect(screen.getByText("PDC_CONFERMATO")).toBeInTheDocument();
  });

  it("bottone Auto-assegna abilitato quando PDC_CONFERMATO", async () => {
    renderRoute(42);
    await waitFor(() => {
      const btn = screen.getByRole("button", { name: /Esegui auto-assegna/i });
      expect(btn).not.toBeDisabled();
    });
  });

  it("bottone Auto-assegna disabilitato + warning banner quando non PDC_CONFERMATO", async () => {
    renderRoute(7);
    await waitFor(() => {
      expect(screen.getByText("PDE_IN_LAVORAZIONE")).toBeInTheDocument();
    });
    const btn = screen.getByRole("button", { name: /Esegui auto-assegna/i });
    expect(btn).toBeDisabled();
    expect(
      screen.getByText(
        /L'auto-assegna è abilitato solo da/i,
      ),
    ).toBeInTheDocument();
  });

  it("empty state se nessun run effettuato", async () => {
    renderRoute(42);
    await waitFor(() => {
      expect(
        screen.getByText(/Nessun run effettuato/i),
      ).toBeInTheDocument();
    });
  });

  it("apre dialog auto-assegna su click bottone e mostra date default", async () => {
    renderRoute(42);
    const btn = await screen.findByRole("button", {
      name: /Esegui auto-assegna/i,
    });
    fireEvent.click(btn);
    await waitFor(() => {
      expect(
        screen.getByRole("heading", { name: /Auto-assegna persone PdC/i }),
      ).toBeInTheDocument();
    });
    const dataDaInput = screen.getByLabelText(
      /Data da \(incluso\)/i,
    ) as HTMLInputElement;
    expect(dataDaInput.value).toBe("2026-05-04");
    const dataAInput = screen.getByLabelText(
      /Data a \(inclusa\)/i,
    ) as HTMLInputElement;
    expect(dataAInput.value).toBe("2026-05-08");
  });
});
