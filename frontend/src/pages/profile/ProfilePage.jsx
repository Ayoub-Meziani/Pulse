import { useState } from "react";
import { useAuth } from "../../auth/AuthContext";
import {
  addTrustedContact, deleteTrustedContact, getCarePlan, getProfile, listTrustedContacts, updateProfile, updateTrustedContact,
} from "../../api/patient";
import Badge from "../../components/ui/Badge";
import Button from "../../components/ui/Button";
import { Card, CardBody, CardHeader, PageHeader } from "../../components/ui/Card";
import { Section } from "../../components/ui/States";
import { formatDate } from "../../lib/format";
import { useResource } from "../../lib/useResource";

const input = "field mt-1.5 text-sm";

function Row({ label, children }) {
  return (
    <div className="grid gap-1 py-3 sm:grid-cols-3">
      <dt className="text-sm text-ink-muted">{label}</dt>
      <dd className="text-sm text-ink sm:col-span-2">{children || <span className="text-ink-subtle">Non renseigné</span>}</dd>
    </div>
  );
}

function errorText(e) {
  if (e?.status === 422) {
    const d = Array.isArray(e.details) ? e.details.map((x) => x.message).filter(Boolean).join(" ; ") : "";
    return `Valeurs refusées${d ? ` : ${d}` : "."}`;
  }
  return "L'enregistrement a échoué. Réessayez.";
}

/** PUT replaces the whole profile, so the form always sends every field (empty -> null). */
function ProfileForm({ profile, onSaved, onCancel, patientId }) {
  const [f, setF] = useState({
    full_name: profile.full_name, timezone: profile.timezone, birth_year: profile.birth_year ?? "",
    relevant_conditions: profile.relevant_conditions.join(", "), allergies: profile.allergies ?? "",
    medication_context: profile.medication_context ?? "", regular_clinic: profile.regular_clinic ?? "",
    consent_location: profile.consent_location,
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.type === "checkbox" ? e.target.checked : e.target.value });

  async function save(event) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await updateProfile(patientId, {
        full_name: f.full_name.trim(), timezone: f.timezone.trim(),
        birth_year: f.birth_year === "" ? null : Number(f.birth_year),
        relevant_conditions: f.relevant_conditions.split(",").map((s) => s.trim()).filter(Boolean),
        allergies: f.allergies.trim() || null, medication_context: f.medication_context.trim() || null,
        regular_clinic: f.regular_clinic.trim() || null, consent_location: f.consent_location,
      });
      onSaved();
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={save} className="space-y-4">
      <label className="block text-sm font-medium text-ink">Nom<input className={input} required maxLength={120} value={f.full_name} onChange={set("full_name")} /></label>
      <div className="grid gap-4 sm:grid-cols-2">
        <label className="block text-sm font-medium text-ink">Année de naissance<input className={input} inputMode="numeric" value={f.birth_year} onChange={set("birth_year")} placeholder="1968" /></label>
        <label className="block text-sm font-medium text-ink">Fuseau horaire<input className={input} required value={f.timezone} onChange={set("timezone")} /></label>
      </div>
      <label className="block text-sm font-medium text-ink">Antécédents <span className="font-normal text-ink-muted">(séparés par des virgules)</span>
        <input className={input} value={f.relevant_conditions} onChange={set("relevant_conditions")} placeholder="hypertension, diabète" /></label>
      <label className="block text-sm font-medium text-ink">Allergies<input className={input} value={f.allergies} onChange={set("allergies")} /></label>
      <label className="block text-sm font-medium text-ink">Traitement en cours <span className="font-normal text-ink-muted">(tel que vous le décrivez ; PULSE ne l'interprète pas)</span>
        <textarea className={input} rows={2} value={f.medication_context} onChange={set("medication_context")} /></label>
      <label className="block text-sm font-medium text-ink">Cabinet ou clinique habituels<input className={input} value={f.regular_clinic} onChange={set("regular_clinic")} /></label>
      <label className="flex items-start gap-3 text-sm text-ink">
        <input type="checkbox" className="mt-0.5 h-4 w-4 accent-brand" checked={f.consent_location} onChange={set("consent_location")} />
        J'accepte que ma position soit enregistrée dans le dossier d'un épisode d'urgence quand je choisis de la partager.
      </label>
      {error && <p role="alert" className="rounded-xl bg-danger-soft px-4 py-3 text-sm text-danger">{error}</p>}
      <div className="flex flex-wrap gap-3">
        <Button type="submit" disabled={busy}>{busy ? "Enregistrement…" : "Enregistrer"}</Button>
        <Button variant="secondary" onClick={onCancel}>Annuler</Button>
      </div>
    </form>
  );
}

function Contacts({ patientId }) {
  const contacts = useResource((signal) => listTrustedContacts(patientId, { signal }), `tc:${patientId}`);
  const [adding, setAdding] = useState(false);
  const [form, setForm] = useState({ name: "", relationship: "", phone: "", consent: false });
  const [confirmDelete, setConfirmDelete] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  async function run(fn) {
    setBusy(true);
    setError(null);
    try { await fn(); contacts.reload(); return true; }
    catch (e) { setError(errorText(e)); return false; }
    finally { setBusy(false); }
  }

  async function add(event) {
    event.preventDefault();
    const ok = await run(() => addTrustedContact(patientId, {
      name: form.name.trim(), relationship: form.relationship.trim() || null, phone: form.phone.trim(), contact_consented: true,
    }));
    if (ok) { setAdding(false); setForm({ name: "", relationship: "", phone: "", consent: false }); }
  }

  return (
    <div className="space-y-3">
      <Section state={contacts} what="vos contacts">
        {(list) => list.length === 0 ? <p className="text-sm text-ink-muted">Aucun contact enregistré.</p> : (
          <ul className="divide-y divide-line">
            {list.map((c) => (
              <li key={c.id} className="flex flex-wrap items-center gap-2 py-3 text-sm">
                <span aria-hidden="true" className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-brand-soft font-bold text-brand">{c.name.trim().charAt(0).toUpperCase()}</span>
                <span className="min-w-40 flex-1 font-medium text-ink">{c.name}{c.relationship ? <span className="font-normal text-ink-muted"> · {c.relationship}</span> : null}
                  <span className="tnum block font-normal text-ink-muted">{c.phone}</span></span>
                {!c.active && <Badge>Inactif</Badge>}
                <Button variant="ghost" disabled={busy} onClick={() => run(() => updateTrustedContact(c.id, { active: !c.active }))}>{c.active ? "Désactiver" : "Réactiver"}</Button>
                {confirmDelete === c.id ? (
                  <span className="flex items-center gap-2">
                    <Button variant="emergency" disabled={busy} onClick={() => run(() => deleteTrustedContact(c.id)).then(() => setConfirmDelete(null))}>Supprimer définitivement</Button>
                    <Button variant="ghost" onClick={() => setConfirmDelete(null)}>Annuler</Button>
                  </span>
                ) : <Button variant="ghost" onClick={() => setConfirmDelete(c.id)}>Supprimer</Button>}
              </li>
            ))}
          </ul>
        )}
      </Section>
      {error && <p role="alert" className="rounded-xl bg-danger-soft px-4 py-3 text-sm text-danger">{error}</p>}
      {adding ? (
        <form onSubmit={add} className="animate-fade-up space-y-3 rounded-2xl border border-line bg-surface-muted/50 p-4">
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="block text-sm font-medium text-ink">Nom<input className={input} required maxLength={120} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></label>
            <label className="block text-sm font-medium text-ink">Lien<input className={input} maxLength={60} value={form.relationship} onChange={(e) => setForm({ ...form, relationship: e.target.value })} placeholder="Fille, voisin…" /></label>
          </div>
          <label className="block text-sm font-medium text-ink">Téléphone<input className={input} required inputMode="tel" value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} placeholder="+213 …" /></label>
          <label className="flex items-start gap-3 text-sm text-ink">
            <input type="checkbox" className="mt-0.5 h-4 w-4 accent-brand" checked={form.consent} onChange={(e) => setForm({ ...form, consent: e.target.checked })} />
            Cette personne a accepté d'être mon contact de confiance.
          </label>
          <div className="flex flex-wrap gap-3">
            <Button type="submit" disabled={busy || !form.consent}>Ajouter</Button>
            <Button variant="secondary" onClick={() => setAdding(false)}>Annuler</Button>
          </div>
        </form>
      ) : <Button variant="secondary" onClick={() => setAdding(true)}>Ajouter un contact</Button>}
    </div>
  );
}

/** The patient's profile, care plan (read only: set by the doctor) and trusted contacts. */
export default function ProfilePage() {
  const { user } = useAuth();
  const [editing, setEditing] = useState(false);
  const [saved, setSaved] = useState(false);
  const profile = useResource((signal) => getProfile(user.id, { signal }), `pr:${user.id}`);
  const plan = useResource((signal) => getCarePlan(user.id, { signal }), `cp:${user.id}`);

  return (
    <div className="space-y-6">
      <PageHeader eyebrow="Espace patient" title="Mon profil" />
      <div className="grid gap-4 lg:grid-cols-2">
        <Card variant="elevated">
          <CardHeader title="Informations" icon="user" action={!editing && profile.status === "ok" && <Button variant="secondary" onClick={() => { setEditing(true); setSaved(false); }}>Modifier</Button>} />
          <CardBody>
            {saved && <p role="status" className="mb-3 rounded-xl bg-success-soft px-4 py-3 text-sm text-success">Profil enregistré.</p>}
            <Section state={profile} what="votre profil">
              {(p) => editing ? (
                <ProfileForm profile={p} patientId={user.id} onCancel={() => setEditing(false)}
                  onSaved={() => { setEditing(false); setSaved(true); profile.reload(); }} />
              ) : (
                <dl className="divide-y divide-line">
                  <Row label="Nom">{p.full_name}</Row>
                  <Row label="Email">{p.email}</Row>
                  <Row label="Fuseau horaire">{p.timezone}</Row>
                  <Row label="Année de naissance">{p.birth_year}</Row>
                  <Row label="Médecin traitant">{p.regular_doctor_name}{p.regular_clinic ? ` · ${p.regular_clinic}` : ""}</Row>
                  <Row label="Antécédents">{p.relevant_conditions.join(", ")}</Row>
                  <Row label="Allergies">{p.allergies}</Row>
                  <Row label="Traitement en cours">{p.medication_context}</Row>
                  <Row label="Position en cas d'urgence">{p.consent_location ? "Peut être enregistrée quand je la partage" : "Non autorisée"}</Row>
                </dl>
              )}
            </Section>
          </CardBody>
        </Card>
        <div className="space-y-4">
          <Card className="relative overflow-hidden before:absolute before:inset-x-0 before:top-0 before:h-1 before:bg-linear-to-r before:from-brand before:to-glow">
            <CardHeader title="Plan de suivi" subtitle="Fixé par votre médecin" icon="clipboard" />
            <CardBody>
              <Section state={plan} what="votre plan de suivi">
                {(c) => (
                  <dl className="divide-y divide-line">
                    <Row label="Cible">
                      <span className="tnum text-lg font-extrabold">{c.target_systolic}/{c.target_diastolic}</span> <span className="text-ink-muted">mmHg</span>{" "}
                      {c.is_default ? <Badge>Cible générale</Badge> : <Badge tone="brand">Fixée par votre médecin</Badge>}
                    </Row>
                    <Row label="Mesures par jour">{c.monitoring_readings_per_day}</Row>
                    <Row label="Consigne du médecin">{c.clinician_guidance}</Row>
                    <Row label="Prochaine révision">{c.review_date && formatDate(c.review_date)}</Row>
                  </dl>
                )}
              </Section>
            </CardBody>
          </Card>
          <Card>
            <CardHeader icon="users" title="Personnes de confiance" subtitle="Visibles sur votre carte d'urgence. PULSE ne les contacte pas : c'est vous qui appelez ou partagez." />
            <CardBody><Contacts patientId={user.id} /></CardBody>
          </Card>
        </div>
      </div>
    </div>
  );
}
