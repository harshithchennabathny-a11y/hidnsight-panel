import React, { useState, useEffect } from 'react';
import { getCandidates } from './api';
import SubmissionForm from './components/SubmissionForm';
import CandidateView from './components/CandidateView';
import DisagreementsPanel from './components/DisagreementsPanel';
import CalibrationPanel from './components/CalibrationPanel';

export default function App() {
  const [candidates, setCandidates] = useState([]);
  const [selectedSlug, setSelectedSlug] = useState(null);
  const [view, setView] = useState('submit'); // 'submit', 'candidate', 'disagreements', 'calibration'
  const [search, setSearch] = useState('');

  const fetchCandidates = () => {
    getCandidates().then(setCandidates).catch(console.error);
  };

  useEffect(() => {
    fetchCandidates();
  }, []);

  const filteredCandidates = candidates.filter(c => 
    c.display_name.toLowerCase().includes(search.toLowerCase()) ||
    c.slug.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div className="min-h-screen bg-gray-100 font-sans text-gray-900">
      <header className="bg-white shadow-sm sticky top-0 z-10">
        <div className="max-w-6xl mx-auto px-4 py-4 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 bg-blue-600 text-white rounded flex items-center justify-center font-bold text-xl">P</div>
            <h1 className="text-xl font-bold text-gray-900">Panel</h1>
          </div>
          <nav className="flex gap-4">
            <button onClick={() => setView('submit')} className={`text-sm font-medium ${view === 'submit' ? 'text-blue-600' : 'text-gray-500 hover:text-gray-900'}`}>
              Submit Feedback
            </button>
            <button onClick={() => setView('candidate')} className={`text-sm font-medium ${view === 'candidate' ? 'text-blue-600' : 'text-gray-500 hover:text-gray-900'}`}>
              Interviewer Briefing
            </button>
            <button onClick={() => setView('disagreements')} className={`text-sm font-medium ${view === 'disagreements' ? 'text-blue-600' : 'text-gray-500 hover:text-gray-900'}`}>
              Coordinator View
            </button>
            <button onClick={() => setView('calibration')} className={`text-sm font-medium ${view === 'calibration' ? 'text-blue-600' : 'text-gray-500 hover:text-gray-900'}`}>
              Calibration
            </button>
          </nav>
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-4 py-8 grid grid-cols-1 md:grid-cols-4 gap-8">
        <aside className="md:col-span-1">
          <div className="flex items-center justify-between mb-2">
            <h2 className="text-sm font-bold text-gray-400 uppercase tracking-wider">Candidates</h2>
            <span className="text-xs font-medium text-gray-500">{filteredCandidates.length} of {candidates.length}</span>
          </div>
          <div className="mb-3">
            <input
              type="text"
              placeholder="Search 1,000 candidates..."
              value={search}
              onChange={e => setSearch(e.target.value)}
              className="w-full text-xs px-2.5 py-1.5 border border-gray-300 rounded focus:outline-none focus:ring-1 focus:ring-blue-500 focus:border-blue-500"
            />
          </div>
          {candidates.length === 0 ? (
            <p className="text-sm text-gray-500">No candidates yet.</p>
          ) : filteredCandidates.length === 0 ? (
            <p className="text-xs text-gray-400 py-2">No matching candidates.</p>
          ) : (
            <ul className="space-y-1.5 max-h-[75vh] overflow-y-auto pr-1">
              {filteredCandidates.slice(0, 100).map(c => (
                <li key={c.slug}>
                  <button onClick={() => setSelectedSlug(c.slug)} 
                    className={`w-full text-left px-3 py-2 rounded border transition-colors ${selectedSlug === c.slug ? 'bg-blue-50 border-blue-300 text-blue-800' : 'bg-white border-gray-200 hover:border-gray-300 text-gray-700'}`}>
                    <div className="font-medium text-sm truncate">{c.display_name}</div>
                    <div className="text-xs text-gray-500 mt-0.5 flex justify-between">
                      <span>Rounds: {c.round_count}</span>
                      {c.open_disagreement_count > 0 && <span className="text-orange-600 font-semibold">{c.open_disagreement_count} open</span>}
                    </div>
                  </button>
                </li>
              ))}
              {filteredCandidates.length > 100 && (
                <li className="text-center py-2 text-xs text-gray-400">
                  Showing top 100 matches. Refine search for more.
                </li>
              )}
            </ul>
          )}
        </aside>
        
        <section className="md:col-span-3">
          {view === 'submit' && <SubmissionForm onSubmitted={fetchCandidates} />}
          {view === 'calibration' && <CalibrationPanel />}
          {view === 'candidate' && (
            selectedSlug ? <CandidateView slug={selectedSlug} /> : <div className="text-gray-500 mt-10 text-center">Select a candidate from the sidebar.</div>
          )}
          {view === 'disagreements' && (
            selectedSlug ? <DisagreementsPanel slug={selectedSlug} /> : <div className="text-gray-500 mt-10 text-center">Select a candidate from the sidebar.</div>
          )}
        </section>
      </main>
    </div>
  );
}
