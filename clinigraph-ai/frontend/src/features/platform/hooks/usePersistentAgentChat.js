import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { apiDelete, apiGet, apiPost, apiPostNdjson } from '../../../shared/api/http';

function normalizeAssistantContent(content) {
  if (typeof content !== 'string') return '';
  return content
    .replace(/\\n/g, '\n')
    .replace(/\\t/g, '\t')
    .replace(/\\r/g, '')
    .replace(/^\s*#{1,6}\s*/gm, '')
    .replace(/\*\*(SUMMARY|EVIDENCE|CLINICAL IMPLICATIONS|UNCERTAINTY\s*&\s*LIMITATIONS|DISCLAIMER)\*\*/gi, '$1')
    .trim();
}

function getErrorMessage(err) {
  if (err?.status === 401) return 'Authentication failed. Please log in again.';
  if (err?.status === 402) return 'Your subscription is not active. Please update billing to continue.';
  if (err?.status === 403) return 'You do not have permission for this tenant.';
  if (err?.status === 404) return 'Resource not found.';
  return err?.payload?.error || 'Request failed. Please try again.';
}

export function usePersistentAgentChat({ authToken = '', tenantId = '' } = {}) {
  const [searchTerm, setSearchTerm] = useState('');
  const [sessions, setSessions] = useState([]);
  const [sessionsPagination, setSessionsPagination] = useState({ total: 0, limit: 30, offset: 0, has_more: false });
  const [messagesPagination, setMessagesPagination] = useState({ total: 0, limit: 80, offset: 0, has_more: false, from_end: true });
  const [activeSession, setActiveSession] = useState(null);
  const [activeSessionId, setActiveSessionId] = useState(null);
  const [recentlyLoadedMessageIds, setRecentlyLoadedMessageIds] = useState([]);
  const [pendingHighlightId, setPendingHighlightId] = useState(null);
  const [question, setQuestion] = useState('');
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const recentLoadTimerRef = useRef(null);

  const headers = useMemo(
    () => ({
      Authorization: `Bearer ${authToken}`,
      ...(tenantId ? { 'X-Tenant-ID': tenantId } : {}),
    }),
    [authToken, tenantId],
  );

  const requireAuth = useCallback(() => {
    if (!authToken.trim()) {
      setError('Sign in to use the chat workspace.');
      return false;
    }
    return true;
  }, [authToken]);

  useEffect(() => {
    setSessions([]);
    setSessionsPagination({ total: 0, limit: 30, offset: 0, has_more: false });
    setMessagesPagination({ total: 0, limit: 80, offset: 0, has_more: false, from_end: true });
    setActiveSession(null);
    setActiveSessionId(null);
    setPendingHighlightId(null);
    setRecentlyLoadedMessageIds([]);
    setError('');
    if (authToken.trim()) {
      loadSessions('', 0, false);
    }
  }, [authToken, tenantId]);

  const loadSessions = useCallback(
    async (q = '', offset = 0, append = false) => {
      if (!requireAuth()) return;
      setLoading(true);
      setError('');
      try {
        const params = new URLSearchParams();
        if (q.trim()) params.set('q', q.trim());
        params.set('limit', '30');
        params.set('offset', String(offset));
        const data = await apiGet(`/agent/chats/?${params.toString()}`, { headers });

        const items = Array.isArray(data) ? data : (Array.isArray(data?.items) ? data.items : []);
        const pagination = data?.pagination || {
          total: items.length,
          limit: 30,
          offset,
          has_more: false,
        };
        setSessions((prev) => {
          if (!append) return items;
          const seen = new Set(prev.map((row) => row.session_id));
          const merged = [...prev];
          for (const item of items) {
            if (!seen.has(item.session_id)) merged.push(item);
          }
          return merged;
        });
        setSessionsPagination(pagination);
      } catch (err) {
        setError(getErrorMessage(err));
      } finally {
        setLoading(false);
      }
    },
    [headers, requireAuth],
  );

  const loadMoreSessions = useCallback(async () => {
    if (!sessionsPagination.has_more) return;
    const nextOffset = sessionsPagination.offset + sessionsPagination.limit;
    await loadSessions(searchTerm, nextOffset, true);
  }, [loadSessions, searchTerm, sessionsPagination]);

  const createSession = useCallback(
    async (title = '') => {
      if (!requireAuth()) return null;
      try {
        const created = await apiPost('/agent/chats/', { title }, { headers });
        setSessions((prev) => [created, ...prev.filter((item) => item.session_id !== created.session_id)]);
        return created;
      } catch (err) {
        setError(getErrorMessage(err));
        return null;
      }
    },
    [headers, requireAuth],
  );

  const loadSessionDetail = useCallback(
    async (sessionId, highlightId = null, messageOffset = 0, appendOlder = false) => {
      if (!requireAuth()) return;
      setLoading(true);
      setError('');
      try {
        const params = new URLSearchParams();
        params.set('message_limit', '80');
        params.set('message_offset', String(messageOffset));
        params.set('from_end', '1');
        const detail = await apiGet(`/agent/chats/${sessionId}/?${params.toString()}`, { headers });

        setActiveSession((prev) => {
          if (!appendOlder || !prev || prev.session_id !== sessionId) {
            setRecentlyLoadedMessageIds([]);
            return detail;
          }
          const existing = prev.messages || [];
          const incoming = detail.messages || [];
          const existingIds = new Set(existing.map((m) => m.message_id));
          const olderOnly = incoming.filter((m) => !existingIds.has(m.message_id));

          const loadedIds = olderOnly.map((m) => m.message_id);
          setRecentlyLoadedMessageIds(loadedIds);
          if (recentLoadTimerRef.current) {
            clearTimeout(recentLoadTimerRef.current);
          }
          recentLoadTimerRef.current = setTimeout(() => {
            setRecentlyLoadedMessageIds([]);
          }, 1800);

          return {
            ...detail,
            messages: [...olderOnly, ...existing],
          };
        });

        setMessagesPagination(detail?.messages_pagination || { total: 0, limit: 80, offset: 0, has_more: false, from_end: true });
        setActiveSessionId(sessionId);
        setPendingHighlightId(highlightId);
      } catch (err) {
        setError(getErrorMessage(err));
      } finally {
        setLoading(false);
      }
    },
    [headers, requireAuth],
  );

  const refreshActiveSession = useCallback(async () => {
    if (!activeSessionId) return;
    await loadSessionDetail(activeSessionId, null, 0, false);
  }, [activeSessionId, loadSessionDetail]);

  const loadOlderMessages = useCallback(async () => {
    if (!activeSessionId || !messagesPagination.has_more) return;
    const nextOffset = messagesPagination.offset + messagesPagination.limit;
    await loadSessionDetail(activeSessionId, null, nextOffset, true);
  }, [activeSessionId, loadSessionDetail, messagesPagination]);

  const submitQuestion = useCallback(async () => {
    const prompt = question.trim();
    if (!prompt) {
      setError('Please enter a question.');
      return;
    }
    if (!requireAuth()) return;

    setSubmitting(true);
    setError('');

    const tempUserId = `temp-user-${Date.now()}`;
    const tempAssistantId = `temp-assistant-${Date.now()}`;

    try {
      let currentSessionId = activeSessionId;
      if (!currentSessionId) {
        const created = await createSession();
        if (!created) {
          setSubmitting(false);
          return;
        }
        currentSessionId = created.session_id;
        setActiveSessionId(currentSessionId);
        setActiveSession({
          session_id: currentSessionId,
          title: created.title || 'New chat',
          messages: [],
          highlights: [],
        });
      }

      const existingMessages = activeSession?.messages || [];

      // Optimistic append: user prompt and assistant placeholder.
      setActiveSession((prev) => {
        const baseMessages = prev?.messages || existingMessages;
        return {
          ...(prev || {}),
          session_id: currentSessionId,
          title: prev?.title || 'New chat',
          messages: [
            ...baseMessages,
            {
              message_id: tempUserId,
              role: 'user',
              content: prompt,
              request_id: '',
              created_at: new Date().toISOString(),
            },
            {
              message_id: tempAssistantId,
              role: 'assistant',
              content: '...',
              request_id: '',
              created_at: new Date().toISOString(),
            },
          ],
          highlights: prev?.highlights || [],
        };
      });

      const newUserMessage = await apiPost(
        `/agent/chats/${currentSessionId}/messages/`,
        { role: 'user', content: prompt },
        { headers },
      );

      const history = existingMessages.map((msg) => ({ role: msg.role, content: msg.content }));
      let streamedAnswer = '';
      const response = await apiPostNdjson(
        '/agent/query/stream/',
        {
          question: prompt,
          conversation_history: history,
        },
        {
          headers,
          onEvent: (event) => {
            if (event?.event !== 'delta') return;
            streamedAnswer += event.delta || '';
            const liveContent = normalizeAssistantContent(streamedAnswer || '...');

            setActiveSession((prev) => {
              if (!prev) return prev;
              return {
                ...prev,
                messages: (prev.messages || []).map((msg) => {
                  if (msg.message_id !== tempAssistantId) return msg;
                  return {
                    ...msg,
                    content: liveContent,
                  };
                }),
              };
            });
          },
        },
      ).catch(async (streamErr) => {
        if (streamErr?.status === 404 || streamErr?.status === 405) {
          return apiPost(
            '/agent/query/',
            {
              question: prompt,
              conversation_history: history,
            },
            { headers },
          );
        }
        throw streamErr;
      });

      const assistantContent = normalizeAssistantContent(response?.answer || streamedAnswer || '');
      const requestId = response?.request_id || '';

      const newAssistantMessage = await apiPost(
        `/agent/chats/${currentSessionId}/messages/`,
        {
          role: 'assistant',
          content: assistantContent,
          request_id: requestId,
        },
        { headers },
      );

      setActiveSession((prev) => ({
        ...(prev || {}),
        session_id: currentSessionId,
        title: prev?.title || 'New chat',
        messages: (prev?.messages || [])
          .filter((msg) => msg.message_id !== tempUserId && msg.message_id !== tempAssistantId)
          .concat([newUserMessage, newAssistantMessage]),
        highlights: prev?.highlights || [],
      }));
      setQuestion('');
      await loadSessions(searchTerm);
      await loadSessionDetail(currentSessionId, null, 0, false);
    } catch (err) {
      // Remove assistant placeholder on failure to avoid stale loading bubble.
      setActiveSession((prev) => {
        if (!prev) return prev;
        return {
          ...prev,
          messages: (prev.messages || []).filter((msg) => msg.message_id !== tempAssistantId),
        };
      });
      setError(getErrorMessage(err));
    } finally {
      setSubmitting(false);
    }
  }, [
    activeSession,
    activeSessionId,
    createSession,
    headers,
    loadSessionDetail,
    loadSessions,
    question,
    requireAuth,
    searchTerm,
  ]);

  const addHighlight = useCallback(
    async ({ messageId, selectedText, startOffset, endOffset, contextSnippet }) => {
      if (!activeSessionId) return null;
      const tempHighlightId = `temp-highlight-${Date.now()}`;

      setActiveSession((prev) => {
        if (!prev) return prev;
        return {
          ...prev,
          highlights: [
            {
              highlight_id: tempHighlightId,
              message_id: messageId,
              selected_text: selectedText,
              start_offset: startOffset,
              end_offset: endOffset,
              context_snippet: contextSnippet || selectedText,
              created_at: new Date().toISOString(),
            },
            ...(prev.highlights || []),
          ],
        };
      });

      try {
        const created = await apiPost(
          `/agent/chats/${activeSessionId}/highlights/`,
          {
            message_id: messageId,
            selected_text: selectedText,
            start_offset: startOffset,
            end_offset: endOffset,
            context_snippet: contextSnippet,
          },
          { headers },
        );
        setActiveSession((prev) => {
          if (!prev) return prev;
          return {
            ...prev,
            highlights: [
              created,
              ...(prev.highlights || []).filter((item) => item.highlight_id !== tempHighlightId),
            ],
          };
        });
        await refreshActiveSession();
        await loadSessions(searchTerm);
        return created;
      } catch (err) {
        setActiveSession((prev) => {
          if (!prev) return prev;
          return {
            ...prev,
            highlights: (prev.highlights || []).filter((item) => item.highlight_id !== tempHighlightId),
          };
        });
        setError(getErrorMessage(err));
        return null;
      }
    },
    [activeSessionId, headers, loadSessions, refreshActiveSession, searchTerm],
  );

  const popHighlight = useCallback(async () => {
    if (!activeSessionId) return;
    const latest = (activeSession?.highlights || [])[0];
    if (!latest) return;

    setActiveSession((prev) => {
      if (!prev) return prev;
      return {
        ...prev,
        highlights: (prev.highlights || []).filter((item) => item.highlight_id !== latest.highlight_id),
      };
    });

    try {
      await apiDelete(`/agent/chats/${activeSessionId}/highlights/pop/`, { headers });
      await refreshActiveSession();
      await loadSessions(searchTerm);
    } catch (err) {
      setActiveSession((prev) => {
        if (!prev) return prev;
        return {
          ...prev,
          highlights: [latest, ...(prev.highlights || [])],
        };
      });
      setError(getErrorMessage(err));
    }
  }, [activeSession, activeSessionId, headers, loadSessions, refreshActiveSession, searchTerm]);

  return {
    searchTerm,
    setSearchTerm,
    sessions,
    sessionsPagination,
    activeSession,
    activeSessionId,
    pendingHighlightId,
    setPendingHighlightId,
    recentlyLoadedMessageIds,
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
    messagesPagination,
    submitQuestion,
    addHighlight,
    popHighlight,
  };
}
