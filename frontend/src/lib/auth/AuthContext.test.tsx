import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import { AuthProvider, useAuth } from "@/lib/auth/AuthContext";
import { getAccessToken, getRefreshToken } from "@/lib/auth/tokenStorage";
import { FAKE_TOKENS, FAKE_USER, mockFetchSequence } from "@/test/utils";

function StatusProbe() {
  const { status, user, login, logout, hasRole } = useAuth();
  return (
    <div>
      <span data-testid="status">{status}</span>
      <span data-testid="username">{user?.username ?? "—"}</span>
      <span data-testid="has-pianificatore">{hasRole("PIANIFICATORE_GIRO") ? "yes" : "no"}</span>
      <button type="button" onClick={() => void login("mario", "secret")}>
        do-login
      </button>
      <button type="button" onClick={logout}>
        do-logout
      </button>
    </div>
  );
}

describe("AuthContext", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("senza token in storage va in unauthenticated", async () => {
    render(
      <AuthProvider>
        <StatusProbe />
      </AuthProvider>,
    );
    await waitFor(() => {
      expect(screen.getByTestId("status").textContent).toBe("unauthenticated");
    });
  });

  it("login popola user, status authenticated, salva i token", async () => {
    mockFetchSequence([
      { status: 200, body: FAKE_TOKENS },
      { status: 200, body: FAKE_USER },
    ]);

    render(
      <AuthProvider>
        <StatusProbe />
      </AuthProvider>,
    );

    // bootstrap: niente token → unauthenticated
    await waitFor(() => {
      expect(screen.getByTestId("status").textContent).toBe("unauthenticated");
    });

    fireEvent.click(screen.getByRole("button", { name: "do-login" }));

    await waitFor(() => {
      expect(screen.getByTestId("status").textContent).toBe("authenticated");
    });
    expect(screen.getByTestId("username").textContent).toBe("mario");
    expect(screen.getByTestId("has-pianificatore").textContent).toBe("yes");
    expect(getAccessToken()).toBe(FAKE_TOKENS.access_token);
    expect(getRefreshToken()).toBe(FAKE_TOKENS.refresh_token);
  });

  it("logout svuota lo state e i token", async () => {
    mockFetchSequence([
      { status: 200, body: FAKE_TOKENS },
      { status: 200, body: FAKE_USER },
    ]);

    render(
      <AuthProvider>
        <StatusProbe />
      </AuthProvider>,
    );
    await waitFor(() => {
      expect(screen.getByTestId("status").textContent).toBe("unauthenticated");
    });
    fireEvent.click(screen.getByRole("button", { name: "do-login" }));
    await waitFor(() => {
      expect(screen.getByTestId("status").textContent).toBe("authenticated");
    });

    fireEvent.click(screen.getByRole("button", { name: "do-logout" }));
    await waitFor(() => {
      expect(screen.getByTestId("status").textContent).toBe("unauthenticated");
    });
    expect(screen.getByTestId("username").textContent).toBe("—");
    expect(getAccessToken()).toBeNull();
    expect(getRefreshToken()).toBeNull();
  });

  it("hasRole è true se admin anche senza il ruolo specifico", async () => {
    mockFetchSequence([
      { status: 200, body: FAKE_TOKENS },
      {
        status: 200,
        body: { user_id: 2, username: "admin", is_admin: true, roles: [], azienda_id: 42 },
      },
    ]);

    render(
      <AuthProvider>
        <StatusProbe />
      </AuthProvider>,
    );
    await waitFor(() => {
      expect(screen.getByTestId("status").textContent).toBe("unauthenticated");
    });
    fireEvent.click(screen.getByRole("button", { name: "do-login" }));
    await waitFor(() => {
      expect(screen.getByTestId("status").textContent).toBe("authenticated");
    });
    expect(screen.getByTestId("has-pianificatore").textContent).toBe("yes");
  });

  it("con token in storage, bootstrap chiama /me e popola lo user", async () => {
    localStorage.setItem("colazione.access_token", "old.access");
    mockFetchSequence([{ status: 200, body: FAKE_USER }]);

    render(
      <AuthProvider>
        <StatusProbe />
      </AuthProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId("status").textContent).toBe("authenticated");
    });
    expect(screen.getByTestId("username").textContent).toBe("mario");
  });
});
