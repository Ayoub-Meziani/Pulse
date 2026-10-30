// Emergency data kept on the device so the emergency screen opens without network (conception §4, §8.2):
// the public emergency configuration and the patient's own medical card. Cleared on explicit sign-out.
const CONFIG = "pulse.cache.emergency-config";
const CARD = "pulse.cache.emergency-card";

function read(key) {
  try { return JSON.parse(localStorage.getItem(key) ?? "null"); } catch { return null; }
}

function write(key, value) {
  try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* storage unavailable */ }
}

export const readCachedConfig = () => read(CONFIG);
export const cacheConfig = (config) => write(CONFIG, config);

/** The card is only reused for the same patient. */
export function readCachedCard(patientId) {
  const c = read(CARD);
  return c && c.patientId === patientId ? c.card : null;
}

export const cacheCard = (patientId, card) => write(CARD, { patientId, card });

export function clearOfflineCache() {
  try {
    localStorage.removeItem(CONFIG);
    localStorage.removeItem(CARD);
    localStorage.removeItem("pulse.emergency.queue");
  } catch { /* nothing to clear */ }
}
