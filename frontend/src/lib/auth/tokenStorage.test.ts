import { beforeEach, describe, expect, it } from "vitest";

import {
  clearTokens,
  getAccessToken,
  getRefreshToken,
  setAccessToken,
  setRefreshToken,
} from "@/lib/auth/tokenStorage";

describe("tokenStorage", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("scrive e legge l'access token", () => {
    setAccessToken("abc.def.ghi");
    expect(getAccessToken()).toBe("abc.def.ghi");
  });

  it("scrive e legge il refresh token", () => {
    setRefreshToken("ref.123");
    expect(getRefreshToken()).toBe("ref.123");
  });

  it("setAccessToken(null) rimuove la chiave", () => {
    setAccessToken("xyz");
    setAccessToken(null);
    expect(getAccessToken()).toBeNull();
  });

  it("clearTokens rimuove access e refresh", () => {
    setAccessToken("a");
    setRefreshToken("r");
    clearTokens();
    expect(getAccessToken()).toBeNull();
    expect(getRefreshToken()).toBeNull();
  });
});
