import { useCallback, useEffect, useState } from "react";

/**
 * One API read: { status: "loading" | "ok" | "error", data, error, retry, reload }.
 * `load(signal)` must call the API client. An answer for an older request is ignored, so a quick
 * retry or a changed key never shows stale data. `key` re-runs the request when it changes.
 */
export function useResource(load, key) {
  const [attempt, setAttempt] = useState(0);
  const token = `${key}:${attempt}`;
  const [result, setResult] = useState({ token: null, status: "loading", data: null, error: null });

  useEffect(() => {
    const controller = new AbortController();
    load(controller.signal)
      .then((data) => setResult({ token, status: "ok", data, error: null }))
      .catch((error) => {
        if (error?.name !== "AbortError") setResult({ token, status: "error", data: null, error });
      });
    return () => controller.abort();
    // `load` is expected to change with `key`; the token covers both.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  const retry = useCallback(() => setAttempt((n) => n + 1), []);
  const current = result.token === token ? result : { status: "loading", data: null, error: null };
  return { ...current, retry, reload: retry };
}
