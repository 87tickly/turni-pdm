import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { listProgrammi, createProgramma } from "@/lib/api/programmi";

describe("api/programmi", () => {
  let fetchSpy: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchSpy = vi.fn();
    vi.spyOn(globalThis, "fetch").mockImplementation(fetchSpy);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("listProgrammi senza filtri non aggiunge query string", async () => {
    fetchSpy.mockResolvedValueOnce(
      new Response(JSON.stringify([]), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    await listProgrammi();
    const url = fetchSpy.mock.calls[0]?.[0] as string;
    expect(url).toBe("http://localhost:8000/api/programmi");
  });

  it("listProgrammi con filtri serializza la query string", async () => {
    fetchSpy.mockResolvedValueOnce(
      new Response(JSON.stringify([]), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    await listProgrammi({ stato: "bozza", stagione: "invernale" });
    const url = fetchSpy.mock.calls[0]?.[0] as string;
    expect(url).toContain("stato=bozza");
    expect(url).toContain("stagione=invernale");
  });

  it("createProgramma manda POST con body JSON", async () => {
    fetchSpy.mockResolvedValueOnce(
      new Response(JSON.stringify({ id: 1 }), {
        status: 201,
        headers: { "Content-Type": "application/json" },
      }),
    );

    await createProgramma({
      nome: "X",
      valido_da: "2026-01-01",
      valido_a: "2026-12-31",
    });

    const init = fetchSpy.mock.calls[0]?.[1] as RequestInit;
    expect(init.method).toBe("POST");
    const body = JSON.parse(init.body as string);
    expect(body.nome).toBe("X");
  });
});
