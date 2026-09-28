import React, { useState, useEffect } from 'react';
import { getDisagreements, postProbeAsked, postFinalize } from '../api';
import ErrorMessage from './ErrorMessage';
import LoadingSpinner from './LoadingSpinner';
import LifecycleChip from './LifecycleChip';
import VerdictBadge from './VerdictBadge';
import ClaimPair from './ClaimPair';
import ProvenanceTimeline from './ProvenanceTimeline';
import ResolutionForm from './ResolutionForm';

export default function DisagreementsPanel({ slug }) {
  const [disagreements, setDisagreements] = useState([]);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);

  const fetchDisagreements = () => {
    setLoading(true);
    getDisagreements(slug)
      .then(setDisagreements)
      .catch(err => setError(err.message))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    fetchDisagreements();
  }, [slug]);

  const handleProbeAsked = async (id) => {
    try {
      await postProbeAsked(id);
      fetchDisagreements();
    } catch (err) { alert(err.message); }
  };

  const handleFinalize = async () => {
    if (!window.confirm("Are you sure? This moves non-RESOLVED disagreements to STILL_OPEN.")) return;
    try {
      await postFinalize(slug);
      fetchDisagreements();
    } catch (err) { alert(err.message); }
  };

  if (loading) return <LoadingSpinner />;
  if (error) return <ErrorMessage error={error} />;

  return (
    <div>
      <div className="flex justify-between items-center mb-6">
        <h2 className="text-2xl font-bold text-gray-900">Coordinator View (Disagreements)</h2>
        <button onClick={handleFinalize} className="px-4 py-2 bg-red-600 text-white rounded hover:bg-red-700 text-sm font-medium shadow-sm">
          Finalize Panel
        </button>
      </div>

      {disagreements.length === 0 ? (
        <p className="text-gray-500 italic">No disagreements recorded.</p>
      ) : (
        disagreements.map(d => (
          <div key={d.disagreement_id} className="border rounded-xl p-5 mb-5 bg-white shadow-sm">
            <div className="flex justify-between items-start mb-3">
              <div className="flex items-center gap-3">
                <h3 className="font-semibold text-gray-900 capitalize">{d.competency.replace(/_/g, ' ')}</h3>
                <LifecycleChip state={d.state} />
                <VerdictBadge verdict={d.kind} />
              </div>
            </div>

            <ClaimPair factA={d.fact_a} factB={d.fact_b} />

            <div className="mt-4 p-4 bg-gray-50 rounded-lg border border-gray-200">
              <h4 className="text-xs font-semibold text-gray-700 uppercase mb-2">Suggested Probe</h4>
              <p className="text-sm text-gray-900">{d.suggested_probe}</p>
            </div>

            <div className="mt-4">
              <h4 className="text-sm font-semibold text-gray-800 mb-2">Lifecycle Timeline</h4>
              <ProvenanceTimeline transitions={d.transitions} />
            </div>

            {d.state === 'RAISED' && (
              <button onClick={() => handleProbeAsked(d.disagreement_id)} className="mt-4 px-4 py-2 bg-blue-100 text-blue-700 rounded hover:bg-blue-200 text-sm font-medium">
                Mark Probe Asked
              </button>
            )}

            {(d.state === 'PROBE_ASKED' || d.state === 'ESCALATED') && (
              <ResolutionForm disagreementId={d.disagreement_id} onResolved={fetchDisagreements} />
            )}
          </div>
        ))
      )}
    </div>
  );
}
