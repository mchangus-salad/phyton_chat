import { useEffect, useMemo, useState } from 'react';
import { useI18n } from '../../../shared/i18n/I18nProvider';
import { usePersistentAgentChat } from '../hooks/usePersistentAgentChat';

function renderMessageWithHighlights(message, highlights) {
  const text = message.content || '';
  if (!highlights.length) return [{ type: 'text', value: text }];

  const sorted = [...highlights]
    .filter((h) => h.start_offset >= 0 && h.end_offset > h.start_offset && h.end_offset <= text.length)
    .sort((a, b) => a.start_offset - b.start_offset);

  const chunks = [];
  let cursor = 0;
  for (const item of sorted) {
    if (item.start_offset < cursor) continue;
    if (cursor < item.start_offset) {
      chunks.push({ type: 'text', value: text.slice(cursor, item.start_offset) });
    }
    chunks.push({
      type: 'highlight',
      value: text.slice(item.start_offset, item.end_offset),
      highlightId: item.highlight_id,
    });
    cursor = item.end_offset;
  }
  if (cursor < text.length) {
    chunks.push({ type: 'text', value: text.slice(cursor) });
  }
  return chunks;
}

export function AgentChatWorkspace({ authToken, tenantId }) {
  const { t } = useI18n();
  const [chatMainPercent, setChatMainPercent] = useState(76);
  const {
    searchTerm,
    setSearchTerm,
    sessions,
    sessionsPagination,
    activeSession,
    messagesPagination,
    recentlyLoadedMessageIds,
    pendingHighlightId,
    setPendingHighlightId,
    question,
    setQuestion,
    loading,
    submitting,
    error,
    loadSessions,
    loadMoreSessions,
    loadOlderMessages,
    createSession,
    loadSessionDetail,
    submitQuestion,
    addHighlight,
    popHighlight,
  } = usePersistentAgentChat({ authToken, tenantId });

  useEffect(() => {
    if (!pendingHighlightId) return;
    const target = document.getElementById(`highlight-${pendingHighlightId}`);
    if (!target) return;
    target.scrollIntoView({ behavior: 'smooth', block: 'center' });
    target.classList.add('chat-highlight--flash');
    const timer = setTimeout(() => {
      target.classList.remove('chat-highlight--flash');
      setPendingHighlightId(null);
    }, 1200);
    return () => clearTimeout(timer);
  }, [activeSession, pendingHighlightId, setPendingHighlightId]);

  const highlightByMessage = useMemo(() => {
    const map = new Map();
    for (const item of activeSession?.highlights || []) {
      const row = map.get(item.message_id) || [];
      row.push(item);
      map.set(item.message_id, row);
    }
    return map;
  }, [activeSession]);

  const onMessageMouseUp = async (message, event) => {
    if (message.role !== 'assistant') return;
    const selection = window.getSelection();
    if (!selection || selection.rangeCount === 0 || selection.isCollapsed) return;
    if (!event.currentTarget.contains(selection.anchorNode) || !event.currentTarget.contains(selection.focusNode)) return;

    const selectedText = selection.toString().trim();
    if (!selectedText) return;

    const range = selection.getRangeAt(0);
    const prefix = document.createRange();
    prefix.selectNodeContents(event.currentTarget);
    prefix.setEnd(range.startContainer, range.startOffset);
    const startOffset = prefix.toString().length;
    const endOffset = startOffset + selectedText.length;

    const contextStart = Math.max(startOffset - 40, 0);
    const contextEnd = Math.min(endOffset + 40, message.content.length);
    const contextSnippet = message.content.slice(contextStart, contextEnd);

    await addHighlight({
      messageId: message.message_id,
      selectedText,
      startOffset,
      endOffset,
      contextSnippet,
    });

    selection.removeAllRanges();
  };

  const sidebarPercent = 100 - chatMainPercent;

  return (
    <section className="agent-chat-workspace card">
      <div className="agent-chat-workspace__header">
        <div>
          <h2>{t('genai.chatTitle')}</h2>
          <p className="description">{t('genai.chatDescription')}</p>
        </div>
        <div className="agent-chat-size-controls" aria-label={t('genai.chatWidthLabel')}>
          <span>{t('genai.chatWidthLabel')}</span>
          <button
            type="button"
            className="secondary-action"
            onClick={() => setChatMainPercent((current) => Math.max(62, current - 4))}
          >
            {t('genai.chatWidthNarrow')}
          </button>
          <input
            type="range"
            min="62"
            max="88"
            value={chatMainPercent}
            onChange={(event) => setChatMainPercent(Number(event.target.value))}
          />
          <button
            type="button"
            className="secondary-action"
            onClick={() => setChatMainPercent((current) => Math.min(88, current + 4))}
          >
            {t('genai.chatWidthWide')}
          </button>
          <button
            type="button"
            className="secondary-action"
            onClick={() => setChatMainPercent(76)}
          >
            {t('genai.chatWidthReset')}
          </button>
        </div>
      </div>

      <div className="agent-chat-layout" style={{ gridTemplateColumns: `minmax(190px, ${sidebarPercent}%) minmax(520px, ${chatMainPercent}%)` }}>
        <aside className="agent-chat-sidebar">
          <div className="agent-chat-sidebar__actions">
            <button type="button" className="primary-action" onClick={() => createSession()}>
              {t('genai.newChat')}
            </button>
            <button type="button" className="secondary-action" onClick={() => loadSessions(searchTerm)}>
              {t('genai.loadChats')}
            </button>
          </div>

          <div className="form-group">
            <label htmlFor="chat-search">{t('genai.searchChats')}</label>
            <input
              id="chat-search"
              type="text"
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') loadSessions(e.currentTarget.value);
              }}
              placeholder={t('genai.searchChatsPlaceholder')}
            />
          </div>

          <ul className="agent-chat-list">
            {sessions.map((session) => (
              <li key={session.session_id} className="agent-chat-list__item">
                <button type="button" onClick={() => loadSessionDetail(session.session_id)} className="agent-chat-list__button">
                  <span className="agent-chat-list__title">{session.title || t('genai.untitledChat')}</span>
                  <span className="agent-chat-list__preview">{session.preview || ''}</span>
                </button>
                {session.highlights_preview?.length ? (
                  <div className="agent-chat-list__hover-preview">
                    <p>{t('genai.highlightPreview')}</p>
                    {session.highlights_preview.map((highlight) => (
                      <button
                        type="button"
                        key={highlight.highlight_id}
                        className="agent-chat-list__jump"
                        onClick={() => loadSessionDetail(session.session_id, highlight.highlight_id)}
                      >
                        {highlight.context_snippet || highlight.selected_text}
                      </button>
                    ))}
                  </div>
                ) : null}
              </li>
            ))}
          </ul>
          {sessionsPagination?.has_more ? (
            <button type="button" className="secondary-action" onClick={loadMoreSessions}>
              {t('genai.loadMoreChats')}
            </button>
          ) : null}
        </aside>

        <div className="agent-chat-main" onContextMenu={(e) => {
          if (e.target?.closest?.('.chat-highlight')) {
            e.preventDefault();
            popHighlight();
          }
        }}>
          <div className="agent-chat-composer">
            <textarea
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              placeholder={t('genai.questionPlaceholder')}
              rows={4}
            />
            <button type="button" className="primary-action" onClick={submitQuestion} disabled={submitting}>
              {submitting ? t('genai.processing') : t('genai.submitQuery')}
            </button>
          </div>

          <div className="agent-chat-messages">
            {(activeSession?.messages || []).map((message) => {
              const highlights = highlightByMessage.get(message.message_id) || [];
              const parts = renderMessageWithHighlights(message, highlights);
              const isRecentLoaded = recentlyLoadedMessageIds.includes(message.message_id);
              return (
                <article
                  key={message.message_id}
                  className={`agent-chat-message agent-chat-message--${message.role} ${isRecentLoaded ? 'agent-chat-message--recent' : ''}`}
                >
                  <header>{message.role === 'assistant' ? t('genai.assistant') : t('genai.user')}</header>
                  <p onMouseUp={(e) => onMessageMouseUp(message, e)}>
                    {parts.map((part, idx) => {
                      if (part.type === 'highlight') {
                        return (
                          <mark
                            id={`highlight-${part.highlightId}`}
                            className="chat-highlight"
                            key={`${part.highlightId}-${idx}`}
                            title={t('genai.rightClickUndo')}
                          >
                            {part.value}
                          </mark>
                        );
                      }
                      return <span key={`${message.message_id}-${idx}`}>{part.value}</span>;
                    })}
                  </p>
                </article>
              );
            })}
          </div>
          {messagesPagination?.has_more ? (
            <button type="button" className="secondary-action agent-chat-load-older" onClick={loadOlderMessages}>
              {t('genai.loadOlderMessages')}
            </button>
          ) : null}
        </div>
      </div>

      {(loading || submitting) && <p className="billing-note">{t('ui.loading')}</p>}
      {error ? <p className="billing-error">{error}</p> : null}
    </section>
  );
}
