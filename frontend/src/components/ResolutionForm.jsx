import React, { useState } from 'react';
import { postResolution } from '../api';

const RESOLUTION_LABELS = {
  CONFIRMS_CLAIM_A: 'The follow-up response is consistent with Claim A',
  CONFIRMS_CLAIM_B: 'The follow-up response is consistent with Claim B',
  BOTH_HOLD_UNDER_DIFFERENT_CONTEXT: 'Both claims hold, under different conditions',
  NEW_INFORMATION_UNRESOLVED: 'New information came up that is not yet resolved',
  UNCLEAR: 'The response did not clearly settle it',
};

const TASK_CONTEXT_LABELS = {
  whiteboard_design: 'Whiteboard Design',
  live_coding: 'Live Coding',
  take_home_review: 'Take-Home Review',
  pair_programming: 'Pair Programming',
  behavioral: 'Behavioral',
  system_design_discussion: 'System Design Discussion',
  other: 'Other',
};

function ContextSelect({ label, value, onChange }) {
  return (
    <label className="block text-sm font-medium text-gray-700">
      {label}
      <select value={value} onChange={e => onChange(e.target.value)} required
        className="mt-1 block w-full border border-gray-300 rounded-md p-2 text-sm bg-white">
        <option value="">Select context…</option>
        {Object.entries(TASK_CONTEXT_LABELS).map(([v, l]) => (
          <option key={v} value={v}>{l}</option>
        ))}
      </select>
    </label>
  );
}

export default function ResolutionForm({ disagreementId, onResolved }) {
  const [type, setType] = useState('');
  const [note, setNote] = useState('');
  const [ctxA, setCtxA] = useState('');
  const [ctxB, setCtxB] = useState('');
  const [error, setError] = useState(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const needsContexts = type === 'BOTH_HOLD_UNDER_DIFFERENT_CONTEXT';

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (note.length < 10) { setError('Notes must be at least 10 characters'); return; }
    
    setIsSubmitting(true);
    setError(null);
    try {
      const body = { resolution_type: type, note };
      if (needsContexts) { body.context_a = ctxA; body.context_b = ctxB; }
      const updated = await postResolution(disagreementId, body);
      onResolved(updated);
    } catch (err) { 
      setError(err.message); 
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="mt-4 space-y-3 bg-gray-50 p-4 rounded-lg border border-gray-200">
      <label className="block text-sm font-medium text-gray-700">
        What happened when the follow-up was asked?
        <select value={type} onChange={e => setType(e.target.value)} required
          className="mt-1 block w-full border border-gray-300 rounded-md p-2 text-sm bg-white">
          <option value="">Select…</option>
          {Object.entries(RESOLUTION_LABELS).map(([v, l]) => (
            <option key={v} value={v}>{l}</option>
          ))}
        </select>
      </label>

      {needsContexts && (
        <div className="grid grid-cols-2 gap-3">
          <ContextSelect label="Context for Claim A" value={ctxA} onChange={setCtxA} />
          <ContextSelect label="Context for Claim B" value={ctxB} onChange={setCtxB} />
        </div>
      )}

      <label className="block text-sm font-medium text-gray-700">
        Notes
        <textarea value={note} onChange={e => setNote(e.target.value)} required minLength={10} rows={3}
          className="mt-1 block w-full border border-gray-300 rounded-md p-2 text-sm" />
      </label>

      {error && <p className="text-sm text-red-600 bg-red-50 p-2 rounded">{error}</p>}
      <button type="submit" disabled={isSubmitting} className="px-4 py-2 bg-blue-600 text-white text-sm rounded-md hover:bg-blue-700 disabled:opacity-50">
        {isSubmitting ? 'Recording...' : 'Record resolution'}
      </button>
    </form>
  );
}
