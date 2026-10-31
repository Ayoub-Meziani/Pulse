import { useCallback, useEffect, useState } from "react";

/**
 * One API read: { status: "loading" | "ok" | "error", data, error, last, refreshing, retry, reload }.
 * `load(signal)` must call the API client. An answer for an older request is ignored, so a quick
 * retry or a changed key never shows stale data. `key` re-runs the request when it changes.
 * `last` is the last good data of this key, kept after a failed reload (null otherwise): showing it is the caller's choice.
 */
export function useResource(load, key) {
  const [attempt, setAttempt] = useState(0);
  const token = `${key}:${attempt}`;
  const [result, setResult] = useState({ token: null, status: "loading", data: null, error: null, last: null });

  useEffect(() => {
    const controller = new AbortController();
    load(controller.signal)
      .then((data) => setResult({ token, key, status: "ok", data, error: null, last: data }))
      .catch((error) => {
        if (error?.name !== "AbortError") {
          setResult((prev) => ({ token, key, status: "error", data: null, error, last: prev.key === key ? prev.last : null }));
        }
      });
    return () => controller.abort();
    // `load` is expected to change with `key`; the token covers both.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  const retry = useCallback(() => setAttempt((n) => n + 1), []);
  // A reload of the same key keeps showing the data already on screen (no flash) until the new answer arrives.
  const current = result.token === token ? result
    : result.key === key && result.status === "ok" ? { ...result, refreshing: true }
      : { status: "loading", data: null, error: null, last: result.key === key ? result.last : null };
  return { ...current, retry, reload: retry };
}
