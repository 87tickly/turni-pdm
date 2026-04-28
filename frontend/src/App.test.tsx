import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";

import { App } from "@/App";

/**
 * Test smoke: senza token in storage e senza backend raggiungibile,
 * la route default `/` redirige a `/login` (via ProtectedRoute).
 */
describe("App", () => {
  beforeEach(() => {
    localStorage.clear();
    // jsdom non ha fetch reale: fail-fast difensivo
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new Error("network"));
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("mostra la login page quando non autenticato", async () => {
    render(<App />);
    await waitFor(() => {
      expect(screen.getByLabelText(/utente/i)).toBeInTheDocument();
    });
    expect(screen.getByLabelText(/password/i)).toBeInTheDocument();
    // Brand wordmark "ARTURO Business" visibile
    expect(screen.getByLabelText("ARTURO Business")).toBeInTheDocument();
  });
});
