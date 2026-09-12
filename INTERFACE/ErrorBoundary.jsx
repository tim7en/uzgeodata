import React from 'react';

/**
 * A blank page tells nobody anything. When a render throws, show what threw and
 * where, so the next report is a message rather than "it is not loading".
 */
export default class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { failure: null };
  }

  static getDerivedStateFromError(failure) {
    return { failure };
  }

  componentDidCatch(failure, info) {
    console.error('Landing map failed to render', failure, info);
  }

  render() {
    if (!this.state.failure) return this.props.children;
    return <main className="land-state">
      <h1>This page stopped.</h1>
      <p>{String(this.state.failure?.message || this.state.failure)}</p>
      <p><a href="/guide.html">Get help or download basin data directly</a></p>
    </main>;
  }
}
