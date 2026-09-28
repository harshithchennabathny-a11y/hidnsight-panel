import React, { useState } from 'react';
import { postSubmission } from '../api';
import ErrorMessage from './ErrorMessage';

const TASK_CONTEXTS = [
  { value: 'whiteboard_design', label: 'Whiteboard Design' },
  { value: 'live_coding', label: 'Live Coding' },
  { value: 'take_home_review', label: 'Take-Home Review' },
  { value: 'pair_programming', label: 'Pair Programming' },
  { value: 'behavioral', label: 'Behavioral' },
  { value: 'system_design_discussion', label: 'System Design Discussion' },
  { value: 'other', label: 'Other' },
];

const POLARITY_COLORS = {
  positive: 'bg-green-100 text-green-800',
  negative: 'bg-red-100 text-red-800',
  mixed: 'bg-amber-100 text-amber-800',
  neutral: 'bg-gray-100 text-gray-700',
};

function toSlug(name) {
  return name
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');
}

function highlightSpan(rawText, span) {
  if (!span || !rawText.includes(span)) return rawText;
  const idx = rawText.indexOf(span);
  return (
    <>
      {rawText.slice(0, idx)}
      <mark className="bg-yellow-200 rounded px-0.5">{span}</mark>
      {rawText.slice(idx + span.length)}
    </>
  );
}

export default function SubmissionForm({ onSubmitted }) {
  const [formData, setFormData] = useState({
    candidate_slug: '', candidate_name: '', interviewer_id: '', interviewer_name: '',
    round: 1, task_context: 'whiteboard_design', reviewed_others_notes: false, feedback_text: ''
  });
  const [slugManuallyEdited, setSlugManuallyEdited] = useState(false);
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState(null);

  const handleCandidateNameChange = (e) => {
    const name = e.target.value;
    const updates = { candidate_name: name };
    if (!slugManuallyEdited) {
      updates.candidate_slug = toSlug(name);
    }
    setFormData(prev => ({ ...prev, ...updates }));
  };

  const handleSlugChange = (e) => {
    setSlugManuallyEdited(true);
    setFormData(prev => ({ ...prev, candidate_slug: e.target.value }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    setResult(null);
    try {
      const res = await postSubmission({
        ...formData, round: parseInt(formData.round, 10)
      });
      setResult(res);
      setFormData(prev => ({ ...prev, feedback_text: '', round: parseInt(prev.round) + 1 }));
      setSlugManuallyEdited(false);
      if (onSubmitted) onSubmitted();
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  };

  const charCount = formData.feedback_text.length;

  return (
    <div className="bg-white p-6 rounded-xl shadow-sm border border-gray-200">
      <h2 className="text-xl font-bold text-gray-900 mb-5">Submit Feedback</h2>
      {error && <ErrorMessage error={error} />}

      <form onSubmit={handleSubmit} className="space-y-4">
        {/* 1. Candidate name and ID */}
        <div className="grid grid-cols-2 gap-4">
          <label className="block text-sm font-medium text-gray-700">
            Candidate name
            <input
              type="text" required
              value={formData.candidate_name}
              onChange={handleCandidateNameChange}
              className="mt-1 block w-full border border-gray-300 rounded p-2 text-sm"
            />
          </label>
          <label className="block text-sm font-medium text-gray-700">
            Candidate ID
            <input
              type="text" required pattern="^[a-z0-9]+(-[a-z0-9]+)*$"
              title="Lowercase letters, digits and hyphens only"
              value={formData.candidate_slug}
              onChange={handleSlugChange}
              className="mt-1 block w-full border border-gray-300 rounded p-2 text-sm font-mono"
            />
          </label>
        </div>

        {/* 2. Your ID and Your name */}
        <div className="grid grid-cols-2 gap-4">
          <label className="block text-sm font-medium text-gray-700">
            Your ID
            <input
              type="text" required
              value={formData.interviewer_id}
              onChange={e => setFormData({ ...formData, interviewer_id: e.target.value })}
              className="mt-1 block w-full border border-gray-300 rounded p-2 text-sm"
            />
          </label>
          <label className="block text-sm font-medium text-gray-700">
            Your name
            <input
              type="text" required
              value={formData.interviewer_name}
              onChange={e => setFormData({ ...formData, interviewer_name: e.target.value })}
              className="mt-1 block w-full border border-gray-300 rounded p-2 text-sm"
            />
          </label>
        </div>

        {/* 3. Round */}
        <label className="block text-sm font-medium text-gray-700 w-32">
          Round
          <input
            type="number" required min="1" max="10"
            value={formData.round}
            onChange={e => setFormData({ ...formData, round: e.target.value })}
            className="mt-1 block w-full border border-gray-300 rounded p-2 text-sm"
          />
        </label>

        {/* 4. Task context */}
        <label className="block text-sm font-medium text-gray-700">
          Task context
          <select
            required
            value={formData.task_context}
            onChange={e => setFormData({ ...formData, task_context: e.target.value })}
            className="mt-1 block w-full border border-gray-300 rounded p-2 text-sm bg-white"
          >
            {TASK_CONTEXTS.map(c => (
              <option key={c.value} value={c.value}>{c.label}</option>
            ))}
          </select>
        </label>

        {/* 5. Checkbox */}
        <label className="flex items-center gap-2 text-sm text-gray-700">
          <input
            type="checkbox"
            checked={formData.reviewed_others_notes}
            onChange={e => setFormData({ ...formData, reviewed_others_notes: e.target.checked })}
            className="rounded text-blue-600"
          />
          I read other interviewers&apos; notes on this candidate before writing this.
        </label>

        {/* 6. Feedback with live counter */}
        <label className="block text-sm font-medium text-gray-700">
          Feedback
          <textarea
            required minLength="20" maxLength="4000" rows="6"
            value={formData.feedback_text}
            onChange={e => setFormData({ ...formData, feedback_text: e.target.value })}
            className="mt-1 block w-full border border-gray-300 rounded p-2 text-sm"
            placeholder="Describe the candidate's performance across the competencies you assessed…"
          />
          <div className={`text-right text-xs mt-1 ${charCount < 20 ? 'text-red-500' : charCount > 3800 ? 'text-amber-600' : 'text-gray-400'}`}>
            {charCount} / 4000
          </div>
        </label>

        <button
          type="submit"
          disabled={submitting}
          className="w-full bg-blue-600 text-white font-semibold py-2 rounded hover:bg-blue-700 disabled:opacity-50 transition-colors"
        >
          {submitting ? 'Submitting…' : 'Submit feedback'}
        </button>
      </form>

      {/* Success: show extracted facts */}
      {result && (
        <div className="mt-6 border-t border-gray-200 pt-5">
          <h3 className="text-sm font-semibold text-gray-700 mb-3">
            {result.facts.length} fact{result.facts.length !== 1 ? 's' : ''} extracted from your feedback:
          </h3>
          <ul className="space-y-3">
            {result.facts.map((f, i) => (
              <li key={i} className="bg-gray-50 rounded-lg p-3 border border-gray-200 text-sm">
                <div className="flex items-center gap-2 mb-1">
                  <span className="font-medium text-gray-800 capitalize">{f.competency.replace(/_/g, ' ')}</span>
                  <span className={`text-xs px-1.5 py-0.5 rounded font-medium ${POLARITY_COLORS[f.polarity] || 'bg-gray-100'}`}>
                    {f.polarity}
                  </span>
                </div>
                <p className="text-xs text-gray-600 leading-relaxed">
                  {/* Highlight the evidence span in the original feedback */}
                  {highlightSpan(formData.candidate_name ? result.facts[0]?.claim_raw || f.claim_raw : f.claim_raw, f.claim_raw)}
                </p>
                {f.claim_raw && (
                  <p className="text-xs text-gray-500 mt-1 italic">Evidence: &ldquo;{f.claim_raw}&rdquo;</p>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
