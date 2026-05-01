import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, screen, waitFor } from "@testing-library/react";
import { Route, Routes } from "react-router-dom";

import { PianificatorePdcGiriRoute } from "@/routes/pianificatore-pdc/GiriRoute";
import { renderWithProviders } from "@/test/renderWithProviders";
import type { GiroListItem } from "@/lib/api/giri";

function makeGiro(over: Partial<GiroListItem> = {}): GiroListItem {
  return {
    id: 1,
    numero_turno: "A001",
    tipo_materiale: "ALe711",
    materiale_tipo_codice: "ALe711",
    numero_giornate: 5,
    km_media_giornaliera: 320,
    km_media_annua: 110000,
    motivo_chiusura: "naturale",
    chiuso: true,
    stato: "pubblicato",
    created_at: "2026-04-01T10:00:00Z",
    ...over,
  };
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("PianificatorePdcGiriRoute", () => {
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
        <Route path="/pianificatore-pdc/giri" element={<PianificatorePdcGiriRoute />} />
      </Routes>,
      {
        routerProps: { initialEntries: ["/pianificatore-pdc/giri"] },
        withAuth: true,
      },
    );
  }

  it("mostra titolo + tabella con i giri caricati", async () => {
    fetchSpy.mockResolvedValueOnce(
      jsonResponse([
        makeGiro({ id: 1, numero_turno: "A001", tipo_materiale: "ALe711" }),
        makeGiro({ id: 2, numero_turno: "A002", tipo_materiale: "ETR526" }),
      ]),
    );

    renderRoute();

    await waitFor(() => {
      expect(
        screen.getByRole("heading", { name: /Vista giri materiali/i }),
      ).toBeInTheDocument();
    });

    await waitFor(() => {
      expect(screen.getByTestId("giro-row-1")).toBeInTheDocument();
    });
    expect(screen.getByText("A001")).toBeInTheDocument();
    expect(screen.getByText("A002")).toBeInTheDocument();
    expect(screen.getByText("ALe711")).toBeInTheDocument();
    expect(screen.getByText("ETR526")).toBeInTheDocument();
  });

  it("DB vuoto → empty state", async () => {
    fetchSpy.mockResolvedValueOnce(jsonResponse([]));

    renderRoute();

    await waitFor(() => {
      expect(screen.getByText(/Nessun giro materiale/i)).toBeInTheDocument();
    });
  });

  it("submit del search box rifa la fetch con q", async () => {
    fetchSpy.mockResolvedValueOnce(jsonResponse([makeGiro()]));
    renderRoute();

    await waitFor(() => {
      expect(screen.getByTestId("giro-row-1")).toBeInTheDocument();
    });

    fetchSpy.mockResolvedValueOnce(
      jsonResponse([makeGiro({ id: 99, numero_turno: "FIO-99" })]),
    );
    fireEvent.change(screen.getByLabelText(/Cerca giro per numero turno/i), {
      target: { value: "FIO" },
    });
    fireEvent.submit(screen.getByLabelText(/Cerca giro per numero turno/i).closest("form")!);

    await waitFor(() => {
      const callsUrls = fetchSpy.mock.calls.map((c) =>
        typeof c[0] === "string" ? c[0] : (c[0] as Request).url,
      );
      expect(callsUrls.some((u: string) => u.includes("q=FIO"))).toBe(true);
    });
  });

  it("error state mostra il messaggio backend", async () => {
    fetchSpy.mockResolvedValueOnce(
      new Response(JSON.stringify({ detail: "boom" }), {
        status: 500,
        headers: { "Content-Type": "application/json" },
      }),
    );

    renderRoute();

    await waitFor(() => {
      expect(screen.getByRole("alert")).toBeInTheDocument();
      expect(screen.getByText(/boom/)).toBeInTheDocument();
    });
  });
});
