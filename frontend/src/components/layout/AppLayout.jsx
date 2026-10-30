import { Link, NavLink, Outlet } from "react-router";

const navigation = [
  { name: "Espace patient", path: "/patient", icon: "◉" },
  { name: "Espace médecin", path: "/doctor", icon: "▦" },
  { name: "Alertes", path: "/alerts", icon: "◷" },
  { name: "Mon profil", path: "/profile", icon: "○" },
];

export default function AppLayout() {
  const linkClasses = ({ isActive }) =>
    `flex items-center gap-3 rounded-xl px-4 py-3 text-sm font-medium transition-all duration-200 ${
      isActive
        ? "bg-white/10 text-white"
        : "text-slate-400 hover:bg-white/5 hover:text-white"
    }`;

  return (
    <div className="min-h-screen bg-[#f7f8fa] text-slate-900 md:flex">

      {/* Sidebar */}
      <aside className="flex w-full flex-col bg-[#142b3b] px-5 py-5 md:sticky md:top-0 md:h-screen md:w-64 md:shrink-0 md:px-6 md:py-8">

        {/* Logo */}
        <Link to="/patient" className="mb-8 flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-emerald-400 text-lg font-bold text-[#142b3b]">
            P
          </div>

          <div>
            <h1 className="text-xl font-bold tracking-wide text-white">
              PULSE
            </h1>
            <p className="text-xs text-slate-400">
              Healthcare platform
            </p>
          </div>
        </Link>

        {/* Navigation */}
        <div>
          <p className="mb-3 px-4 text-xs font-semibold uppercase tracking-widest text-slate-500">
            Menu principal
          </p>
          <nav className="flex gap-2 overflow-x-auto pb-2 md:flex-col md:pb-0">
            {navigation.map((item) => (
              <NavLink
                key={item.path}
                to={item.path}
                className={linkClasses}
              >
                <span className="text-lg">{item.icon}</span>
                <span className="whitespace-nowrap">{item.name}</span>
              </NavLink>
            ))}
          </nav>
        </div>

        {/* Sidebar bottom */}
        <div className="mt-8 hidden rounded-2xl border border-white/10 bg-white/5 p-4 md:mt-auto md:block">
          <p className="text-sm font-semibold text-white">
            Votre santé, notre priorité.
          </p>
          <p className="mt-2 text-xs leading-5 text-slate-400">
            Une plateforme pour faciliter le suivi de la tension artérielle.
          </p>
        </div>
      </aside>

      {/* Main area */}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-20 flex h-16 items-center justify-between border-b border-slate-200 bg-white/95 px-5 backdrop-blur-md sm:px-8">
          <p className="text-sm font-medium text-slate-500">
            Plateforme de suivi médical
          </p>

          <div className="flex h-9 w-9 items-center justify-center rounded-full bg-emerald-50 text-sm font-semibold text-emerald-700">
            P
          </div>
        </header>

        <main className="w-full flex-1 px-5 py-8 sm:px-8 sm:py-10 lg:px-10">
          <Outlet />
        </main>

        <footer className="border-t border-slate-200 px-5 py-5 text-center text-xs text-slate-400 sm:px-8">
          PULSE · Plateforme de suivi de la tension artérielle
        </footer>

      </div>
    </div>
  );
}