// Landing page per server-side role. Navigation is only convenience: every API call is authorized by the
// server, so a hidden link is never a permission.
export function homeFor(role) {
  if (role === "patient") return "/patient";
  if (role === "doctor") return "/doctor";
  if (role === "admin") return "/admin";
  return null;
}

export const ROLE_LABEL = { patient: "Patient", doctor: "Médecin", admin: "Administrateur" };

export const NAV = {
  patient: [
    { to: "/patient", label: "Tableau de bord", icon: "home", end: true },
    { to: "/patient/mesure", label: "Nouvelle mesure", icon: "plus" },
    { to: "/patient/historique", label: "Historique", icon: "history" },
    { to: "/patient/alertes", label: "Alertes", icon: "bell" },
    { to: "/patient/journal", label: "Journal", icon: "note" },
    { to: "/patient/profil", label: "Mon profil", icon: "user" },
  ],
  doctor: [{ to: "/doctor", label: "Mes patients", icon: "users", end: true }],
  admin: [{ to: "/admin", label: "Compte", icon: "shield", end: true }],
};
