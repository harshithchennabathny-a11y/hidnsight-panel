import React from 'react';

// RULE: Both columns MUST be identical in size, weight, and color.
// Verdict colors are NEVER applied here.
export default function ClaimPair({ factA, factB }) {
  return (
    <div className="grid grid-cols-2 gap-4 mt-3">
      <ClaimColumn label="Claim A" fact={factA} />
      <ClaimColumn label="Claim B" fact={factB} />
    </div>
  );
}

function ClaimColumn({ label, fact }) {
  if (!fact) return null;
  return (
    // Identical className on both — do NOT vary by label
    <div className="border border-gray-200 rounded-lg p-4 bg-gray-50">
      <p className="text-xs font-semibold text-gray-500 uppercase mb-2">{label}</p>
      <blockquote className="text-sm text-gray-800 italic mb-3">
        "{fact.claim_raw}"
      </blockquote>
      <p className="text-xs text-gray-500">
        {fact.interviewer} · Round {fact.round} · {fact.task_context.replace(/_/g, ' ')}
      </p>
    </div>
  );
}
