export default function LoginPage() {
  const handleSubmit = (event) => {
    event.preventDefault();
    // La connexion FastAPI sera intégrée ultérieurement.
  };

  return (
    <main className="flex min-h-screen items-center justify-center bg-[#F7F8FA] px-4 py-6">
      <section className="w-full max-w-md rounded-2xl border border-slate-200 bg-white p-6 shadow-lg shadow-slate-900/5 sm:p-9">
        {/* Logo */}
        <div className="mb-7 flex items-center justify-center gap-3">
          <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-[#0B5CAD] text-xl font-bold text-white">
            P
          </div>

          <div>
            <h1 className="text-2xl font-bold tracking-wide text-[#142B3B]">
              PULSE
            </h1>
            <p className="text-xs text-slate-500">
              Healthcare platform
            </p>
          </div>
        </div>

        {/* Heading */}
        <div className="mb-7 text-center">
          <h2 className="text-2xl font-bold text-[#142B3B]">
            Bienvenue sur PULSE
          </h2>
          <p className="mt-2 text-sm text-slate-500">
            Connectez-vous pour accéder à votre espace.
          </p>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="space-y-5">
          <div>
            <label
              htmlFor="email"
              className="mb-2 block text-sm font-semibold text-[#142B3B]"
            >
              Adresse e-mail
            </label>

            <input
              id="email"
              type="email"
              placeholder="exemple@email.com"
              autoComplete="email"
              required
              className="h-12 w-full rounded-xl border border-slate-200 bg-white px-4 text-sm text-[#142B3B] outline-none transition placeholder:text-slate-400 focus:border-[#0B5CAD] focus:ring-4 focus:ring-blue-500/10"
            />
          </div>

          <div>
            <label
              htmlFor="password"
              className="mb-2 block text-sm font-semibold text-[#142B3B]"
            >
              Mot de passe
            </label>

            <input
              id="password"
              type="password"
              placeholder="Votre mot de passe"
              autoComplete="current-password"
              required
              className="h-12 w-full rounded-xl border border-slate-200 bg-white px-4 text-sm text-[#142B3B] outline-none transition placeholder:text-slate-400 focus:border-[#0B5CAD] focus:ring-4 focus:ring-blue-500/10"
            />
          </div>

          <button
            type="submit"
            className="h-12 w-full rounded-xl bg-[#0B5CAD] text-sm font-semibold text-white shadow-md shadow-blue-900/10 transition hover:bg-blue-800 active:scale-[0.99]"
          >
            Se connecter
          </button>
        </form>

        {/* Security information */}
        <div className="mt-6 flex items-center justify-center gap-2 text-xs text-slate-500">
          <span className="text-[#0B5CAD]">●</span>
          Accès sécurisé à votre espace médical
        </div>

        <p className="mt-7 text-center text-xs text-slate-400">
          PULSE · Plateforme de suivi de la tension artérielle
        </p>
      </section>
    </main>
  );
}