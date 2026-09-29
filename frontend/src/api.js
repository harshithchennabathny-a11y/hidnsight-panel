const BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';

const handle = async (res) => {
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.error || `HTTP ${res.status}`);
  }
  return res.json();
};

export const getCandidates = () => fetch(`${BASE}/candidates`).then(handle);
export const postSubmission = (body) =>
  fetch(`${BASE}/submissions`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }).then(handle);
export const getEvaluation = (slug) => fetch(`${BASE}/candidates/${slug}/evaluation`).then(handle);
export const getBriefing = (slug, forRound, useMemory = true) => fetch(`${BASE}/candidates/${slug}/briefing?for_round=${forRound}&use_memory=${useMemory}`).then(handle);
export const getDisagreements = (slug) => fetch(`${BASE}/candidates/${slug}/disagreements`).then(handle);
export const postProbeAsked = (id) => fetch(`${BASE}/disagreements/${id}/probe-asked`, { method: 'POST' }).then(handle);
export const postResolution = (id, body) =>
  fetch(`${BASE}/disagreements/${id}/resolution`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }).then(handle);
export const postFinalize = (slug) => fetch(`${BASE}/candidates/${slug}/finalize`, { method: 'POST' }).then(handle);
export const getCalibration = () => fetch(`${BASE}/calibration`).then(handle);
