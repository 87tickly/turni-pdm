/**
 * Persistenza access + refresh JWT in localStorage.
 *
 * Scelta localStorage (anziché sessionStorage o cookie httpOnly):
 * - sopravvive a chiusura tab → meno attriti per uso desktop
 * - in futuro Tauri leggerà gli stessi token via webview
 *
 * Trade-off noto: vulnerabile a XSS. Mitigato da CSP + nessun
 * `dangerouslySetInnerHTML`. Per multi-utente sullo stesso device
 * un cookie httpOnly sarebbe più rigoroso, ma complicherebbe il
 * desktop wrap.
 */

const ACCESS_KEY = "colazione.access_token";
const REFRESH_KEY = "colazione.refresh_token";

export function getAccessToken(): string | null {
  return localStorage.getItem(ACCESS_KEY);
}

export function setAccessToken(token: string | null): void {
  if (token === null) {
    localStorage.removeItem(ACCESS_KEY);
  } else {
    localStorage.setItem(ACCESS_KEY, token);
  }
}

export function getRefreshToken(): string | null {
  return localStorage.getItem(REFRESH_KEY);
}

export function setRefreshToken(token: string | null): void {
  if (token === null) {
    localStorage.removeItem(REFRESH_KEY);
  } else {
    localStorage.setItem(REFRESH_KEY, token);
  }
}

export function clearTokens(): void {
  localStorage.removeItem(ACCESS_KEY);
  localStorage.removeItem(REFRESH_KEY);
}
