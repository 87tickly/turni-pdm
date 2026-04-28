import { vi } from "vitest";

import type { CurrentUser, TokenResponse } from "@/lib/api/auth";

/** Helper: registra una sequenza di risposte fetch da consumare in ordine. */
export function mockFetchSequence(responses: Array<{ status: number; body: unknown }>): void {
  const queue = [...responses];
  vi.spyOn(globalThis, "fetch").mockImplementation(async () => {
    const next = queue.shift();
    if (next === undefined) {
      throw new Error("mockFetchSequence: nessuna risposta residua");
    }
    return new Response(JSON.stringify(next.body), {
      status: next.status,
      headers: { "Content-Type": "application/json" },
    });
  });
}

export const FAKE_TOKENS: TokenResponse = {
  access_token: "fake.access.token",
  refresh_token: "fake.refresh.token",
  token_type: "bearer",
  expires_in_min: 60,
};

export const FAKE_USER: CurrentUser = {
  user_id: 1,
  username: "mario",
  is_admin: false,
  roles: ["PIANIFICATORE_GIRO"],
  azienda_id: 42,
};

export const FAKE_ADMIN: CurrentUser = {
  user_id: 2,
  username: "admin",
  is_admin: true,
  roles: [],
  azienda_id: 42,
};
