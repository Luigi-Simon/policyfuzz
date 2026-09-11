import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import { dataMode, apiBase } from './api/config';
import { HttpTransport } from './api/httpTransport';
import { MockTransport } from './api/mockTransport';
import './styles.css';

const root = ReactDOM.createRoot(document.getElementById('root')!);
if (window.location.pathname === '/v2' || window.location.pathname === '/v2/') {
  const WorkflowApp = React.lazy(() => import('./v2/WorkflowApp').then(module => ({ default: module.WorkflowApp })));
  root.render(<React.StrictMode><React.Suspense fallback={<p role="status">Loading PolicyFuzz v2…</p>}><WorkflowApp /></React.Suspense></React.StrictMode>);
} else if (window.location.pathname === '/v2/fixture') {
  const V2App = React.lazy(() => import('./v2/V2App').then(module => ({ default: module.V2App })));
  root.render(<React.StrictMode><React.Suspense fallback={<p role="status">Loading PolicyFuzz v2…</p>}><V2App /></React.Suspense></React.StrictMode>);
} else {
  const transport = dataMode === 'mock' ? new MockTransport() : new HttpTransport(apiBase);
  const query = new URLSearchParams(window.location.search);
  root.render(<React.StrictMode><App transport={transport} initialRunId={query.get('run_id') ?? undefined} initialAgentRunId={query.get('mirofish_run') ?? undefined}/></React.StrictMode>);
}
