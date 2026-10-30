import { Link, NavLink, Outlet, useNavigate } from "react-router";
import { useAuth } from "../../auth/AuthContext";
import { homeFor } from "../../auth/roles";

export default function AppLayout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const linkClasses = ({ isActive }) =>
    `rounded-lg px-4 py-2 text-sm font-medium transition ${
      isActive
        ? "bg-blue-50 text-blue-700"
        : "text-slate-600 hover:bg-slate-100 hover:text-slate-900"
    }`;

  function signOut() {
    logout();
    navigate("/login", { replace: true });
  }

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">

      <header className="sticky top-0 z-10 border-b border-slate-200 bg-white/95 backdrop-blur">
        <nav className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-4 px-6 py-4">

          <Link
            to={homeFor(user.role) ?? "/"}
            className="text-xl font-bold tracking-tight text-blue-700"
          >
            PulseCare
          </Link>

          <div className="flex flex-wrap items-center gap-2">

            {user.role === "patient" && (
              <NavLink to="/patient" className={linkClasses}>
                Patient
              </NavLink>
            )}

            {user.role === "doctor" && (
              <NavLink to="/doctor" className={linkClasses}>
                Médecin
              </NavLink>
            )}

            <NavLink to="/profile" className={linkClasses}>
              Profil
            </NavLink>

            <span className="ml-2 hidden text-sm text-slate-500 sm:inline">{user.full_name}</span>
            <button
              type="button"
              onClick={signOut}
              className="rounded-lg px-4 py-2 text-sm font-medium text-slate-600 transition hover:bg-slate-100 hover:text-slate-900"
            >
              Déconnexion
            </button>

          </div>

        </nav>
      </header>

      <main className="mx-auto w-full max-w-7xl px-5 py-8 sm:px-8 sm:py-10">
        <Outlet />
      </main>

      <footer className="border-t border-slate-200 bg-white px-6 py-5 text-center text-sm text-slate-500">
        PulseCare · Plateforme de suivi de la tension artérielle
      </footer>

    </div>
  );
}
