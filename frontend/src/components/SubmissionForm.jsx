import React, { useState } from 'react';
import { postSubmission } from '../api';
import ErrorMessage from './ErrorMessage';

const TASK_CONTEXTS = [
  'whiteboard_design', 'live_coding', 'take_home_review',
  'pair_programming', 'behavioral', 'system_design_discussion', 'other'
];

export default function SubmissionForm({ onSubmitted }) {
  const [formData, setFormData] = useState({
    candidate_slug: '', candidate_name: '', interviewer_id: '', interviewer_name: '',
    round: 1, task_context: 'whiteboard_design', reviewed_others_notes: false, feedback_text: ''
  });
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const res = await postSubmission({
        ...formData, round: parseInt(formData.round, 10)
      });
      alert(`Submission successful! ${res.facts.length} facts extracted.`);
      setFormData(prev => ({ ...prev, feedback_text: '', round: parseInt(prev.round) + 1 }));
      if (onSubmitted) onSubmitted();
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="bg-white p-6 rounded-xl shadow-sm border border-gray-200">
      <h2 className="text-xl font-bold text-gray-900 mb-5">Submit Feedback</h2>
      {error && <ErrorMessage error={error} />}
      <form onSubmit={handleSubmit} className="space-y-4">
        <div className="grid grid-cols-2 gap-4">
          <label className="block text-sm font-medium text-gray-700">
            Candidate Slug
            <input type="text" required pattern="^[a-z0-9]+(-[a-z0-9]+)*$" value={formData.candidate_slug} onChange={e => setFormData({...formData, candidate_slug: e.target.value})} className="mt-1 block w-full border border-gray-300 rounded p-2" />
          </label>
          <label className="block text-sm font-medium text-gray-700">
            Candidate Name
            <input type="text" required value={formData.candidate_name} onChange={e => setFormData({...formData, candidate_name: e.target.value})} className="mt-1 block w-full border border-gray-300 rounded p-2" />
          </label>
        </div>
        <div className="grid grid-cols-2 gap-4">
          <label className="block text-sm font-medium text-gray-700">
            Interviewer ID
            <input type="text" required value={formData.interviewer_id} onChange={e => setFormData({...formData, interviewer_id: e.target.value})} className="mt-1 block w-full border border-gray-300 rounded p-2" />
          </label>
          <label className="block text-sm font-medium text-gray-700">
            Interviewer Name
            <input type="text" required value={formData.interviewer_name} onChange={e => setFormData({...formData, interviewer_name: e.target.value})} className="mt-1 block w-full border border-gray-300 rounded p-2" />
          </label>
        </div>
        <div className="grid grid-cols-3 gap-4">
          <label className="block text-sm font-medium text-gray-700">
            Round (1-10)
            <input type="number" required min="1" max="10" value={formData.round} onChange={e => setFormData({...formData, round: e.target.value})} className="mt-1 block w-full border border-gray-300 rounded p-2" />
          </label>
          <label className="block text-sm font-medium text-gray-700 col-span-2">
            Task Context
            <select required value={formData.task_context} onChange={e => setFormData({...formData, task_context: e.target.value})} className="mt-1 block w-full border border-gray-300 rounded p-2 bg-white">
              {TASK_CONTEXTS.map(c => <option key={c} value={c}>{c.replace(/_/g, ' ')}</option>)}
            </select>
          </label>
        </div>
        <label className="flex items-center gap-2 text-sm text-gray-700">
          <input type="checkbox" checked={formData.reviewed_others_notes} onChange={e => setFormData({...formData, reviewed_others_notes: e.target.checked})} className="rounded text-blue-600" />
          I read other interviewers' notes before writing this
        </label>
        <label className="block text-sm font-medium text-gray-700">
          Feedback Text
          <textarea required minLength="20" maxLength="4000" rows="5" value={formData.feedback_text} onChange={e => setFormData({...formData, feedback_text: e.target.value})} className="mt-1 block w-full border border-gray-300 rounded p-2" />
        </label>
        <button type="submit" disabled={submitting} className="w-full bg-blue-600 text-white font-semibold py-2 rounded hover:bg-blue-700 disabled:opacity-50">
          {submitting ? 'Submitting...' : 'Submit Feedback'}
        </button>
      </form>
    </div>
  );
}
