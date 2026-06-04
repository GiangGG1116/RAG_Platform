import React, { useState, useEffect, useRef, useCallback } from 'react';
import type { AppSettings, Citation, ConversationSummary } from '../services/api';
import {
  queryRAGStream,
  queryRAG,
  listConversations,
  createConversation,
  getConversation,
  updateConversation,
  deleteConversationApi,
  addMessages,
} from '../services/api';
import { ChatHistory } from './ChatHistory';

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

function genId(): string {
  return Math.random().toString(36).substring(2, 9) + Date.now().toString(36);
}

function buildTitle(firstUserText: string): string {
  return firstUserText.length > 52 ? firstUserText.slice(0, 52) + '…' : firstUserText;
}

export const ChatInterface: React.FC<ChatInterfaceProps> = ({ settings }) => {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [selectedCitation, setSelectedCitation] = useState<Citation | null>(null);
  const [historyOpen, setHistoryOpen] = useState(true);
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);

  // Use refs so async callbacks always read the latest value
  const dbConvIdRef = useRef<string | null>(null);
  const memoryIdRef = useRef<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const isFirstMessage = useRef(true);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => { scrollToBottom(); }, [messages]);

  // ── Load history list ───────────────────────────────────────
  const refreshHistory = useCallback(async () => {
    setHistoryLoading(true);
    try {
      const resp = await listConversations(settings, 1, 50);
      setConversations(resp.items);
    } catch (err) {
      console.warn('Could not load conversations:', err);
    } finally {
      setHistoryLoading(false);
    }
  }, [settings]);

  useEffect(() => { refreshHistory(); }, [refreshHistory]);

  // ── Reset to new chat ───────────────────────────────────────
  const handleNewChat = () => {
    setMessages([]);
    dbConvIdRef.current = null;
    memoryIdRef.current = null;
    isFirstMessage.current = true;
  };

  // ── Select saved conversation ───────────────────────────────
  const handleSelectConversation = async (conv: ConversationSummary) => {
    try {
      const full = await getConversation(settings, conv.id);
      const restored: Message[] = full.messages.map((m) => ({
        id: m.id,
        role: m.role as 'user' | 'assistant',
        text: m.content,
        citations: m.meta?.citations ?? undefined,
        model: m.meta?.model ?? undefined,
        latency_ms: m.meta?.latency_ms ?? undefined,
        loading: false,
      }));
      setMessages(restored);
      dbConvIdRef.current = full.id;
      memoryIdRef.current = full.memory_id ?? null;
      isFirstMessage.current = false;
    } catch (err) {
      console.error('Failed to load conversation:', err);
    }
  };

  const handleDeleteConversation = async (id: string) => {
    try {
      await deleteConversationApi(settings, id);
      if (id === dbConvIdRef.current) handleNewChat();
      await refreshHistory();
    } catch (err) {
      console.error('Failed to delete conversation:', err);
    }
  };

  // ── Persist a completed turn ────────────────────────────────
  const persistTurn = useCallback(async (
    userText: string,
    assistantText: string,
    citations?: Citation[],
    model?: string,
    latency_ms?: number,
  ) => {
    try {
      let convId = dbConvIdRef.current;
      if (!convId) {
        const created = await createConversation(
          settings,
          buildTitle(userText),
          memoryIdRef.current,
        );
        convId = created.id;
        dbConvIdRef.current = convId;
      } else if (isFirstMessage.current && memoryIdRef.current) {
        await updateConversation(settings, convId, { memory_id: memoryIdRef.current });
      }
      isFirstMessage.current = false;

      await addMessages(settings, convId, [
        { role: 'user', content: userText, meta: {} },
        {
          role: 'assistant',
          content: assistantText,
          meta: {
            citations: citations ?? [],
            model: model ?? '',
            latency_ms: latency_ms ?? 0,
          },
        },
      ]);

      await refreshHistory();
    } catch (err) {
      console.error('Failed to persist conversation turn:', err);
    }
  }, [settings, refreshHistory]);

  // ── Submit ──────────────────────────────────────────────────
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim()) return;

    const userQuestion = input;
    setInput('');

    const userMsgId = genId();
    const assistantMsgId = genId();

    setMessages((prev) => [
      ...prev,
      { id: userMsgId, role: 'user', text: userQuestion },
      { id: assistantMsgId, role: 'assistant', text: '', statusText: 'Analyzing query…', loading: true },
    ]);

    if (settings.stream) {
      // Accumulate streaming result in local vars (not state)
      let finalText = '';
      let finalCitations: Citation[] | undefined;
      let finalModel: string | undefined;
      let finalLatency: number | undefined;

      try {
        await queryRAGStream(settings, userQuestion, memoryIdRef.current, {
          onStatus: (s) =>
            setMessages((prev) =>
              prev.map((m) => (m.id === assistantMsgId ? { ...m, statusText: s } : m))
            ),
          onToken: (token) => {
            finalText += token;
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantMsgId
                  ? { ...m, text: m.text + token, statusText: undefined }
                  : m
              )
            );
          },
          onCitations: (citations) => {
            finalCitations = citations;
            setMessages((prev) =>
              prev.map((m) => (m.id === assistantMsgId ? { ...m, citations } : m))
            );
          },
          onDone: (doneData) => {
            if (doneData.conversation_id) memoryIdRef.current = doneData.conversation_id;
            finalModel = doneData.model;
            finalLatency = doneData.latency_ms;
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantMsgId
                  ? { ...m, model: doneData.model, latency_ms: doneData.latency_ms, loading: false, statusText: undefined }
                  : m
              )
            );
          },
          onError: (err) =>
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantMsgId
                  ? { ...m, text: m.text + `\n\n[Error: ${err}]`, loading: false, statusText: undefined }
                  : m
              )
            ),
        });

        // Persist AFTER stream fully completes (outside setMessages)
        if (finalText) {
          await persistTurn(userQuestion, finalText, finalCitations, finalModel, finalLatency);
        }
      } catch (err: any) {
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantMsgId
              ? { ...m, text: `Failed: ${err.message || 'Unknown error'}`, loading: false, statusText: undefined }
              : m
          )
        );
      }
    } else {
      // Blocking mode
      try {
        const response = await queryRAG(settings, userQuestion, memoryIdRef.current);
        if (response.conversation_id) memoryIdRef.current = response.conversation_id;

        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantMsgId
              ? {
                  ...m,
                  text: response.answer,
                  citations: response.citations,
                  model: response.model,
                  latency_ms: response.latency_ms,
                  loading: false,
                  statusText: undefined,
                }
              : m
          )
        );

        // Persist directly after response (outside setMessages)
        await persistTurn(
          userQuestion,
          response.answer,
          response.citations,
          response.model,
          response.latency_ms,
        );
      } catch (err: any) {
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantMsgId
              ? { ...m, text: `Failed: ${err.message || 'Unknown error'}`, loading: false, statusText: undefined }
              : m
          )
        );
      }
    }
  };

  const isLoading = messages.some((m) => m.loading);
  const dbConvId = dbConvIdRef.current;

  return (
    <div className="chat-container">
      {/* History Sidebar */}
      <div className={`chat-history-sidebar ${historyOpen ? 'open' : 'closed'}`}>
        <ChatHistory
          conversations={conversations}
          activeConversationId={dbConvId}
          loading={historyLoading}
          onSelect={handleSelectConversation}
          onDelete={handleDeleteConversation}
          onNewChat={handleNewChat}
        />
      </div>

      {/* Main area */}
      <div className="chat-main">
        {/* Header */}
        <div className="chat-header">
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <button
              className="history-toggle-btn"
              onClick={() => setHistoryOpen((o) => !o)}
              title={historyOpen ? 'Hide history' : 'Show history'}
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <line x1="3" y1="6" x2="21" y2="6" />
                <line x1="3" y1="12" x2="21" y2="12" />
                <line x1="3" y1="18" x2="21" y2="18" />
              </svg>
            </button>
            <div>
              <h2>RAG Chat Interface</h2>
              <div style={{ fontSize: '13px', color: 'var(--text-secondary)', marginTop: '2px' }}>
                {dbConvId ? `Conv: ${dbConvId.slice(0, 16)}…` : 'New conversation'}
              </div>
            </div>
          </div>
          <button className="btn btn-secondary" onClick={handleNewChat}>
            + New Conversation
          </button>
        </div>

        {/* Messages */}
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
              {conversations.length > 0 && (
                <p style={{ marginTop: '16px', fontSize: '13px', color: 'var(--text-muted)' }}>
                  ← Select a past conversation from the history panel to continue
                </p>
              )}
            </div>
          ) : (
            messages.map((msg) => (
              <div key={msg.id} className={`message ${msg.role}`}>
                <div className="message-avatar">{msg.role === 'user' ? 'U' : 'AI'}</div>
                <div style={{ display: 'flex', flexDirection: 'column' }}>
                  <div className="message-bubble">
                    {msg.statusText && (
                      <div style={{ display: 'flex', alignItems: 'center', gap: '10px', color: 'var(--text-secondary)', fontSize: '13px', fontStyle: 'italic' }}>
                        <svg className="spinner" viewBox="0 0 50 50" style={{ width: '16px', height: '16px' }}>
                          <circle className="path" cx="25" cy="25" r="20" fill="none" strokeWidth="6" />
                        </svg>
                        {msg.statusText}
                      </div>
                    )}
                    {msg.text && <div className="message-text">{msg.text}</div>}
                    {msg.citations && msg.citations.length > 0 && (
                      <div className="citations-list">
                        {msg.citations.map((cite, index) => (
                          <div key={index} className="citation-chip" onClick={() => setSelectedCitation(cite)}>
                            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                              <path strokeLinecap="round" strokeLinejoin="round" d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" />
                            </svg>
                            [{index + 1}] {cite.document_title}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
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

        {/* Input */}
        <div className="chat-input-area">
          <form onSubmit={handleSubmit} className="chat-form">
            <input
              type="text"
              className="form-input"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Type your question…"
              disabled={isLoading}
              style={{ borderRadius: 'var(--radius-md)', padding: '16px 20px', fontSize: '15px' }}
            />
            <button
              type="submit"
              className="btn btn-primary"
              style={{ padding: '0 24px', flexShrink: 0 }}
              disabled={!input.trim() || isLoading}
            >
              Ask
            </button>
          </form>
        </div>
      </div>

      {/* Citation Modal */}
      {selectedCitation && (
        <div className="modal-overlay" onClick={() => setSelectedCitation(null)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3>Source Reference Citation</h3>
              <button className="modal-close" onClick={() => setSelectedCitation(null)}>&times;</button>
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
                <div style={{ padding: '16px', background: 'var(--bg-primary)', borderRadius: '8px', border: '1px solid var(--border-color)', fontSize: '14px', lineHeight: '1.6', whiteSpace: 'pre-wrap', color: 'var(--text-primary)', maxHeight: '300px', overflowY: 'auto' }}>
                  {selectedCitation.excerpt}
                </div>
              </div>
            </div>
            <div style={{ padding: '16px 24px', borderTop: '1px solid var(--border-color)', display: 'flex', justifyContent: 'flex-end' }}>
              <button className="btn btn-secondary" onClick={() => setSelectedCitation(null)}>Close</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
