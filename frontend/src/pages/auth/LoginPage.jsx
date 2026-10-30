import { useState } from "react";
import { Navigate, useLocation, useNavigate } from "react-router";
import { ApiError } from "../../api/client";
import { useAuth } from "../../auth/AuthContext";
import { homeFor } from "../../auth/roles";
import Logo from "../../components/ui/Logo";

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

  const input = "mt-1.5 block w-full rounded-xl border border-line bg-surface px-3.5 py-2.5 text-ink outline-none focus:border-brand focus:ring-2 focus:ring-brand/20";
  return (
    <div className="grid min-h-screen lg:grid-cols-2">
      <aside className="hidden flex-col justify-between bg-navy p-10 text-white lg:flex">
        <Logo inverse size={36} />
        <div className="max-w-md">
          <h2 className="text-3xl font-bold leading-tight">Suivi de la tension artérielle, entre deux consultations.</h2>
          <p className="mt-4 text-white/75">
            Le patient saisit ses mesures et ses symptômes ; des règles de sécurité fixes lui indiquent la conduite à
            tenir, et son médecin suit l'évolution. Un bracelet est facultatif.
          </p>
        </div>
        <p className="text-xs text-white/60">Prototype — ne pose pas de diagnostic et ne remplace pas un professionnel de santé.</p>
      </aside>
      <main className="flex items-center justify-center px-5 py-10">
        <form onSubmit={submit} className="w-full max-w-sm" aria-labelledby="login-title">
          <div className="lg:hidden"><Logo size={36} /></div>
          <h1 id="login-title" className="mt-8 text-2xl font-bold text-ink lg:mt-0">Connexion</h1>
          <p className="mt-1 text-sm text-ink-muted">Accès réservé aux patients et médecins inscrits.</p>

          <label className="mt-6 block text-sm font-medium text-ink" htmlFor="email">Email</label>
          <input id="email" type="email" autoComplete="username" required value={email}
            onChange={(e) => setEmail(e.target.value)} className={input} />

          <label className="mt-4 block text-sm font-medium text-ink" htmlFor="password">Mot de passe</label>
          <input id="password" type="password" autoComplete="current-password" required value={password}
            onChange={(e) => setPassword(e.target.value)} className={input} />

          {error && <p role="alert" className="mt-4 rounded-xl bg-danger-soft px-3.5 py-2.5 text-sm text-danger">{error}</p>}

          <button type="submit" disabled={busy}
            className="mt-6 min-h-11 w-full rounded-xl bg-brand px-4 py-2.5 font-semibold text-white transition-colors hover:bg-brand-hover disabled:opacity-60">
            {busy ? "Connexion…" : "Se connecter"}
          </button>
          <p className="mt-6 text-xs text-ink-subtle">En cas d'urgence, n'attendez pas : appelez directement les secours.</p>
        </form>
      </main>
    </div>
  );
}
