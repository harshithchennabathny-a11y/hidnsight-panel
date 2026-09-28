import React from 'react';

const COLORS = {
  RAISED:      'bg-red-100 text-red-800 border-red-200',
  PROBE_ASKED: 'bg-blue-100 text-blue-800 border-blue-200',
  RESOLVED:    'bg-green-100 text-green-800 border-green-200',
  ESCALATED:   'bg-orange-100 text-orange-800 border-orange-200',
  STILL_OPEN:  'bg-gray-100 text-gray-800 border-gray-200',
};

export default function LifecycleChip({ state }) {
  if (!state) return null;
  return (
    <span className={`text-xs font-medium px-2 py-0.5 rounded-full border ${COLORS[state] || 'bg-gray-100 text-gray-800 border-gray-200'}`}>
      {state.replace(/_/g, ' ')}
    </span>
  );
}
