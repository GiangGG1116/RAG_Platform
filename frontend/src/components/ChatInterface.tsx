import React, { useState, useEffect, useRef } from 'react';
import type { AppSettings, Citation } from '../services/api';
import { queryRAGStream, queryRAG } from '../services/api';

interface Message {
  id: string;
  role: 'user' | 'assistant';
  text: string;
  statusText?: string;
  citations?: Citation[];
  model?: string;
  latency_ms?: number;
  loading?: boolean;
}

interface ChatInterfaceProps {
  settings: AppSettings;
}

export const ChatInterface: React.FC<ChatInterfaceProps> = ({ settings }) => {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [conversationId, setConversationId] = useState<string | null>(null);
  
  // Selected citation for modal detail view
  const [selectedCitation, setSelectedCitation] = useState<Citation | null>(null);

  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const handleNewChat = () => {
    setMessages([]);
    setConversationId(null);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim()) return;

    const userQuestion = input;
    setInput('');

    const userMsgId = Math.random().toString(36).substring(7);
    const assistantMsgId = Math.random().toString(36).substring(7);

    // Append User Message
    const newUserMsg: Message = {
      id: userMsgId,
      role: 'user',
      text: userQuestion,
    };

    // Append Assistant Placeholder Message
    const newAssistantMsg: Message = {
      id: assistantMsgId,
      role: 'assistant',
      text: '',
      statusText: 'Analyzing query...',
      loading: true,
    };

    setMessages((prev) => [...prev, newUserMsg, newAssistantMsg]);

    if (settings.stream) {
      // ── Streaming SSE Execution ────────────────────────────────
      try {
        await queryRAGStream(
          settings,
          userQuestion,
          conversationId,
          {
            onStatus: (statusText) => {
              setMessages((prev) =>
                prev.map((msg) =>
                  msg.id === assistantMsgId
                    ? { ...msg, statusText }
                    : msg
                )
              );
            },
            onToken: (token) => {
              setMessages((prev) =>
                prev.map((msg) =>
                  msg.id === assistantMsgId
                    ? { ...msg, text: msg.text + token, statusText: undefined }
                    : msg
                )
              );
            },
            onCitations: (citations) => {
              setMessages((prev) =>
                prev.map((msg) =>
                  msg.id === assistantMsgId
                    ? { ...msg, citations }
                    : msg
                )
              );
            },
            onDone: (doneData) => {
              if (doneData.conversation_id) {
                setConversationId(doneData.conversation_id);
              }
              setMessages((prev) =>
                prev.map((msg) =>
                  msg.id === assistantMsgId
                    ? {
                        ...msg,
                        model: doneData.model,
                        latency_ms: doneData.latency_ms,
                        loading: false,
                        statusText: undefined,
                      }
                    : msg
                )
              );
            },
            onError: (errorText) => {
              setMessages((prev) =>
                prev.map((msg) =>
                  msg.id === assistantMsgId
                    ? {
                        ...msg,
                        text: msg.text + `\n\n[Error: ${errorText}]`,
                        loading: false,
                        statusText: undefined,
                      }
                    : msg
                )
              );
            },
          }
        );
      } catch (err: any) {
        setMessages((prev) =>
          prev.map((msg) =>
            msg.id === assistantMsgId
              ? {
                  ...msg,
                  text: `Failed to query RAG. ${err.message || 'Unknown network error.'}`,
                  loading: false,
                  statusText: undefined,
                }
              : msg
          )
        );
      }
    } else {
      // ── Blocking JSON Execution ────────────────────────────────
      try {
        const response = await queryRAG(settings, userQuestion, conversationId);
        if (response.conversation_id) {
          setConversationId(response.conversation_id);
        }
        setMessages((prev) =>
          prev.map((msg) =>
            msg.id === assistantMsgId
              ? {
                  ...msg,
                  text: response.answer,
                  citations: response.citations,
                  model: response.model,
                  latency_ms: response.latency_ms,
                  loading: false,
                  statusText: undefined,
                }
              : msg
          )
        );
      } catch (err: any) {
        setMessages((prev) =>
          prev.map((msg) =>
            msg.id === assistantMsgId
              ? {
                  ...msg,
                  text: `Failed to query RAG. ${err.message || 'Unknown error.'}`,
                  loading: false,
                  statusText: undefined,
                }
              : msg
          )
        );
      }
    }
  };

  return (
    <div className="chat-container">
      {/* Header */}
      <div className="chat-header">
        <div>
          <h2>RAG Chat Interface</h2>
          <div style={{ fontSize: '13px', color: 'var(--text-secondary)', marginTop: '2px' }}>
            {conversationId ? `Active Conversation: ${conversationId}` : 'Stateless multi-turn mode'}
          </div>
        </div>
        <button className="btn btn-secondary" onClick={handleNewChat}>
          + New Conversation
        </button>
      </div>

      {/* Messages Window */}
      <div className="chat-messages">
        {messages.length === 0 ? (
          <div className="empty-state">
            <div className="logo-icon" style={{ width: '60px', height: '60px', borderRadius: '16px', marginBottom: '24px' }}>
              <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path strokeLinecap="round" strokeLinejoin="round" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
              </svg>
            </div>
            <h2 style={{ fontSize: '24px', fontWeight: '700', marginBottom: '8px' }}>Ask RAG Anything</h2>
            <p style={{ maxWidth: '480px', fontSize: '14px', color: 'var(--text-secondary)', lineHeight: '1.5' }}>
              Submit queries grounded in your ingested documents. The engine will retrieve context, rerank sources, and write a detailed response citing exact matches.
            </p>
          </div>
        ) : (
          messages.map((msg) => (
            <div key={msg.id} className={`message ${msg.role}`}>
              <div className="message-avatar">
                {msg.role === 'user' ? 'U' : 'AI'}
              </div>
              <div style={{ display: 'flex', flexDirection: 'column' }}>
                <div className="message-bubble">
                  {msg.statusText && (
                    <div style={{ display: 'flex', alignItems: 'center', gap: '10px', color: 'var(--text-secondary)', fontSize: '13px', fontStyle: 'italic' }}>
                      <svg className="spinner" viewBox="0 0 50 50" style={{ width: '16px', height: '16px' }}>
                        <circle className="path" cx="25" cy="25" r="20" fill="none" strokeWidth="6"></circle>
                      </svg>
                      {msg.statusText}
                    </div>
                  )}
                  {msg.text && <div className="message-text">{msg.text}</div>}
                  
                  {/* Citations section */}
                  {msg.citations && msg.citations.length > 0 && (
                    <div className="citations-list">
                      {msg.citations.map((cite, index) => (
                        <div
                          key={index}
                          className="citation-chip"
                          onClick={() => setSelectedCitation(cite)}
                        >
                          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <path strokeLinecap="round" strokeLinejoin="round" d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" />
                          </svg>
                          [{index + 1}] {cite.document_title}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
                
                {/* Meta details (latency, model) */}
                {(msg.latency_ms !== undefined || msg.model) && (
                  <div className="message-meta">
                    {msg.model && <span>Model: {msg.model}</span>}
                    {msg.latency_ms !== undefined && <span>Latency: {msg.latency_ms}ms</span>}
                  </div>
                )}
              </div>
            </div>
          ))
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input area */}
      <div className="chat-input-area">
        <form onSubmit={handleSubmit} className="chat-form">
          <input
            type="text"
            className="form-input"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Type your question..."
            disabled={messages.some((m) => m.loading)}
            style={{ borderRadius: 'var(--radius-md)', padding: '16px 20px', fontSize: '15px' }}
          />
          <button
            type="submit"
            className="btn btn-primary"
            style={{ padding: '0 24px', flexShrink: 0 }}
            disabled={!input.trim() || messages.some((m) => m.loading)}
          >
            Ask
          </button>
        </form>
      </div>

      {/* Citation Detail Modal */}
      {selectedCitation && (
        <div className="modal-overlay" onClick={() => setSelectedCitation(null)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3>Source Reference Citation</h3>
              <button className="modal-close" onClick={() => setSelectedCitation(null)}>
                &times;
              </button>
            </div>
            <div className="modal-body">
              <div style={{ marginBottom: '16px' }}>
                <div className="form-label" style={{ color: 'var(--text-muted)' }}>Document Title</div>
                <div style={{ fontSize: '16px', fontWeight: 600, color: 'var(--text-primary)' }}>{selectedCitation.document_title}</div>
              </div>
              
              <div style={{ display: 'flex', gap: '24px', marginBottom: '20px' }}>
                <div>
                  <div className="form-label" style={{ color: 'var(--text-muted)' }}>Doc ID</div>
                  <div style={{ fontSize: '12px', fontFamily: 'monospace', color: 'var(--text-secondary)' }}>{selectedCitation.document_id}</div>
                </div>
                <div>
                  <div className="form-label" style={{ color: 'var(--text-muted)' }}>Relevance Score</div>
                  <div style={{ fontSize: '14px', fontWeight: 'bold', color: 'var(--status-success)' }}>
                    {(selectedCitation.relevance_score * 100).toFixed(1)}%
                  </div>
                </div>
              </div>

              <div>
                <div className="form-label" style={{ color: 'var(--text-muted)' }}>Grounded Excerpt</div>
                <div
                  style={{
                    padding: '16px',
                    background: 'var(--bg-primary)',
                    borderRadius: '8px',
                    border: '1px solid var(--border-color)',
                    fontSize: '14px',
                    lineHeight: '1.6',
                    whiteSpace: 'pre-wrap',
                    color: 'var(--text-primary)',
                    maxHeight: '300px',
                    overflowY: 'auto'
                  }}
                >
                  {selectedCitation.excerpt}
                </div>
              </div>
            </div>
            <div style={{ padding: '16px 24px', borderTop: '1px solid var(--border-color)', display: 'flex', justifyContent: 'flex-end' }}>
              <button className="btn btn-secondary" onClick={() => setSelectedCitation(null)}>
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
