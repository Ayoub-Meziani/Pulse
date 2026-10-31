import { useState } from "react";
import { Navigate, useLocation, useNavigate } from "react-router";
import { ApiError } from "../../api/client";
import { useAuth } from "../../auth/AuthContext";
import { homeFor } from "../../auth/roles";
import Button from "../../components/ui/Button";
import { Card } from "../../components/ui/Card";
import Icon from "../../components/ui/Icon";
import Logo from "../../components/ui/Logo";

// Three points of the description above, as short bullets (no figures: decoration never looks like data).
const FEATURES = [
  ["pulse", "Le patient saisit ses mesures et ses symptômes"],
  ["shield", "Des règles de sécurité fixes indiquent la conduite à tenir"],
  ["users", "Le médecin suit l'évolution ; un bracelet est facultatif"],
];
const ECG = "M0 34h110l8-6 8 6h22l7 10 11-40 12 48 7-18h40l10-7 10 7h95l8-6 8 6h22l7 10 11-40 12 48 7-18h40l10-7 10 7h125";

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
    <div className="grid min-h-screen lg:grid-cols-[1.1fr_1fr]">
      <aside className="relative isolate flex flex-col justify-between gap-8 overflow-hidden bg-linear-to-br from-night via-night-2 to-night px-6 py-8 text-white sm:px-10 lg:p-12">
        <span aria-hidden="true" className="pointer-events-none absolute -left-24 -top-24 -z-10 h-80 w-80 animate-float rounded-full bg-brand/45 blur-3xl" />
        <span aria-hidden="true" className="pointer-events-none absolute -bottom-32 -right-20 -z-10 h-96 w-96 animate-float rounded-full bg-glow/25 blur-3xl [animation-delay:-9s]" />
        <Logo inverse size={36} animated />
        <div className="max-w-lg animate-fade-up">
          <h2 className="text-2xl font-extrabold leading-tight tracking-tight sm:text-4xl">
            Suivi de la tension artérielle, <span className="text-glow">entre deux consultations.</span>
          </h2>
          <p className="mt-4 hidden text-white/75 sm:block">
            Le patient saisit ses mesures et ses symptômes ; des règles de sécurité fixes lui indiquent la conduite à
            tenir, et son médecin suit l'évolution. Un bracelet est facultatif.
          </p>
          <ul className="stagger mt-6 hidden space-y-3 sm:block">
            {FEATURES.map(([icon, text]) => (
              <li key={icon} className="flex items-center gap-3 text-sm text-white/85">
                <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-white/10 text-glow"><Icon name={icon} size={18} /></span>
                {text}
              </li>
            ))}
          </ul>
        </div>
        {/* Decoration only: an ECG motif, never a reading. */}
        <svg viewBox="0 0 600 60" className="h-auto w-full text-glow" aria-hidden="true" focusable="false">
          <path d={ECG} fill="none" stroke="currentColor" strokeOpacity="0.15" strokeWidth="2" strokeLinejoin="round" />
          <path d={ECG} fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"
            pathLength="100" strokeDasharray="100" className="animate-ecg" />
        </svg>
        <p className="text-xs text-white/60">Prototype — ne pose pas de diagnostic et ne remplace pas un professionnel de santé.</p>
      </aside>
      <main className="flex items-center justify-center px-4 py-10 sm:px-5">
        <Card as="form" variant="glass" onSubmit={submit} className="w-full max-w-sm animate-scale-in p-6 shadow-lift sm:p-8" aria-labelledby="login-title">
          <h1 id="login-title" className="text-2xl font-extrabold tracking-tight text-ink">Connexion</h1>
          <p className="mt-1 text-sm text-ink-muted">Accès réservé aux patients et médecins inscrits.</p>

          <label className="mt-6 block text-sm font-medium text-ink" htmlFor="email">Email</label>
          <input id="email" type="email" autoComplete="username" required value={email}
            onChange={(e) => setEmail(e.target.value)} className="field mt-1.5" />

          <label className="mt-4 block text-sm font-medium text-ink" htmlFor="password">Mot de passe</label>
          <input id="password" type="password" autoComplete="current-password" required value={password}
            onChange={(e) => setPassword(e.target.value)} className="field mt-1.5" />

          {error && <p role="alert" className="mt-4 flex gap-2 rounded-xl bg-danger-soft px-3.5 py-2.5 text-sm text-danger"><Icon name="alert" size={18} className="shrink-0" />{error}</p>}

          <Button type="submit" disabled={busy} className="mt-6 w-full">
            {busy ? "Connexion…" : "Se connecter"}
          </Button>
          <p className="mt-6 text-xs text-ink-subtle">En cas d'urgence, n'attendez pas : appelez directement les secours.</p>
        </Card>
      </main>
    </div>
  );
}
