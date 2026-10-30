// Session and refresh behaviour of api/client.js against the backend's real contract:
// POST /auth/login and /auth/refresh -> SessionOut, 401 "invalid_token" for an expired access token.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const USER = { id: "11111111-1111-4111-8111-111111111111", role: "patient", full_name: "Test", email: "t@pulse.test", timezone: "Africa/Algiers" };

function session(n) {
  return { access_token: `access-${n}`, refresh_token: `refresh-${n}`, expires_at: "2099-01-01T00:00:00Z", token_type: "bearer", user: USER };
}

function reply(status, body) {
  return Promise.resolve(new Response(body === undefined ? null : JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  }));
}

const expired = () => reply(401, { error: { code: "invalid_token", message: "Session is invalid or expired. Log in again.", details: null } });

function memoryStorage(initial = {}) {
  const data = new Map(Object.entries(initial));
  return {
    getItem: (k) => (data.has(k) ? data.get(k) : null),
    setItem: (k, v) => void data.set(k, String(v)),
    removeItem: (k) => void data.delete(k),
    has: (k) => data.has(k),
  };
}

let storage;
let calls;

async function load(initialStorage = {}) {
  storage = memoryStorage(initialStorage);
  vi.stubGlobal("sessionStorage", storage);
  vi.resetModules();
  return import("./client.js");
}

function mockFetch(handler) {
  calls = [];
  vi.stubGlobal("fetch", vi.fn((url, init = {}) => {
    const call = { url, method: init.method ?? "GET", auth: init.headers?.Authorization, body: init.body ? JSON.parse(init.body) : undefined };
    calls.push(call);
    return handler(call);
  }));
}

const signedIn = { "pulse.access_token": "access-1", "pulse.refresh_token": "refresh-1" };

beforeEach(() => {
  vi.spyOn(console, "log");
  vi.spyOn(console, "error");
  vi.spyOn(console, "warn");
});

afterEach(() => {
  // Credentials, tokens and patient data are never logged.
  for (const spy of [console.log, console.error, console.warn]) expect(spy).not.toHaveBeenCalled();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("login", () => {
  it("posts the credentials to /api/v1/auth/login without a token and stores the session", async () => {
    const client = await load();
    mockFetch(() => reply(200, session(1)));
    const user = await client.login("a@pulse.test", "secret");
    expect(user).toEqual(USER);
    expect(calls).toEqual([{ url: "/api/v1/auth/login", method: "POST", auth: undefined, body: { email: "a@pulse.test", password: "secret" } }]);
    expect(storage.getItem("pulse.access_token")).toBe("access-1");
    expect(storage.getItem("pulse.refresh_token")).toBe("refresh-1");
  });

  it("surfaces invalid credentials as a typed error and stores nothing", async () => {
    const client = await load();
    mockFetch(() => reply(401, { error: { code: "invalid_credentials", message: "Email or password is incorrect.", details: null } }));
    await expect(client.login("a@pulse.test", "wrong")).rejects.toMatchObject({ name: "ApiError", status: 401, code: "invalid_credentials" });
    expect(client.hasSession()).toBe(false);
    expect(storage.has("pulse.access_token")).toBe(false);
  });

  it("reports an unreachable server as network_error", async () => {
    const client = await load();
    mockFetch(() => Promise.reject(new TypeError("Failed to fetch")));
    await expect(client.login("a@pulse.test", "x")).rejects.toMatchObject({ status: 0, code: "network_error" });
  });
});

describe("authenticated requests", () => {
  it("sends the stored bearer token with query parameters", async () => {
    const client = await load(signedIn);
    mockFetch(() => reply(200, []));
    await client.request("/patients/p1/alerts", { query: { status: "active", skip: undefined } });
    expect(calls).toEqual([{ url: "/api/v1/patients/p1/alerts?status=active", method: "GET", auth: "Bearer access-1", body: undefined }]);
  });

  it("restores the session after a page reload from sessionStorage and asks /me for the user", async () => {
    const client = await load(signedIn);
    expect(client.hasSession()).toBe(true);
    mockFetch(() => reply(200, USER));
    await expect(client.getMe()).resolves.toEqual(USER);
    expect(calls[0]).toMatchObject({ url: "/api/v1/me", auth: "Bearer access-1" });
  });

  it("turns the API error body into an ApiError", async () => {
    const client = await load(signedIn);
    mockFetch(() => reply(403, { error: { code: "forbidden", message: "Not allowed.", details: [{ field: "x" }] } }));
    await expect(client.request("/patients/p/summary")).rejects.toMatchObject({ status: 403, code: "forbidden", message: "Not allowed.", details: [{ field: "x" }] });
  });

  it("does not try to refresh a 401 that is not an expired token", async () => {
    const client = await load(signedIn);
    mockFetch(() => reply(401, { error: { code: "not_authenticated", message: "Log in first.", details: null } }));
    await expect(client.request("/me")).rejects.toMatchObject({ code: "not_authenticated" });
    expect(calls).toHaveLength(1);
  });
});

describe("token refresh", () => {
  it("renews an expired access token once, retries the request and stores the rotated refresh token", async () => {
    const client = await load(signedIn);
    mockFetch((call) => {
      if (call.url.endsWith("/auth/refresh")) return reply(200, session(2));
      return call.auth === "Bearer access-1" ? expired() : reply(200, USER);
    });
    await expect(client.request("/me")).resolves.toEqual(USER);
    expect(calls.map((c) => [c.url, c.auth, c.body])).toEqual([
      ["/api/v1/me", "Bearer access-1", undefined],
      ["/api/v1/auth/refresh", undefined, { refresh_token: "refresh-1" }],
      ["/api/v1/me", "Bearer access-2", undefined],
    ]);
    expect(storage.getItem("pulse.access_token")).toBe("access-2");
    expect(storage.getItem("pulse.refresh_token")).toBe("refresh-2");
  });

  it("shares one refresh between concurrent requests", async () => {
    const client = await load(signedIn);
    mockFetch(async (call) => {
      if (call.url.endsWith("/auth/refresh")) {
        await new Promise((r) => setTimeout(r, 10));
        return reply(200, session(2));
      }
      return call.auth === "Bearer access-1" ? expired() : reply(200, []);
    });
    await Promise.all([client.request("/a"), client.request("/b"), client.request("/c")]);
    expect(calls.filter((c) => c.url.endsWith("/auth/refresh"))).toHaveLength(1);
  });

  it("clears the session and signals expiry when the refresh token is rejected", async () => {
    const client = await load(signedIn);
    const expiredListener = vi.fn();
    client.onSessionExpired(expiredListener);
    mockFetch((call) => (call.url.endsWith("/auth/refresh")
      ? reply(401, { error: { code: "invalid_token", message: "Session expired. Log in again.", details: null } })
      : expired()));
    await expect(client.request("/me")).rejects.toMatchObject({ status: 401, code: "invalid_token" });
    expect(expiredListener).toHaveBeenCalledTimes(1);
    expect(client.hasSession()).toBe(false);
    expect(storage.has("pulse.access_token")).toBe(false);
    expect(storage.has("pulse.refresh_token")).toBe(false);
    expect(calls).toHaveLength(2); // original + one refresh: no loop
  });

  it("never refreshes twice for one request, even if the retry is still rejected", async () => {
    const client = await load(signedIn);
    mockFetch((call) => (call.url.endsWith("/auth/refresh") ? reply(200, session(2)) : expired()));
    await expect(client.request("/me")).rejects.toMatchObject({ status: 401, code: "invalid_token" });
    expect(calls.map((c) => c.url)).toEqual(["/api/v1/me", "/api/v1/auth/refresh", "/api/v1/me"]);
  });

  it("keeps the session when the refresh fails because the server is down", async () => {
    const client = await load(signedIn);
    const expiredListener = vi.fn();
    client.onSessionExpired(expiredListener);
    mockFetch((call) => (call.url.endsWith("/auth/refresh")
      ? reply(503, { error: { code: "auth_unavailable", message: "Authentication service is unavailable.", details: null } })
      : expired()));
    await expect(client.request("/me")).rejects.toMatchObject({ status: 503, code: "auth_unavailable" });
    expect(expiredListener).not.toHaveBeenCalled();
    expect(client.hasSession()).toBe(true);
  });

  it("requires login when an access token expires and there is no refresh token", async () => {
    const client = await load({ "pulse.access_token": "access-1" });
    const expiredListener = vi.fn();
    client.onSessionExpired(expiredListener);
    mockFetch(() => expired());
    await expect(client.request("/me")).rejects.toMatchObject({ code: "invalid_token" });
    expect(expiredListener).toHaveBeenCalledTimes(1);
    expect(client.hasSession()).toBe(false);
    expect(calls).toHaveLength(1);
  });
});

describe("logout", () => {
  it("clears local tokens without calling the server (the contract has no logout endpoint)", async () => {
    const client = await load(signedIn);
    mockFetch(() => reply(200, {}));
    client.logout();
    expect(client.hasSession()).toBe(false);
    expect(storage.has("pulse.access_token")).toBe(false);
    expect(storage.has("pulse.refresh_token")).toBe(false);
    expect(calls).toHaveLength(0);
  });
});
