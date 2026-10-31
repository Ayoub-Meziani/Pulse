import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { getMe, hasSession, login as apiLogin, logout as apiLogout, onSessionExpired } from "../api/client";
import { alertSound } from "../lib/alertSound";
import { clearOfflineCache } from "../lib/offlineCache";

const AuthContext = createContext(null);

// status: "loading" (checking a stored session) | "authenticated" | "anonymous".
// The user, and above all the role, only ever come from the server's /me answer.
export function AuthProvider({ children }) {
  const [state, setState] = useState({ status: hasSession() ? "loading" : "anonymous", user: null });

  useEffect(() => {
    if (!hasSession()) return undefined;
    const controller = new AbortController();
    getMe(controller.signal)
      .then((user) => setState({ status: "authenticated", user }))
      .catch((error) => {
        if (error?.name === "AbortError") return;
        // A 401 already cleared the session. After an outage we cannot tell who this is, so the
        // login page is shown; the stored tokens stay and the next page load checks them again.
        setState({ status: "anonymous", user: null });
      });
    return () => controller.abort();
  }, []);

  useEffect(
    () => onSessionExpired(() => setState({ status: "anonymous", user: null })),
    [],
  );

  const login = useCallback(async (email, password) => {
    await apiLogin(email, password);
    try {
      const user = await getMe();
      setState({ status: "authenticated", user });
      return user;
    } catch (error) {
      apiLogout();
      throw error;
    }
  }, []);

  const logout = useCallback(() => {
    apiLogout();
    clearOfflineCache();  // emergency card, config and unsent incident steps leave the device with the session
    alertSound.reset();   // silence, and the next person does not inherit this session's mute
    setState({ status: "anonymous", user: null });
  }, []);

  const value = useMemo(() => ({ ...state, login, logout }), [state, login, logout]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

// eslint-disable-next-line react-refresh/only-export-components
export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside <AuthProvider>");
  return value;
}
