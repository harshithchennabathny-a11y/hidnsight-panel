import React from 'react';

export default function ProvenanceTimeline({ transitions, verdictPathHumanReadable }) {
  if (!transitions || transitions.length === 0) return null;
  
  return (
    <div className="mt-3">
      {verdictPathHumanReadable && (
        <p className="text-xs text-gray-500 mb-2 font-medium">Path: {verdictPathHumanReadable}</p>
      )}
      <ol className="border-l border-gray-200 ml-2">
        {transitions.map((t, i) => (
          <li key={i} className="ml-4 mb-3 relative">
            <span className="absolute -left-[1.35rem] mt-1 w-2.5 h-2.5 rounded-full bg-gray-300 border border-white" />
            <p className="text-xs font-semibold text-gray-700">{t.to_state}</p>
            <p className="text-[10px] text-gray-400">{new Date(t.created_at).toLocaleString()}</p>
            {t.note && <p className="text-xs text-gray-600 mt-0.5">{t.note}</p>}
          </li>
        ))}
      </ol>
    </div>
  );
}
