import { Link, Navigate, Outlet, useLocation } from "react-router";
import { useAuth } from "./AuthContext";
import { homeFor } from "./roles";

/**
 * Renders its children (or the nested routes) only for a signed-in user whose server-side role is
 * listed. Nothing of the protected page is rendered while the session is being checked.
 */
export default function RequireRole({ roles, children }) {
  const { status, user } = useAuth();
  const location = useLocation();

  if (status === "loading") {
    return (
      <div className="flex min-h-screen items-center justify-center bg-canvas text-ink-muted" role="status">
        Vérification de la session…
      </div>
    );
  }
  if (status !== "authenticated") {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }
  if (!roles.includes(user.role)) {
    const home = homeFor(user.role);
    return (
      <section className="mx-auto mt-16 max-w-md rounded-2xl border border-line bg-surface p-8 text-center" role="alert">
        <h1 className="text-xl font-bold text-ink">Accès refusé</h1>
        <p className="mt-2 text-ink-muted">Votre compte n'a pas accès à cette page.</p>
        {home && (
          <Link to={home} className="mt-4 inline-block text-sm font-semibold text-brand">
            Retour à mon espace
          </Link>
        )}
      </section>
    );
  }
  return children ?? <Outlet />;
}
