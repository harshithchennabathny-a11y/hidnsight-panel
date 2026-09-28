import React from 'react';

export default function ErrorMessage({ error }) {
  if (!error) return null;
  return (
    <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded relative mb-4" role="alert">
      <span className="block sm:inline">{error}</span>
    </div>
  );
}
