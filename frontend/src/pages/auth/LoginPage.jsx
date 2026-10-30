import { useState } from "react";
import { Navigate, useLocation, useNavigate } from "react-router";
import { ApiError } from "../../api/client";
import { useAuth } from "../../auth/AuthContext";
import { homeFor } from "../../auth/roles";

function loginMessage(error) {
  if (!(error instanceof ApiError)) return "Erreur inattendue. Réessayez.";
  if (error.code === "invalid_credentials") return "Email ou mot de passe incorrect.";
  if (error.code === "network_error") return error.message;
  if (error.status === 503) return "Le service de connexion est indisponible. Réessayez dans un instant.";
  if (error.status === 422) return "Saisissez un email et un mot de passe.";
  return "Connexion impossible. Réessayez.";
}

// Only same-site paths are honoured after login (no open redirect).
function safeTarget(from) {
  return typeof from === "string" && from.startsWith("/") && !from.startsWith("//") && from !== "/login"
    ? from
    : null;
}

export default function LoginPage() {
  const { status, user, login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  if (status === "authenticated") {
    return <Navigate to={homeFor(user.role) ?? "/"} replace />;
  }

  async function submit(event) {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      const signedIn = await login(email.trim(), password);
      navigate(safeTarget(location.state?.from) ?? homeFor(signedIn.role) ?? "/", { replace: true });
    } catch (e) {
      setPassword("");
      setError(loginMessage(e));
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50 px-5">
      <form
        onSubmit={submit}
        className="w-full max-w-sm rounded-2xl border border-slate-200 bg-white p-8 shadow-sm"
        aria-labelledby="login-title"
      >
        <p className="text-xl font-bold tracking-tight text-blue-700">PulseCare</p>
        <h1 id="login-title" className="mt-4 text-2xl font-bold text-slate-900">Connexion</h1>

        <label className="mt-6 block text-sm font-medium text-slate-700" htmlFor="email">Email</label>
        <input
          id="email"
          type="email"
          autoComplete="username"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-slate-900 focus:border-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-200"
        />

        <label className="mt-4 block text-sm font-medium text-slate-700" htmlFor="password">Mot de passe</label>
        <input
          id="password"
          type="password"
          autoComplete="current-password"
          required
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-slate-900 focus:border-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-200"
        />

        {error && (
          <p role="alert" className="mt-4 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-800">{error}</p>
        )}

        <button
          type="submit"
          disabled={busy}
          className="mt-6 w-full rounded-lg bg-blue-700 px-4 py-2.5 font-medium text-white transition hover:bg-blue-800 disabled:opacity-60"
        >
          {busy ? "Connexion…" : "Se connecter"}
        </button>
      </form>
    </div>
  );
}
