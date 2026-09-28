import React from 'react';
import VerdictBadge from './VerdictBadge';
import LifecycleChip from './LifecycleChip';
import ClaimPair from './ClaimPair';

function insufficiencyText(reason) {
  if (reason === 'single_source') {
    return "Not enough independent sources: only one interviewer has assessed this competency.";
  }
  if (reason === 'anchored_agreement_only') {
    return "Not enough independent sources: the matching assessments were written after reading each other's notes.";
  }
  return reason;
}

export default function CompetencyCard({ analysis }) {
  const isInsufficient = analysis.verdict === 'INSUFFICIENT_EVIDENCE';

  return (
    <div className="border rounded-xl p-5 mb-4 bg-white shadow-sm">
      {/* 1. Header */}
      <div className="flex items-center gap-3 mb-1">
        <h3 className="font-semibold text-gray-900 capitalize">
          {analysis.competency.replace(/_/g, ' ')}
        </h3>
        <VerdictBadge verdict={analysis.verdict} />
        {analysis.lifecycle_state && <LifecycleChip state={analysis.lifecycle_state} />}
      </div>

      {/* 2. Path line — always visible */}
      <p className="text-xs text-gray-500 mb-3">{analysis.verdict_path_human_readable}</p>

      {/* 3. Independent sources */}
      <p className="text-xs text-gray-600 mb-3">
        Independent sources: {analysis.independent_source_count}
      </p>

      {isInsufficient ? (
        <p className="text-sm text-gray-600">{insufficiencyText(analysis.insufficiency_reason)}</p>
      ) : (
        <>
          {/* 4. Claim pair */}
          {analysis.primary_pair && (
            <ClaimPair factA={analysis.primary_pair.fact_a} factB={analysis.primary_pair.fact_b} />
          )}

          {/* 5. Anchored dissent note */}
          {analysis.anchored_dissent && (
            <p className="text-xs text-amber-700 mt-2">
              One of these assessments was written after reading the other interviewer's notes.
            </p>
          )}

          {/* 6. Pair count */}
          <p className="text-xs text-gray-400 mt-2">
            {analysis.pair_count} pairs compared. The pair shown is the highest-severity one.
          </p>

          {/* 7. Rationale + follow-up */}
          {analysis.synthesis_rationale && (
            <p className="text-sm text-gray-700 mt-3">{analysis.synthesis_rationale}</p>
          )}
          {analysis.recommended_follow_up && (
            <div className="mt-2 p-3 bg-blue-50 rounded text-sm text-blue-800 border border-blue-100">
              <span className="font-medium">Suggested follow-up: </span>
              {analysis.recommended_follow_up}
            </div>
          )}

          {/* 9. Diagnostics */}
          {analysis.signal_summary && (
            <p className="text-xs text-gray-400 mt-4 pt-3 border-t border-gray-100">
              Raw signals — NLI contradiction score: {analysis.signal_summary.nli_contradiction_max?.toFixed(3) ?? 'n/a'} ·
              Opposite polarity: {analysis.signal_summary.polarity_opposite ? 'yes' : 'no'}
            </p>
          )}
        </>
      )}
    </div>
  );
}
