import React from 'react';

const COLORS = {
  CONTRADICTION:        'bg-red-100 text-red-800',
  CONDITIONAL_BOTH_APPLY: 'bg-yellow-100 text-yellow-800',
  COMPLEMENTARY:        'bg-green-100 text-green-800',
  INSUFFICIENT_EVIDENCE: 'bg-gray-100 text-gray-600',
};

const LABELS = {
  CONTRADICTION:        'Contradiction',
  CONDITIONAL_BOTH_APPLY: 'Both apply (conditional)',
  COMPLEMENTARY:        'Complementary',
  INSUFFICIENT_EVIDENCE: 'Insufficient evidence',
};

export default function VerdictBadge({ verdict }) {
  if (!verdict) return null;
  return (
    <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${COLORS[verdict]}`}>
      {LABELS[verdict]}
    </span>
  );
}
