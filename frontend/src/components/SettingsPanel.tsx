import React, { useState } from 'react';
import type { AppSettings } from '../services/api';

interface SettingsPanelProps {
  settings: AppSettings;
  onChange: (settings: AppSettings) => void;
}

export const SettingsPanel: React.FC<SettingsPanelProps> = ({ settings, onChange }) => {
  const [showApiKey, setShowApiKey] = useState(false);

  const handleChange = (key: keyof AppSettings, value: any) => {
    onChange({
      ...settings,
      [key]: value,
    });
  };

  return (
    <div className="settings-drawer">
      <div className="settings-section-title">API Connection</div>
      
      <div className="form-group">
        <label className="form-label">Gateway URL</label>
        <input
          type="text"
          className="form-input"
          value={settings.apiUrl}
          onChange={(e) => handleChange('apiUrl', e.target.value)}
          placeholder="http://localhost:8000"
        />
      </div>

      <div className="form-group">
        <label className="form-label">API Key</label>
        <div style={{ position: 'relative' }}>
          <input
            type={showApiKey ? 'text' : 'password'}
            className="form-input"
            value={settings.apiKey}
            onChange={(e) => handleChange('apiKey', e.target.value)}
            placeholder="X-API-Key"
            style={{ paddingRight: '40px' }}
          />
          <button
            type="button"
            onClick={() => setShowApiKey(!showApiKey)}
            style={{
              position: 'absolute',
              right: '12px',
              top: '50%',
              transform: 'translateY(-50%)',
              background: 'none',
              border: 'none',
              color: 'var(--text-secondary)',
              cursor: 'pointer',
              fontSize: '12px'
            }}
          >
            {showApiKey ? 'Hide' : 'Show'}
          </button>
        </div>
      </div>

      <div className="settings-section-title">RAG Engine Parameters</div>

      <div className="form-group">
        <label className="form-label">Tenant ID</label>
        <input
          type="text"
          className="form-input"
          value={settings.tenantId}
          onChange={(e) => handleChange('tenantId', e.target.value)}
          placeholder="default"
        />
      </div>

      <div className="form-group">
        <label className="form-label">Top K Chunks ({settings.topK})</label>
        <input
          type="range"
          min="1"
          max="30"
          value={settings.topK}
          onChange={(e) => handleChange('topK', parseInt(e.target.value, 10))}
          style={{
            width: '100%',
            accentColor: 'var(--accent-primary)',
            background: 'var(--bg-tertiary)',
            height: '6px',
            borderRadius: '3px',
            cursor: 'pointer'
          }}
        />
      </div>

      <div className="toggle-container">
        <div>
          <div className="form-label" style={{ marginBottom: '2px' }}>Rerank Chunks</div>
          <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Use cross-encoder to sort results</div>
        </div>
        <label className="switch">
          <input
            type="checkbox"
            checked={settings.rerank}
            onChange={(e) => handleChange('rerank', e.target.checked)}
          />
          <span className="slider"></span>
        </label>
      </div>

      <div className="toggle-container">
        <div>
          <div className="form-label" style={{ marginBottom: '2px' }}>Streaming</div>
          <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Generate answer token-by-token</div>
        </div>
        <label className="switch">
          <input
            type="checkbox"
            checked={settings.stream}
            onChange={(e) => handleChange('stream', e.target.checked)}
          />
          <span className="slider"></span>
        </label>
      </div>
      
      <div style={{ marginTop: 'auto', paddingTop: '20px', borderTop: '1px solid var(--border-color)', fontSize: '11px', color: 'var(--text-muted)', textAlign: 'center' }}>
        RAG Microservices Platform v1.0.0
      </div>
    </div>
  );
};
