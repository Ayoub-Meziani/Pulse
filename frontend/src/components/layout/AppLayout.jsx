import { useState } from "react";
import EscalationBanner from "../doctor/EscalationBanner";
import { Link, NavLink, Outlet, useNavigate } from "react-router";
import { getEmergencyConfig } from "../../api/patient";
import { useAuth } from "../../auth/AuthContext";
import { homeFor, NAV, ROLE_LABEL } from "../../auth/roles";
import { initials } from "../../lib/format";
import { useResource } from "../../lib/useResource";
import Icon from "../ui/Icon";
import Logo from "../ui/Logo";

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
              `flex min-h-11 items-center gap-3 rounded-xl px-3.5 text-sm font-medium transition-colors ${
                isActive ? "bg-white/12 text-white" : "text-white/75 hover:bg-white/8 hover:text-white"
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
        className="rounded-lg p-2 text-white/70 hover:bg-white/10 hover:text-white">
        <Icon name="logout" size={18} />
      </button>
    </div>
  );
}

function SidebarContent({ user, items, onNavigate, onSignOut }) {
  return (
    <div className="flex h-full flex-col gap-6 p-5">
      <Link to={homeFor(user.role) ?? "/"} onClick={onNavigate} className="px-1"><Logo inverse /></Link>
      <nav aria-label="Navigation principale" className="flex-1"><NavItems items={items} onNavigate={onNavigate} /></nav>
      {user.role === "patient" && (
        <Link to="/patient/urgence" onClick={onNavigate}
          className="flex min-h-11 items-center justify-center gap-2 rounded-xl bg-emergency px-4 font-semibold text-white hover:bg-emergency-hover">
          <Icon name="phone" size={18} /> Urgence
        </Link>
      )}
      <UserBlock user={user} onSignOut={onSignOut} />
    </div>
  );
}

export default function AppLayout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const config = useResource((signal) => getEmergencyConfig({ signal }), "config");
  const items = NAV[user.role] ?? [];


  function signOut() {
    logout();
    navigate("/login", { replace: true });
  }

  return (
    <div className="min-h-screen lg:pl-64">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:left-3 focus:top-3 focus:z-50 focus:rounded-lg focus:bg-surface focus:px-3 focus:py-2">
        Aller au contenu
      </a>

      <aside className="fixed inset-y-0 left-0 z-30 hidden w-64 bg-navy lg:block">
        <SidebarContent user={user} items={items} onSignOut={signOut} />
      </aside>

      {/* Mobile and tablet: top bar, emergency always one tap away, menu in a drawer. */}
      <header className="sticky top-0 z-20 flex items-center gap-3 border-b border-line bg-surface/95 px-4 py-3 backdrop-blur lg:hidden">
        <button type="button" onClick={() => setOpen(true)} aria-label="Ouvrir le menu" aria-expanded={open}
          className="rounded-lg p-2 text-ink hover:bg-surface-muted">
          <Icon name="menu" />
        </button>
        <Link to={homeFor(user.role) ?? "/"} className="min-w-0 flex-1"><Logo size={28} /></Link>
        {user.role === "patient" && (
          <Link to="/patient/urgence"
            className="inline-flex min-h-10 items-center gap-1.5 rounded-xl bg-emergency px-3 text-sm font-semibold text-white">
            <Icon name="phone" size={16} /> Urgence
          </Link>
        )}
      </header>

      {open && (
        <div className="fixed inset-0 z-40 lg:hidden" role="dialog" aria-modal="true" aria-label="Menu">
          <button type="button" className="absolute inset-0 bg-ink/40" aria-label="Fermer le menu" onClick={() => setOpen(false)} />
          <div className="absolute inset-y-0 left-0 w-72 max-w-[85vw] bg-navy shadow-xl">
            <button type="button" onClick={() => setOpen(false)} aria-label="Fermer le menu"
              className="absolute right-3 top-4 rounded-lg p-2 text-white/80 hover:bg-white/10">
              <Icon name="close" />
            </button>
            <SidebarContent user={user} items={items} onNavigate={() => setOpen(false)} onSignOut={signOut} />
          </div>
        </div>
      )}

      {config.data?.demo_mode && (
        <div className="border-b border-sim/20 bg-sim-soft px-4 py-2 text-center text-xs font-semibold text-sim sm:text-sm">
          Environnement de démonstration — comptes et données fictifs. Le bouton d'appel compose le numéro d'un membre de l'équipe.
        </div>
      )}

      <main id="main" className="mx-auto w-full max-w-6xl px-4 py-6 sm:px-6 sm:py-8 lg:px-8">
        {user.role === "doctor" && <EscalationBanner timeZone={user.timezone} />}
        <Outlet />
      </main>

      <footer className="mx-auto max-w-6xl px-4 pb-8 text-xs text-ink-subtle sm:px-6 lg:px-8">
        PULSE est un prototype de suivi de la tension artérielle. Il ne pose pas de diagnostic et ne remplace pas un
        professionnel de santé. En cas d'urgence, appelez les secours.
      </footer>
    </div>
  );
}
