import React, { useState, useEffect } from 'react';
import { getDisagreements, postProbeAsked, postFinalize } from '../api';
import ErrorMessage from './ErrorMessage';
import LoadingSpinner from './LoadingSpinner';
import LifecycleChip from './LifecycleChip';
import VerdictBadge from './VerdictBadge';
import ClaimPair from './ClaimPair';
import ProvenanceTimeline from './ProvenanceTimeline';
import ResolutionForm from './ResolutionForm';

// Sort order: unresolved first
const SORT_ORDER = { RAISED: 0, ESCALATED: 1, PROBE_ASKED: 2, STILL_OPEN: 3, RESOLVED: 4 };

export default function DisagreementsPanel({ slug }) {
  const [disagreements, setDisagreements] = useState([]);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  const [finalizeResult, setFinalizeResult] = useState(null);

  const fetchDisagreements = () => {
    setLoading(true);
    getDisagreements(slug)
      .then(list => {
        const sorted = [...list].sort((a, b) =>
          (SORT_ORDER[a.state] ?? 99) - (SORT_ORDER[b.state] ?? 99)
        );
        setDisagreements(sorted);
      })
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
    // Spec §7.3: exact confirmation dialog text
    if (!window.confirm(
      'Finalizing locks this candidate. Disagreements that are not resolved will be recorded as Still open.'
    )) return;
    try {
      const result = await postFinalize(slug);
      setFinalizeResult(result);
      fetchDisagreements();
    } catch (err) { alert(err.message); }
  };

  if (loading) return <LoadingSpinner />;
  if (error) return <ErrorMessage error={error} />;

  const canAct = (state) =>
    state === 'RAISED' || state === 'PROBE_ASKED' || state === 'ESCALATED';

  return (
    <div>
      <div className="flex justify-between items-center mb-6">
        <h2 className="text-2xl font-bold text-gray-900">Disagreements</h2>
        <button
          onClick={handleFinalize}
          className="px-4 py-2 bg-red-600 text-white rounded hover:bg-red-700 text-sm font-medium shadow-sm transition-colors"
        >
          Finalize
        </button>
      </div>

      {finalizeResult && (
        <div className="mb-6 p-4 bg-amber-50 border border-amber-200 rounded-lg text-sm text-amber-800">
          <strong>Panel finalized.</strong> {finalizeResult.still_open_count ?? 0} disagreement(s) recorded as Still open.
        </div>
      )}

      {disagreements.length === 0 ? (
        <p className="text-gray-500 italic">No disagreements recorded.</p>
      ) : (
        disagreements.map(d => (
          <div key={d.disagreement_id} className="border rounded-xl p-5 mb-5 bg-white shadow-sm">
            {/* Row header: kind, competency, state, date */}
            <div className="flex flex-wrap items-center gap-3 mb-3">
              <h3 className="font-semibold text-gray-900 capitalize">
                {d.competency.replace(/_/g, ' ')}
              </h3>
              <VerdictBadge verdict={d.kind} />
              <LifecycleChip state={d.state} />
              <span className="text-xs text-gray-400 ml-auto">
                Raised {new Date(d.created_at).toLocaleDateString()}
              </span>
            </div>

            {/* Both claims — identical styling per UI fairness rule */}
            <ClaimPair factA={d.fact_a} factB={d.fact_b} />

            {/* Follow-up / probe */}
            {d.suggested_probe && (
              <div className="mt-4 p-4 bg-gray-50 rounded-lg border border-gray-200">
                <h4 className="text-xs font-semibold text-gray-700 uppercase mb-2">Suggested probe</h4>
                <p className="text-sm text-gray-900">{d.suggested_probe}</p>
              </div>
            )}

            {/* Provenance timeline */}
            <div className="mt-4">
              <h4 className="text-sm font-semibold text-gray-800 mb-2">Lifecycle timeline</h4>
              <ProvenanceTimeline transitions={d.transitions} />
            </div>

            {/* Action buttons per state — spec §7.3 */}
            {canAct(d.state) && (
              <div className="mt-4 flex flex-wrap gap-3">
                {/* "Mark probe asked" for RAISED or ESCALATED */}
                {(d.state === 'RAISED' || d.state === 'ESCALATED') && (
                  <button
                    onClick={() => handleProbeAsked(d.disagreement_id)}
                    className="px-4 py-2 bg-blue-100 text-blue-700 rounded hover:bg-blue-200 text-sm font-medium transition-colors"
                  >
                    Mark probe asked
                  </button>
                )}
              </div>
            )}

            {/* Record resolution — available from RAISED, PROBE_ASKED, ESCALATED */}
            {canAct(d.state) && (
              <ResolutionForm
                disagreementId={d.disagreement_id}
                onResolved={fetchDisagreements}
              />
            )}
          </div>
        ))
      )}
    </div>
  );
}
