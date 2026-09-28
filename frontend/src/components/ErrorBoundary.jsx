import React from 'react';

export default class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    console.error("ErrorBoundary caught an error:", error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="p-6 m-4 max-w-xl mx-auto bg-red-50 border border-red-200 rounded-lg text-red-900">
          <h2 className="text-lg font-bold mb-2">Something went wrong</h2>
          <p className="mb-4">The application encountered an unhandled error.</p>
          <pre className="p-4 bg-red-100 rounded text-sm overflow-auto whitespace-pre-wrap">
            {this.state.error?.message || String(this.state.error)}
          </pre>
          <button 
            onClick={() => window.location.reload()}
            className="mt-4 px-4 py-2 bg-red-600 text-white rounded hover:bg-red-700"
          >
            Reload Application
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
