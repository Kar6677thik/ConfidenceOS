import { Component } from 'react';

export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, info) {
    console.error('[ConfidenceOS] Render error:', error, info.componentStack);
  }

  reset() {
    this.setState({ hasError: false, error: null });
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="flex-1 flex flex-col items-center justify-center gap-4 p-8 text-center bg-[var(--bg-base)]">
          <span className="material-symbols-outlined text-[64px] text-[var(--critical)]">error</span>
          <p className="text-[18px] font-semibold text-[var(--text)]">View failed to render</p>
          <p className="caption-mono text-[var(--text-muted)] max-w-sm leading-relaxed">
            An unexpected error occurred in this panel. The rest of the app is still operational.
          </p>
          {this.state.error?.message && (
            <p className="caption-mono text-[var(--text-dim)] max-w-sm font-data text-[12px]">
              {this.state.error.message}
            </p>
          )}
          <button
            onClick={() => this.reset()}
            className="industrial-control text-[var(--safe-text)] border-[var(--safe-text)]/60 mt-2"
          >
            Retry
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
