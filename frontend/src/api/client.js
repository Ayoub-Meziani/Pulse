// The only module that talks to the PULSE API (contract/openapi.json, base path /api/v1).
// The backend decides authentication, authorization and every clinical level; this file only
// moves requests and sessions. Credentials, tokens and response bodies are never logged.
//
// Session contract (POST /auth/login, POST /auth/refresh -> SessionOut):
//   { access_token, refresh_token, expires_at, token_type: "bearer", user: { id, role, ... } }
// A rejected or expired access token answers 401 with error.code "invalid_token"; a request with
// no token answers 401 "not_authenticated". Refresh tokens rotate: each refresh returns a new one.
// The contract has no logout endpoint, so logout only clears the local session.

export const API_BASE = "/api/v1";

const ACCESS_KEY = "pulse.access_token";
const REFRESH_KEY = "pulse.refresh_token";

export class ApiError extends Error {
  constructor(status, code, message, details = null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

// ---------------------------------------------------------------- session storage
// sessionStorage keeps the login across a page refresh in the same tab and is dropped when the
// tab closes. If storage is unavailable (private mode) the tokens live in memory for this page.
let memory = { access: null, refresh: null };

function store(key, value) {
  try {
    if (value) sessionStorage.setItem(key, value);
    else sessionStorage.removeItem(key);
  } catch {
    /* storage unavailable: the in-memory copy still works */
  }
}

function load(key) {
  try {
    return sessionStorage.getItem(key);
  } catch {
    return null;
  }
}

export function getAccessToken() {
  return load(ACCESS_KEY) ?? memory.access;
}

function getRefreshToken() {
  return load(REFRESH_KEY) ?? memory.refresh;
}

function saveSession(session) {
  memory = { access: session.access_token, refresh: session.refresh_token };
  store(ACCESS_KEY, session.access_token);
  store(REFRESH_KEY, session.refresh_token);
}

export function hasSession() {
  return Boolean(getAccessToken() || getRefreshToken());
}

const expiredListeners = new Set();

/** Called when the session is cleared because it can no longer be renewed. Returns an unsubscribe. */
export function onSessionExpired(listener) {
  expiredListeners.add(listener);
  return () => expiredListeners.delete(listener);
}

export function clearSession() {
  memory = { access: null, refresh: null };
  store(ACCESS_KEY, null);
  store(REFRESH_KEY, null);
}

function expireSession() {
  clearSession();
  expiredListeners.forEach((listener) => listener());
}

// ---------------------------------------------------------------- requests
function networkError() {
  return new ApiError(0, "network_error", "Impossible de joindre le serveur. Vérifiez votre connexion.");
}

async function parse(response) {
  if (response.status === 204) return null;
  try {
    return await response.json();
  } catch {
    return null;
  }
}

function toError(response, body) {
  const error = body?.error;
  return new ApiError(
    response.status,
    error?.code ?? `http_${response.status}`,
    error?.message ?? "Erreur inattendue. Réessayez.",
    error?.details ?? null,
  );
}

function url(path, query) {
  const params = new URLSearchParams();
  Object.entries(query ?? {}).forEach(([key, value]) => {
    if (value !== undefined && value !== null) params.set(key, String(value));
  });
  const qs = params.toString();
  return `${API_BASE}${path}${qs ? `?${qs}` : ""}`;
}

async function send(path, { method = "GET", body, query, token, signal } = {}) {
  const headers = { Accept: "application/json" };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (token) headers.Authorization = `Bearer ${token}`;
  let response;
  try {
    response = await fetch(url(path, query), {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      signal,
    });
  } catch (error) {
    if (error?.name === "AbortError") throw error;
    throw networkError();
  }
  const data = await parse(response);
  if (!response.ok) throw toError(response, data);
  return data;
}

// One refresh at a time: concurrent 401s wait for the same exchange, so a rotating refresh
// token is never spent twice.
let refreshing = null;

function refreshSession() {
  if (!refreshing) {
    refreshing = (async () => {
      const refreshToken = getRefreshToken();
      if (!refreshToken) throw new ApiError(401, "invalid_token", "Session expirée. Connectez-vous à nouveau.");
      try {
        const session = await send("/auth/refresh", { method: "POST", body: { refresh_token: refreshToken } });
        saveSession(session);
        return session.access_token;
      } catch (error) {
        // A refresh token the server rejects is final. A network or server failure is not: keep
        // the session so the user is not logged out by an outage, and let the caller show the error.
        if (error instanceof ApiError && error.status >= 400 && error.status < 500) expireSession();
        throw error;
      }
    })().finally(() => {
      refreshing = null;
    });
  }
  return refreshing;
}

/**
 * Authenticated request. On 401 "invalid_token" it renews the session once and retries once; it
 * never loops. If renewal is rejected the session is cleared and the caller sees the 401.
 */
export async function request(path, options = {}) {
  const token = getAccessToken();
  try {
    return await send(path, { ...options, token });
  } catch (error) {
    if (!(error instanceof ApiError) || error.status !== 401 || error.code !== "invalid_token") throw error;
    if (!getRefreshToken()) {
      expireSession();
      throw error;
    }
    const fresh = await refreshSession();
    return send(path, { ...options, token: fresh });
  }
}

// ---------------------------------------------------------------- authentication
export async function login(email, password) {
  const session = await send("/auth/login", { method: "POST", body: { email, password } });
  saveSession(session);
  return session.user;
}

export function logout() {
  clearSession();
}

/** The signed-in user as the server sees them (role comes from here, never from the browser). */
export function getMe(signal) {
  return request("/me", { signal });
}
