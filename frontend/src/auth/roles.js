// Landing page per server-side role. Admin has no screen in this app.
export function homeFor(role) {
  if (role === "patient") return "/patient";
  if (role === "doctor") return "/doctor";
  return null;
}
