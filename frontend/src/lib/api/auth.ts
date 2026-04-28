/**
 * Wrapper API per gli endpoint /api/auth/* del backend.
 *
 * Gli schemi rispecchiano `colazione.schemas.security`:
 * - `LoginRequest`, `TokenResponse`, `CurrentUser`.
 */

import { apiJson } from "@/lib/api/client";

export interface CurrentUser {
  user_id: number;
  username: string;
  is_admin: boolean;
  roles: string[];
  azienda_id: number;
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in_min: number;
}

export interface LoginRequest {
  username: string;
  password: string;
}

export async function loginApi(req: LoginRequest): Promise<TokenResponse> {
  return apiJson<TokenResponse>("/api/auth/login", {
    method: "POST",
    body: req,
    skipAuthRefresh: true,
  });
}

export async function fetchCurrentUser(): Promise<CurrentUser> {
  return apiJson<CurrentUser>("/api/auth/me", { method: "GET" });
}
