import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import { AuthProvider } from "@/lib/auth/AuthContext";
import { LoginRoute } from "@/routes/LoginRoute";
import { FAKE_TOKENS, FAKE_USER, mockFetchSequence } from "@/test/utils";

function renderLogin() {
  return render(
    <MemoryRouter initialEntries={["/login"]}>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<LoginRoute />} />
          <Route path="/pianificatore-giro/dashboard" element={<div>Dashboard target</div>} />
        </Routes>
      </AuthProvider>
    </MemoryRouter>,
  );
}

describe("LoginRoute", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("submit con credenziali valide naviga alla dashboard", async () => {
    mockFetchSequence([
      { status: 200, body: FAKE_TOKENS },
      { status: 200, body: FAKE_USER },
    ]);

    renderLogin();

    fireEvent.change(screen.getByLabelText(/utente/i), { target: { value: "mario" } });
    fireEvent.change(screen.getByLabelText(/password/i), { target: { value: "secret" } });
    fireEvent.click(screen.getByRole("button", { name: /entra/i }));

    await waitFor(() => {
      expect(screen.getByText("Dashboard target")).toBeInTheDocument();
    });
  });

  it("mostra messaggio specifico su 401", async () => {
    mockFetchSequence([{ status: 401, body: { detail: "credenziali non valide" } }]);

    renderLogin();

    fireEvent.change(screen.getByLabelText(/utente/i), { target: { value: "mario" } });
    fireEvent.change(screen.getByLabelText(/password/i), { target: { value: "wrong" } });
    fireEvent.click(screen.getByRole("button", { name: /entra/i }));

    await waitFor(() => {
      expect(screen.getByRole("alert").textContent).toMatch(/credenziali non valide/i);
    });
  });

  it("disabilita il submit con campi vuoti", async () => {
    renderLogin();
    const button = screen.getByRole("button", { name: /entra/i });
    expect(button).toBeDisabled();

    fireEvent.change(screen.getByLabelText(/utente/i), { target: { value: "mario" } });
    expect(button).toBeDisabled();

    fireEvent.change(screen.getByLabelText(/password/i), { target: { value: "x" } });
    expect(button).not.toBeDisabled();
  });
});
