import { useState } from "react";

export default function ProfilePage() {
  const [profile, setProfile] = useState({
    firstName: "Ishak",
    lastName: "Kaci",
    email: "patient@example.com",
    phone: "",
    age: "",
    emergencyContact: "",
    doctorName: "",
    doctorPhone: "",
  });

  const [message, setMessage] = useState("");

  function handleChange(event) {
    const { name, value } = event.target;

    setProfile((previousProfile) => ({
      ...previousProfile,
      [name]: value,
    }));

    setMessage("");
  }

  function handleSubmit(event) {
    event.preventDefault();

    setMessage(
      "Modifications enregistrées localement pour la démonstration."
    );
  }

  const inputClasses =
    "mt-2 w-full rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm outline-none transition focus:border-blue-500 focus:ring-2 focus:ring-blue-100";

  return (
    <div className="mx-auto max-w-4xl space-y-8">

      {/* En-tête */}
      <section>
        <p className="text-sm font-semibold text-blue-700">
          MON COMPTE
        </p>

        <h1 className="mt-2 text-3xl font-bold text-slate-900">
          Mon profil
        </h1>

        <p className="mt-2 text-slate-500">
          Gérez vos informations personnelles et vos contacts médicaux.
        </p>
      </section>

      <form onSubmit={handleSubmit} className="space-y-6">

        {/* Informations personnelles */}
        <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm sm:p-8">
          <h2 className="text-lg font-semibold text-slate-900">
            Informations personnelles
          </h2>

          <div className="mt-6 grid gap-5 sm:grid-cols-2">

            <div>
              <label className="text-sm font-medium text-slate-700">
                Prénom
              </label>

              <input
                type="text"
                name="firstName"
                value={profile.firstName}
                onChange={handleChange}
                className={inputClasses}
                placeholder="Votre prénom"
              />
            </div>

            <div>
              <label className="text-sm font-medium text-slate-700">
                Nom
              </label>

              <input
                type="text"
                name="lastName"
                value={profile.lastName}
                onChange={handleChange}
                className={inputClasses}
                placeholder="Votre nom"
              />
            </div>

            <div>
              <label className="text-sm font-medium text-slate-700">
                Adresse e-mail
              </label>

              <input
                type="email"
                name="email"
                value={profile.email}
                onChange={handleChange}
                className={inputClasses}
                placeholder="exemple@email.com"
              />
            </div>

            <div>
              <label className="text-sm font-medium text-slate-700">
                Téléphone
              </label>

              <input
                type="tel"
                name="phone"
                value={profile.phone}
                onChange={handleChange}
                className={inputClasses}
                placeholder="+213 ..."
              />
            </div>

            <div>
              <label className="text-sm font-medium text-slate-700">
                Âge
              </label>

              <input
                type="number"
                name="age"
                value={profile.age}
                onChange={handleChange}
                min="1"
                max="120"
                className={inputClasses}
                placeholder="Votre âge"
              />
            </div>

          </div>
        </section>

        {/* Contact d'urgence */}
        <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm sm:p-8">
          <h2 className="text-lg font-semibold text-slate-900">
            Contact d'urgence
          </h2>

          <p className="mt-1 text-sm text-slate-500">
            Personne à contacter si une notification nécessite une attention particulière.
          </p>

          <div className="mt-5">
            <label className="text-sm font-medium text-slate-700">
              Téléphone du contact
            </label>

            <input
              type="tel"
              name="emergencyContact"
              value={profile.emergencyContact}
              onChange={handleChange}
              className={inputClasses}
              placeholder="+213 ..."
            />
          </div>
        </section>

        {/* Médecin */}
        <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm sm:p-8">
          <h2 className="text-lg font-semibold text-slate-900">
            Médecin référent
          </h2>

          <div className="mt-5 grid gap-5 sm:grid-cols-2">

            <div>
              <label className="text-sm font-medium text-slate-700">
                Nom du médecin
              </label>

              <input
                type="text"
                name="doctorName"
                value={profile.doctorName}
                onChange={handleChange}
                className={inputClasses}
                placeholder="Nom du médecin"
              />
            </div>

            <div>
              <label className="text-sm font-medium text-slate-700">
                Téléphone du médecin
              </label>

              <input
                type="tel"
                name="doctorPhone"
                value={profile.doctorPhone}
                onChange={handleChange}
                className={inputClasses}
                placeholder="+213 ..."
              />
            </div>

          </div>
        </section>

        {/* Bouton de sauvegarde */}
        <div className="flex flex-col items-start gap-4">

          <button
            type="submit"
            className="rounded-xl bg-blue-600 px-6 py-3 font-medium text-white transition hover:bg-blue-700"
          >
            Enregistrer les modifications
          </button>

          {message && (
            <p className="rounded-lg bg-green-50 px-4 py-3 text-sm text-green-700">
              {message}
            </p>
          )}

        </div>

      </form>

      <p className="text-xs leading-5 text-slate-400">
        Démonstration : les modifications sont conservées uniquement
        dans l'état local de React. Elles ne sont pas encore enregistrées
        dans une base de données.
      </p>

    </div>
  );
}