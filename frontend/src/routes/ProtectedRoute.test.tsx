import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import { AuthProvider } from "@/lib/auth/AuthContext";
import { ProtectedRoute } from "@/routes/ProtectedRoute";
import { FAKE_USER, mockFetchSequence } from "@/test/utils";

function renderProtected(initialEntry: string, requiredRole?: string) {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<div>Login Page</div>} />
          <Route path="/forbidden" element={<div>Forbidden Page</div>} />
          <Route element={<ProtectedRoute requiredRole={requiredRole} />}>
            <Route path="/protected" element={<div>Protected Content</div>} />
          </Route>
        </Routes>
      </AuthProvider>
    </MemoryRouter>,
  );
}

describe("ProtectedRoute", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("redirige a /login quando non autenticato", async () => {
    renderProtected("/protected");
    await waitFor(() => {
      expect(screen.getByText("Login Page")).toBeInTheDocument();
    });
    expect(screen.queryByText("Protected Content")).toBeNull();
  });

  it("mostra il content quando autenticato e ruolo soddisfatto", async () => {
    localStorage.setItem("colazione.access_token", "valid");
    mockFetchSequence([{ status: 200, body: FAKE_USER }]);

    renderProtected("/protected", "PIANIFICATORE_GIRO");
    await waitFor(() => {
      expect(screen.getByText("Protected Content")).toBeInTheDocument();
    });
  });

  it("redirige a /forbidden quando il ruolo richiesto manca", async () => {
    localStorage.setItem("colazione.access_token", "valid");
    mockFetchSequence([
      {
        status: 200,
        body: { ...FAKE_USER, roles: ["MANUTENZIONE"], is_admin: false },
      },
    ]);

    renderProtected("/protected", "PIANIFICATORE_GIRO");
    await waitFor(() => {
      expect(screen.getByText("Forbidden Page")).toBeInTheDocument();
    });
    expect(screen.queryByText("Protected Content")).toBeNull();
  });
});
