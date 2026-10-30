import { useState } from "react";

const initialProfile = {
firstName: "",
lastName: "",
email: "",
phone: "",
age: "",
emergencyContact: "",
doctorName: "",
doctorPhone: "",
};

export default function ProfilePage() {
const [profile, setProfile] = useState(initialProfile);

const inputClasses =
"mt-2 w-full rounded-xl border border-slate-200 bg-[#fafbfc] px-4 py-3 text-sm text-slate-800 outline-none transition placeholder:text-slate-400 focus:border-emerald-600 focus:bg-white focus:ring-4 focus:ring-emerald-50";

function handleChange(event) {
const { name, value } = event.target;

```
setProfile((previousProfile) => ({
  ...previousProfile,
  [name]: value,
}));
```

}

function handleSubmit(event) {
event.preventDefault();
}

return ( <div className="mx-auto max-w-5xl space-y-10">

```
  {/* Header */}
  <section>
    <p className="text-xs font-semibold uppercase tracking-[0.2em] text-emerald-700">
      Paramètres du compte
    </p>

    <h1 className="mt-3 text-3xl font-semibold tracking-tight text-[#142b3b] sm:text-4xl">
      Mon profil
    </h1>

    <p className="mt-3 max-w-xl text-sm leading-6 text-slate-500">
      Gérez vos informations personnelles et vos contacts médicaux.
    </p>
  </section>

  <form onSubmit={handleSubmit} className="space-y-6">

    {/* Personal information */}
    <section className="rounded-2xl border border-slate-200 bg-white p-6 sm:p-8">
      <div className="border-b border-slate-100 pb-5">
        <h2 className="text-lg font-semibold text-[#142b3b]">
          Informations personnelles
        </h2>

        <p className="mt-1 text-sm text-slate-500">
          Vos informations de base.
        </p>
      </div>

      <div className="mt-6 grid gap-5 sm:grid-cols-2">

        <div>
          <label htmlFor="firstName" className="text-sm font-medium text-slate-700">
            Prénom
          </label>

          <input
            id="firstName"
            type="text"
            name="firstName"
            value={profile.firstName}
            onChange={handleChange}
            className={inputClasses}
            placeholder="Votre prénom"
          />
        </div>

        <div>
          <label htmlFor="lastName" className="text-sm font-medium text-slate-700">
            Nom
          </label>

          <input
            id="lastName"
            type="text"
            name="lastName"
            value={profile.lastName}
            onChange={handleChange}
            className={inputClasses}
            placeholder="Votre nom"
          />
        </div>

        <div>
          <label htmlFor="email" className="text-sm font-medium text-slate-700">
            Adresse e-mail
          </label>

          <input
            id="email"
            type="email"
            name="email"
            value={profile.email}
            onChange={handleChange}
            className={inputClasses}
            placeholder="votre@email.com"
          />
        </div>

        <div>
          <label htmlFor="phone" className="text-sm font-medium text-slate-700">
            Téléphone
          </label>

          <input
            id="phone"
            type="tel"
            name="phone"
            value={profile.phone}
            onChange={handleChange}
            className={inputClasses}
            placeholder="+213 ..."
          />
        </div>

        <div>
          <label htmlFor="age" className="text-sm font-medium text-slate-700">
            Âge
          </label>

          <input
            id="age"
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

    {/* Emergency contact */}
    <section className="rounded-2xl border border-slate-200 bg-white p-6 sm:p-8">
      <div className="border-b border-slate-100 pb-5">
        <h2 className="text-lg font-semibold text-[#142b3b]">
          Contact d'urgence
        </h2>

        <p className="mt-1 text-sm text-slate-500">
          Coordonnées de la personne à contacter en cas de besoin.
        </p>
      </div>

      <div className="mt-6">
        <label htmlFor="emergencyContact" className="text-sm font-medium text-slate-700">
          Téléphone du contact
        </label>

        <input
          id="emergencyContact"
          type="tel"
          name="emergencyContact"
          value={profile.emergencyContact}
          onChange={handleChange}
          className={inputClasses}
          placeholder="+213 ..."
        />
      </div>
    </section>

    {/* Doctor */}
    <section className="rounded-2xl border border-slate-200 bg-white p-6 sm:p-8">
      <div className="border-b border-slate-100 pb-5">
        <h2 className="text-lg font-semibold text-[#142b3b]">
          Médecin référent
        </h2>

        <p className="mt-1 text-sm text-slate-500">
          Coordonnées de votre médecin.
        </p>
      </div>

      <div className="mt-6 grid gap-5 sm:grid-cols-2">

        <div>
          <label htmlFor="doctorName" className="text-sm font-medium text-slate-700">
            Nom du médecin
          </label>

          <input
            id="doctorName"
            type="text"
            name="doctorName"
            value={profile.doctorName}
            onChange={handleChange}
            className={inputClasses}
            placeholder="Nom du médecin"
          />
        </div>

        <div>
          <label htmlFor="doctorPhone" className="text-sm font-medium text-slate-700">
            Téléphone du médecin
          </label>

          <input
            id="doctorPhone"
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

    {/* Submit */}
    <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
      <button
        type="submit"
        disabled
        className="cursor-not-allowed rounded-xl bg-[#142b3b] px-6 py-3 text-sm font-medium text-white opacity-60"
      >
        Enregistrement indisponible
      </button>

      {/* <p className="text-xs text-slate-400">
        La sauvegarde sera activée après la connexion au backend.
      </p> */}
    </div>

  </form>
</div>


);
}
