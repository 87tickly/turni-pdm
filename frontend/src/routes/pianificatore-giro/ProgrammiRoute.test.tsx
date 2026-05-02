import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, screen, waitFor, within } from "@testing-library/react";

import { ProgrammiRoute } from "@/routes/pianificatore-giro/ProgrammiRoute";
import { renderWithProviders } from "@/test/renderWithProviders";
import type { ProgrammaMaterialeRead } from "@/lib/api/programmi";

function makeProgramma(over: Partial<ProgrammaMaterialeRead> = {}): ProgrammaMaterialeRead {
  return {
    id: 1,
    azienda_id: 42,
    nome: "Trenord 2025-2026 invernale Tirano",
    valido_da: "2025-12-14",
    valido_a: "2026-12-12",
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
    stazioni_sosta_extra_json: [],
    created_by_user_id: 1,
    created_by_username: "admin",
    created_at: "2026-04-25T10:00:00Z",
    updated_at: "2026-04-28T10:00:00Z",
    ...over,
  };
}

describe("ProgrammiRoute", () => {
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

  it("mostra la lista dei programmi", async () => {
    // listProgrammi → array; detail/giri per riga → singolo / vuoto.
    const p1 = makeProgramma({ id: 1 });
    const p2 = makeProgramma({ id: 2, nome: "Cremona ATR803", stato: "attivo" });
    fetchSpy.mockImplementation((req: unknown) => {
      const url = typeof req === "string" ? req : (req as Request).url;
      if (/\/api\/programmi\/\d+\/giri$/.test(url)) {
        return Promise.resolve(jsonResponse([]));
      }
      if (/\/api\/programmi\/1$/.test(url)) {
        return Promise.resolve(jsonResponse({ ...p1, regole: [] }));
      }
      if (/\/api\/programmi\/2$/.test(url)) {
        return Promise.resolve(jsonResponse({ ...p2, regole: [] }));
      }
      return Promise.resolve(jsonResponse([p1, p2]));
    });

    renderWithProviders(<ProgrammiRoute />);

    // In Calendar view (default) il nome appare 2× (label + barra). Usa getAllByText.
    await waitFor(() => {
      expect(screen.getAllByText(/Trenord 2025-2026 invernale Tirano/).length).toBeGreaterThan(0);
    });
    expect(screen.getAllByText(/Cremona ATR803/).length).toBeGreaterThan(0);
    // Counter top "2 programmi · 1 attivo, 1 bozza" (footer ne ha un altro
    // "2 programmi totali" → match più specifico)
    expect(screen.getByText(/2 programmi · /)).toBeInTheDocument();
    // Switch UI: Calendario è il default — passa a Tabella per testare le righe.
    fireEvent.click(screen.getByRole("button", { name: /Vista tabella/i }));
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /Pubblica Trenord/i })).toBeInTheDocument();
    });
    expect(screen.getByRole("button", { name: /Archivia Cremona/i })).toBeInTheDocument();
  });

  it("mostra empty state senza programmi", async () => {
    fetchSpy.mockResolvedValue(jsonResponse([]));

    renderWithProviders(<ProgrammiRoute />);

    await waitFor(() => {
      expect(screen.getByText(/Nessun programma materiale/i)).toBeInTheDocument();
    });
    expect(screen.getByRole("button", { name: /Crea il primo programma/i })).toBeInTheDocument();
  });

  it("mostra empty state diverso quando ci sono filtri attivi", async () => {
    fetchSpy.mockResolvedValue(jsonResponse([]));

    renderWithProviders(<ProgrammiRoute />);

    await waitFor(() => {
      expect(screen.getByText(/Nessun programma materiale/i)).toBeInTheDocument();
    });

    // Click sul pulsante segmented "Bozza" → applica il filtro stato.
    fireEvent.click(screen.getByRole("button", { name: /^Bozza$/i, pressed: false }));

    await waitFor(() => {
      expect(screen.getByText(/Nessun programma corrisponde ai filtri/i)).toBeInTheDocument();
    });
  });

  it("applica i filtri come query string nella richiesta", async () => {
    fetchSpy.mockResolvedValue(jsonResponse([]));
    renderWithProviders(<ProgrammiRoute />);

    await waitFor(() => {
      expect(fetchSpy).toHaveBeenCalled();
    });

    fireEvent.click(screen.getByRole("button", { name: /^Attivo$/i, pressed: false }));

    await waitFor(() => {
      const calls = fetchSpy.mock.calls.map((c) =>
        typeof c[0] === "string" ? c[0] : (c[0] as Request).url,
      );
      expect(calls.some((u: string) => u.match(/programmi\?stato=attivo/))).toBe(true);
    });
  });

  it("mostra error banner e permette retry", async () => {
    fetchSpy.mockResolvedValue(jsonResponse({ detail: "DB down" }, 500));

    renderWithProviders(<ProgrammiRoute />);

    await waitFor(() => {
      expect(screen.getByRole("alert")).toBeInTheDocument();
    });
    expect(screen.getByText(/DB down/)).toBeInTheDocument();

    const p = makeProgramma();
    fetchSpy.mockImplementation((req: unknown) => {
      const url = typeof req === "string" ? req : (req as Request).url;
      if (/\/api\/programmi\/1\/giri$/.test(url)) {
        return Promise.resolve(jsonResponse([]));
      }
      if (/\/api\/programmi\/1$/.test(url)) {
        return Promise.resolve(jsonResponse({ ...p, regole: [] }));
      }
      return Promise.resolve(jsonResponse([p]));
    });
    fireEvent.click(screen.getByRole("button", { name: /Riprova/i }));

    await waitFor(() => {
      expect(screen.getAllByText(/Trenord 2025-2026 invernale Tirano/).length).toBeGreaterThan(0);
    });
  });

  it("apre il dialog 'Nuovo programma' al click", async () => {
    fetchSpy.mockResolvedValue(jsonResponse([]));
    renderWithProviders(<ProgrammiRoute />);

    await waitFor(() => {
      expect(screen.getByText(/Nessun programma materiale/i)).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: /Nuovo programma/i }));

    expect(
      await screen.findByRole("dialog", { name: /Nuovo programma materiale/i }),
    ).toBeInTheDocument();
  });

  it("crea un programma e invalida la lista", async () => {
    fetchSpy.mockResolvedValue(jsonResponse([]));
    renderWithProviders(<ProgrammiRoute />);

    await waitFor(() => {
      expect(screen.getByText(/Nessun programma materiale/i)).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: /Crea il primo programma/i }));

    const dialog = await screen.findByRole("dialog", {
      name: /Nuovo programma materiale/i,
    });
    fireEvent.change(within(dialog).getByLabelText(/Nome/i), {
      target: { value: "Test prog" },
    });
    fireEvent.change(within(dialog).getByLabelText(/Valido dal/i), {
      target: { value: "2026-01-01" },
    });
    fireEvent.change(within(dialog).getByLabelText(/Valido al/i), {
      target: { value: "2026-12-31" },
    });

    // POST create
    const created = makeProgramma({ id: 99, nome: "Test prog" });
    fetchSpy.mockResolvedValueOnce(jsonResponse(created, 201));
    // Lista ricaricata dopo invalidate
    fetchSpy.mockResolvedValue(jsonResponse([created]));

    fireEvent.click(within(dialog).getByRole("button", { name: /Crea programma/i }));

    await waitFor(() => {
      const calls = fetchSpy.mock.calls.map((c) =>
        typeof c[0] === "string" ? c[0] : (c[0] as Request).url,
      );
      expect(calls.some((u: string) => u.endsWith("/api/programmi"))).toBe(true);
    });

    const postCall = fetchSpy.mock.calls.find((c) => {
      const init = c[1] as RequestInit | undefined;
      return init?.method === "POST";
    });
    expect(postCall).toBeDefined();
    const body = JSON.parse((postCall![1] as RequestInit).body as string);
    expect(body).toMatchObject({
      nome: "Test prog",
      valido_da: "2026-01-01",
      valido_a: "2026-12-31",
    });
    expect(body).not.toHaveProperty("n_giornate_default");
  });
});
