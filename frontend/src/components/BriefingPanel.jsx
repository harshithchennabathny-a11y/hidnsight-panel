import React, { useState, useEffect } from 'react';
import { getBriefing } from '../api';
import ErrorMessage from './ErrorMessage';
import LoadingSpinner from './LoadingSpinner';

export default function BriefingPanel({ slug, forRound }) {
  const [briefing, setBriefing] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  const [hindsightEnabled, setHindsightEnabled] = useState(true);

  const fetchBriefing = (useMemory) => {
    setLoading(true);
    setError(null);
    getBriefing(slug, forRound, useMemory)
      .then(setBriefing)
      .catch(err => setError(err.message))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    fetchBriefing(true);
  }, [slug, forRound]);

  const handleToggle = () => {
    const next = !hindsightEnabled;
    setHindsightEnabled(next);
    fetchBriefing(next);
  };

  if (loading) return <LoadingSpinner />;
  if (error) return <ErrorMessage error={error} />;
  if (!briefing) return null;

  if (briefing.generic) {
    return (
      <div className="bg-white border rounded-xl p-5 mb-6">
        <h2 className="text-lg font-bold mb-3">Briefing for Round {forRound}</h2>
        <p className="text-gray-600">No prior rounds to summarize.</p>
      </div>
    );
  }

  return (
    <div className="bg-white border rounded-xl p-5 mb-6 shadow-sm">
      <div className="flex items-center justify-between mb-4 border-b pb-3">
        <div className="flex items-center gap-3">
          <h2 className="text-lg font-bold text-gray-900">Briefing for Round {forRound}</h2>
          <span className="text-xs bg-gray-100 text-gray-500 px-2 py-1 rounded">Source: {briefing.synthesis_source}</span>
        </div>
        
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium text-gray-700">Hindsight Memory:</span>
          <button 
            title="Toggle between memory-backed briefing (Hindsight + LLM overview) and raw SQLite-only data with no LLM. This is a live API call — not static text."
            onClick={handleToggle}
            className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${hindsightEnabled ? 'bg-blue-600' : 'bg-gray-300'}`}
          >
            <span className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${hindsightEnabled ? 'translate-x-6' : 'translate-x-1'}`} />
          </button>
          <span className="text-xs text-gray-400 italic">{hindsightEnabled ? 'live memory' : 'no memory — raw SQLite only'}</span>
        </div>
      </div>
      
      {!hindsightEnabled ? (
        <div className="bg-amber-50 p-4 rounded-lg border border-amber-200 mt-2">
          <h3 className="text-amber-800 font-bold mb-2 text-sm uppercase tracking-wide">
            ⚡ Raw SQLite Data — No Memory, No LLM
          </h3>
          <p className="text-amber-700 text-xs mb-3">
            This is the actual API response with <code>use_memory=false</code>. Hindsight and all LLM overview generation are bypassed. 
            What you see below is pure structured data from SQLite — no synthesis, no context, no probing suggestions.
          </p>
          {briefing?.earlier_findings?.length > 0 ? (
            <div>
              <p className="text-xs font-semibold text-amber-800 mb-2">Earlier findings (raw facts only):</p>
              {briefing.earlier_findings.map((f, i) => (
                <div key={i} className="mb-2">
                  <span className="text-xs font-medium text-amber-900 capitalize">{f.competency.replace(/_/g, ' ')}: </span>
                  {f.claims.map((c, j) => (
                    <span key={j} className="text-xs text-amber-800">"{ c.claim}" ({c.interviewer}, R{c.round}) </span>
                  ))}
                </div>
              ))}
            </div>
          ) : (
            <p className="text-xs text-amber-700">No earlier facts found in SQLite for this round.</p>
          )}
          <p className="text-xs text-gray-400 mt-3 italic">synthesis_source: {briefing?.synthesis_source}</p>
        </div>
      ) : (
        <>
          {briefing.overview && (
        <div className="mb-5">
          <h4 className="text-sm font-semibold text-gray-700 uppercase tracking-wider mb-2">Overview</h4>
          <p className="text-sm text-gray-800">{briefing.overview}</p>
        </div>
      )}

      {briefing.open_disagreements.length > 0 && (
        <div className="mb-5 bg-orange-50 border border-orange-100 p-4 rounded-lg">
          <h4 className="text-sm font-semibold text-orange-800 uppercase tracking-wider mb-3">Open Disagreements to Probe</h4>
          <ul className="space-y-3">
            {briefing.open_disagreements.map(d => (
              <li key={d.disagreement_id} className="text-sm text-orange-900">
                <span className="font-semibold capitalize">{d.competency.replace(/_/g, ' ')}:</span> {d.follow_up}
              </li>
            ))}
          </ul>
        </div>
      )}

      {briefing.earlier_findings.length > 0 && (
        <div>
          <h4 className="text-sm font-semibold text-gray-700 uppercase tracking-wider mb-3">Earlier Findings</h4>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {briefing.earlier_findings.map((f, i) => (
              <div key={i} className="border border-gray-100 rounded-lg p-3 bg-gray-50">
                <h5 className="font-medium text-gray-900 capitalize mb-2">{f.competency.replace(/_/g, ' ')}</h5>
                <ul className="list-disc pl-4 space-y-1">
                  {f.claims.map((c, j) => (
                    <li key={j} className="text-xs text-gray-600">
                      "{c.claim}" <span className="text-gray-400">({c.interviewer}, R{c.round})</span>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </div>
      )}
        </>
      )}
    </div>
  );
}
