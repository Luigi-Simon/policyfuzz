import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import { dataMode, apiBase } from './api/config';
import { HttpTransport } from './api/httpTransport';
import { MockTransport } from './api/mockTransport';
import './styles.css';

const transport = dataMode === 'mock' ? new MockTransport() : new HttpTransport(apiBase);
const query = new URLSearchParams(window.location.search);
ReactDOM.createRoot(document.getElementById('root')!).render(<React.StrictMode><App transport={transport} initialAgentRunId={query.get('mirofish_run') ?? undefined}/></React.StrictMode>);
