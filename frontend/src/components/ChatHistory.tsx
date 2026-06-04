import React, { useState } from 'react';
import type { ConversationSummary } from '../services/api';

export type { ConversationSummary };

function formatRelativeTime(dateStr: string): string {
  const date = new Date(dateStr);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffSecs = Math.floor(diffMs / 1000);
  const diffMins = Math.floor(diffSecs / 60);
  const diffHours = Math.floor(diffMins / 60);
  const diffDays = Math.floor(diffHours / 24);

  if (diffSecs < 60) return 'Just now';
  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  if (diffDays === 1) return 'Yesterday';
  if (diffDays < 7) return `${diffDays}d ago`;
  return date.toLocaleDateString('vi-VN', { day: '2-digit', month: '2-digit' });
}

interface ChatHistoryProps {
  conversations: ConversationSummary[];
  activeConversationId: string | null;
  loading: boolean;
  onSelect: (conv: ConversationSummary) => void;
  onDelete: (id: string) => void;
  onNewChat: () => void;
}

export const ChatHistory: React.FC<ChatHistoryProps> = ({
  conversations,
  activeConversationId,
  loading,
  onSelect,
  onDelete,
  onNewChat,
}) => {
  const [hoveringId, setHoveringId] = useState<string | null>(null);
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);

  const handleDeleteClick = (e: React.MouseEvent, id: string) => {
    e.stopPropagation();
    setConfirmDeleteId(id);
  };

  const handleConfirmDelete = (e: React.MouseEvent, id: string) => {
    e.stopPropagation();
    onDelete(id);
    setConfirmDeleteId(null);
  };

  const handleCancelDelete = (e: React.MouseEvent) => {
    e.stopPropagation();
    setConfirmDeleteId(null);
  };

  return (
    <div className="chat-history-panel">
      <div className="chat-history-header">
        <div className="chat-history-title">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          History
        </div>
        <button className="new-chat-btn" onClick={onNewChat} title="New conversation">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
            <line x1="12" y1="5" x2="12" y2="19" />
            <line x1="5" y1="12" x2="19" y2="12" />
          </svg>
        </button>
      </div>

      <div className="chat-history-list">
        {loading ? (
          <div className="chat-history-empty">
            <svg className="spinner" viewBox="0 0 50 50" style={{ width: '24px', height: '24px' }}>
              <circle className="path" cx="25" cy="25" r="20" fill="none" strokeWidth="6" />
            </svg>
            <span>Loading…</span>
          </div>
        ) : conversations.length === 0 ? (
          <div className="chat-history-empty">
            <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
              <path strokeLinecap="round" strokeLinejoin="round" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
            </svg>
            <span>No conversations yet</span>
          </div>
        ) : (
          conversations.map((conv) => (
            <div
              key={conv.id}
              className={`chat-history-item ${activeConversationId === conv.id ? 'active' : ''}`}
              onClick={() => onSelect(conv)}
              onMouseEnter={() => setHoveringId(conv.id)}
              onMouseLeave={() => {
                setHoveringId(null);
                if (confirmDeleteId === conv.id) setConfirmDeleteId(null);
              }}
            >
              <div className="chat-history-item-icon">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
                </svg>
              </div>
              <div className="chat-history-item-content">
                <div className="chat-history-item-title">{conv.title}</div>
                <div className="chat-history-item-meta">
                  <span>{conv.message_count} msgs</span>
                  <span className="chat-history-item-time">{formatRelativeTime(conv.updated_at)}</span>
                </div>
              </div>

              {confirmDeleteId === conv.id ? (
                <div className="chat-history-confirm-delete" onClick={(e) => e.stopPropagation()}>
                  <button
                    className="chat-history-delete-confirm-btn"
                    onClick={(e) => handleConfirmDelete(e, conv.id)}
                    title="Confirm delete"
                  >
                    <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                      <polyline points="20 6 9 17 4 12" />
                    </svg>
                  </button>
                  <button
                    className="chat-history-delete-cancel-btn"
                    onClick={handleCancelDelete}
                    title="Cancel"
                  >
                    <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                      <line x1="18" y1="6" x2="6" y2="18" />
                      <line x1="6" y1="6" x2="18" y2="18" />
                    </svg>
                  </button>
                </div>
              ) : (
                hoveringId === conv.id && (
                  <button
                    className="chat-history-delete-btn"
                    onClick={(e) => handleDeleteClick(e, conv.id)}
                    title="Delete conversation"
                  >
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <polyline points="3 6 5 6 21 6" />
                      <path d="M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a1 1 0 011-1h4a1 1 0 011 1v2" />
                    </svg>
                  </button>
                )
              )}
            </div>
          ))
        )}
      </div>

      {/* DB badge */}
      <div style={{
        padding: '10px 16px',
        borderTop: '1px solid var(--border-color)',
        display: 'flex',
        alignItems: 'center',
        gap: '6px',
        fontSize: '11px',
        color: 'var(--text-muted)',
      }}>
        <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <ellipse cx="12" cy="5" rx="9" ry="3" />
          <path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3" />
          <path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5" />
        </svg>
        Saved to PostgreSQL
      </div>
    </div>
  );
};
