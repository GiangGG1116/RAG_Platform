import { useState } from 'react';
import type { AppSettings } from './services/api';
import { SettingsPanel } from './components/SettingsPanel';
import { DocManager } from './components/DocManager';
import { ChatInterface } from './components/ChatInterface';

function App() {
  const [activeTab, setActiveTab] = useState<'chat' | 'documents'>('chat');
  const [settings, setSettings] = useState<AppSettings>({
    apiUrl: (() => {
      // 1. Local development (standard docker-compose / dev server)
      if (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') {
        return window.location.origin === 'http://localhost:3000' 
          ? 'http://localhost:8000' 
          : `${window.location.protocol}//${window.location.hostname}:8000`;
      }
      // 2. Kubernetes Ingress (using domain names)
      if (window.location.hostname === 'rag-app.example.com') {
        return `${window.location.protocol}//rag-api.example.com`;
      }
      // 3. Minikube NodePort fallback (Frontend is 30659, API Gateway is 30199)
      if (window.location.port === '30659') {
        return `${window.location.protocol}//${window.location.hostname}:30199`;
      }
      // 4. Default fallback
      return `${window.location.protocol}//${window.location.hostname}:8000`;
    })(),
    apiKey: 'default-api-key-change-me',
    tenantId: 'default',
    topK: 5,
    rerank: true,
    stream: true,
  });

  return (
    <div className="app-container">
      {/* Sidebar Panel */}
      <div className="sidebar glass-panel">
        <div>
          <div className="logo-container">
            <div className="logo-icon">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#ffffff" strokeWidth="2.5">
                <path strokeLinecap="round" strokeLinejoin="round" d="M9.813 15.904L9 21l3.582-1.395A9.011 9.011 0 0012 18h-.188M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
              </svg>
            </div>
            <div className="logo-text">RAG Platform</div>
          </div>

          <div className="nav-menu">
            <button
              className={`nav-item ${activeTab === 'chat' ? 'active' : ''}`}
              onClick={() => setActiveTab('chat')}
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path strokeLinecap="round" strokeLinejoin="round" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
              </svg>
              Chat Console
            </button>
            <button
              className={`nav-item ${activeTab === 'documents' ? 'active' : ''}`}
              onClick={() => setActiveTab('documents')}
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path strokeLinecap="round" strokeLinejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
              Document Space
            </button>
          </div>
        </div>

        {/* Configurations Drawer (Rendered inline inside sidebar bottom portion) */}
        <SettingsPanel settings={settings} onChange={setSettings} />
      </div>

      {/* Main Panel */}
      <div style={{ position: 'relative', overflow: 'hidden', height: '100vh' }}>
        {activeTab === 'chat' ? (
          <ChatInterface settings={settings} />
        ) : (
          <DocManager settings={settings} />
        )}
      </div>
    </div>
  );
}

export default App;
