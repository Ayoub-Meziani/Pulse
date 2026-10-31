import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router";
import { getEmergencyConfig } from "../../api/patient";
import { useAuth } from "../../auth/AuthContext";
import { homeFor, NAV, ROLE_LABEL } from "../../auth/roles";
import { initials } from "../../lib/format";
import { cacheConfig, readCachedConfig } from "../../lib/offlineCache";
import { useDialog } from "../../lib/useDialog";
import { useResource } from "../../lib/useResource";
import DoctorAlertFlag from "../alerts/DoctorAlertFlag";
import PatientAlertFlag from "../alerts/PatientAlertFlag";
import Icon from "../ui/Icon";
import Logo from "../ui/Logo";

const URGENCE = "btn-shine bg-linear-to-br from-emergency to-alarm-2 font-semibold text-white shadow-glow-alarm";

function NavItems({ items, onNavigate }) {
  return (
    <ul className="space-y-1">
      {items.map((item) => (
        <li key={item.to}>
          <NavLink
            to={item.to}
            end={item.end}
            onClick={onNavigate}
            className={({ isActive }) =>
              `relative flex min-h-11 items-center gap-3 rounded-xl px-3.5 text-sm transition-colors before:absolute
                before:inset-y-2.5 before:left-0 before:w-1 before:rounded-full before:bg-glow before:transition-transform
                before:duration-300 before:ease-(--ease-out-expo) ${
                isActive ? "bg-white/10 font-semibold text-white before:scale-y-100"
                  : "font-medium text-white/75 before:scale-y-0 hover:bg-white/8 hover:text-white"
              }`}
          >
            <Icon name={item.icon} size={19} />
            {item.label}
          </NavLink>
        </li>
      ))}
    </ul>
  );
}

function UserBlock({ user, onSignOut }) {
  return (
    <div className="flex items-center gap-3 border-t border-white/10 pt-4">
      <span className="flex h-10 w-10 items-center justify-center rounded-full bg-white/15 text-sm font-semibold text-white">
        {initials(user.full_name)}
      </span>
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-semibold text-white">{user.full_name}</p>
        <p className="text-xs text-white/60">{ROLE_LABEL[user.role] ?? user.role}</p>
      </div>
      <button type="button" onClick={onSignOut} title="Se déconnecter" aria-label="Se déconnecter"
        className="flex min-h-11 min-w-11 items-center justify-center rounded-lg text-white/70 hover:bg-white/10 hover:text-white">
        <Icon name="logout" size={18} />
      </button>
    </div>
  );
}

function SidebarContent({ user, items, onNavigate, onSignOut }) {
  return (
    <div className="flex h-full flex-col gap-6 overflow-y-auto p-5">
      {/* Decorative aurora; the parent is `isolate`, so -z-10 keeps it under the content. */}
      <div aria-hidden="true"
        className="pointer-events-none absolute -left-20 top-1/3 -z-10 h-72 w-72 animate-float rounded-full bg-glow/20 blur-3xl" />
      <Link to={homeFor(user.role) ?? "/"} onClick={onNavigate} className="px-1"><Logo inverse animated /></Link>
      <nav aria-label="Navigation principale" className="flex-1"><NavItems items={items} onNavigate={onNavigate} /></nav>
      {user.role === "patient" && (
        <Link to="/patient/urgence" onClick={onNavigate}
          className={`flex min-h-11 items-center justify-center gap-2 rounded-xl px-4 ${URGENCE}`}>
          <Icon name="phone" size={18} /> Urgence
        </Link>
      )}
      <UserBlock user={user} onSignOut={onSignOut} />
    </div>
  );
}

/** Mobile menu: portalled modal (inert page, Escape closes, focus comes back to the menu button). */
function Drawer({ onClose, children }) {
  const ref = useRef(null);
  useDialog(ref, true, onClose);
  return createPortal(
    <div ref={ref} tabIndex={-1} className="fixed inset-0 z-40 focus:outline-none lg:hidden" role="dialog" aria-modal="true" aria-label="Menu">
      <button type="button" className="absolute inset-0 animate-fade-in bg-night/60" aria-label="Fermer le menu" onClick={onClose} />
      <div className="absolute inset-y-0 left-0 isolate w-72 max-w-[85vw] animate-drawer-in overflow-hidden bg-linear-to-b from-night to-night-2 shadow-xl">
        <button type="button" onClick={onClose} aria-label="Fermer le menu" data-autofocus
          className="absolute right-3 top-3 z-10 flex min-h-11 min-w-11 items-center justify-center rounded-lg text-white/80 hover:bg-white/10">
          <Icon name="close" />
        </button>
        {children}
      </div>
    </div>,
    document.body,
  );
}

export default function AppLayout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [open, setOpen] = useState(false);
  // Cached for the offline emergency screen; the cached copy also keeps the demo banner when offline.
  const config = useResource((s) => getEmergencyConfig({ signal: s }).then((c) => { cacheConfig(c); return c; }), "config");
  const emergencyConfig = config.data ?? readCachedConfig();
  const items = NAV[user.role] ?? [];

  // The drawer is lg:hidden: close it when the screen grows, or the page would stay inert behind it.
  useEffect(() => {
    const wide = window.matchMedia("(min-width: 64rem)");
    const close = () => wide.matches && setOpen(false);
    wide.addEventListener("change", close);
    return () => wide.removeEventListener("change", close);
  }, []);

  function signOut() {
    logout();
    navigate("/login", { replace: true });
  }

  return (
    <div className="min-h-screen lg:pl-64">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:left-3 focus:top-3 focus:z-50 focus:rounded-lg focus:bg-surface focus:px-3 focus:py-2">
        Aller au contenu
      </a>

      <aside className="fixed inset-y-0 left-0 z-30 isolate hidden w-64 overflow-hidden bg-linear-to-b from-night to-night-2 lg:block">
        <SidebarContent user={user} items={items} onSignOut={signOut} />
      </aside>

      {/* Mobile and tablet: top bar, emergency always one tap away, menu in a drawer. */}
      <header className="glass sticky top-0 z-20 flex h-16 items-center gap-3 px-4 shadow-[0_1px_0_rgb(15_23_42/0.08)] lg:hidden">
        <button type="button" onClick={() => setOpen(true)} aria-label="Ouvrir le menu" aria-expanded={open}
          className="flex min-h-11 min-w-11 items-center justify-center rounded-lg text-ink hover:bg-surface-muted">
          <Icon name="menu" />
        </button>
        <Link to={homeFor(user.role) ?? "/"} className="min-w-0 flex-1"><Logo size={28} /></Link>
        {user.role === "patient" && (
          <Link to="/patient/urgence"
            className={`inline-flex min-h-11 items-center gap-1.5 rounded-xl px-3 text-sm ${URGENCE}`}>
            <Icon name="phone" size={16} /> Urgence
          </Link>
        )}
      </header>

      {open && (
        <Drawer onClose={() => setOpen(false)}>
          <SidebarContent user={user} items={items} onNavigate={() => setOpen(false)} onSignOut={signOut} />
        </Drawer>
      )}

      {emergencyConfig?.demo_mode && (
        <div className="flex items-center justify-center gap-2 border-b border-dashed border-sim/50 bg-sim-soft px-4 py-2 text-center text-xs font-semibold text-sim sm:text-sm">
          <Icon name="flask" size={16} />
          <span>Environnement de démonstration — comptes et données fictifs. Le bouton d'appel compose le numéro d'un membre de l'équipe.</span>
        </div>
      )}

      <main id="main" tabIndex={-1} className="mx-auto w-full max-w-6xl px-4 py-6 focus:outline-none sm:px-6 sm:py-8 lg:px-8">
        {/* Severe and emergency alerts stay on top of every page until the doctor resolves them. They stay outside
            the route wrapper so they never remount (and never restart the beep) on navigation. */}
        {user.role === "patient" && <PatientAlertFlag user={user} config={emergencyConfig} />}
        {user.role === "doctor" && <DoctorAlertFlag user={user} />}
        <div key={location.pathname} className="animate-page-in">
          <Outlet />
        </div>
      </main>

      <footer className="mx-auto max-w-6xl px-4 pb-8 text-xs text-ink-subtle sm:px-6 lg:px-8">
        PULSE est un prototype de suivi de la tension artérielle. Il ne pose pas de diagnostic et ne remplace pas un
        professionnel de santé. En cas d'urgence, appelez les secours.
      </footer>
    </div>
  );
}
