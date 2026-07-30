// Thin fetch layer. Every call resolves to parsed JSON or throws an Error
// carrying the server's message, which the UI surfaces in a toast.

async function request(method, path, body, options = {}) {
  const init = { method, headers: {} };

  if (body instanceof FormData) {
    init.body = body;
  } else if (body !== undefined) {
    init.headers['Content-Type'] = 'application/json';
    init.body = JSON.stringify(body);
  }
  if (options.signal) init.signal = options.signal;

  const response = await fetch(path, init);
  if (response.status === 204) return null;

  const text = await response.text();
  let data = null;
  try { data = text ? JSON.parse(text) : null; } catch { data = { raw: text }; }

  if (!response.ok) {
    const error = new Error((data && data.error) || `Request failed (${response.status})`);
    error.status = response.status;
    error.code = data && data.code;
    throw error;
  }
  return data;
}

export const api = {
  get:    (path, options) => request('GET', path, undefined, options),
  post:   (path, body, options) => request('POST', path, body, options),
  patch:  (path, body) => request('PATCH', path, body),
  put:    (path, body) => request('PUT', path, body),
  del:    (path) => request('DELETE', path),

  health: () => request('GET', '/api/health'),

  // Matters
  listWorkspaces: () => request('GET', '/api/workspaces'),
  createWorkspace: (body) => request('POST', '/api/workspaces', body),
  deleteWorkspace: (id) => request('DELETE', `/api/workspaces/${id}`),

  // Vault
  listDocuments: (ws) => request('GET', `/api/workspaces/${ws}/documents`),
  uploadDocuments: (ws, files) => {
    const form = new FormData();
    for (const file of files) form.append('files', file);
    return request('POST', `/api/workspaces/${ws}/documents`, form);
  },
  documentText: (id) => request('GET', `/api/documents/${id}/text`),
  renameDocument: (id, title) => request('PATCH', `/api/documents/${id}`, { title }),
  deleteDocument: (id) => request('DELETE', `/api/documents/${id}`),
  intake: (id) => request('POST', `/api/documents/${id}/intake`, {}),
  search: (ws, query) => request('POST', `/api/workspaces/${ws}/search`, { query }),

  // Tabular review
  listTables: (ws) => request('GET', `/api/workspaces/${ws}/tables`),
  createTable: (ws, body) => request('POST', `/api/workspaces/${ws}/tables`, body),
  getTable: (id) => request('GET', `/api/tables/${id}`),
  renameTable: (id, name) => request('PATCH', `/api/tables/${id}`, { name }),
  deleteTable: (id) => request('DELETE', `/api/tables/${id}`),
  setRows: (id, documentIds) => request('PUT', `/api/tables/${id}/rows`, { document_ids: documentIds }),
  addColumns: (id, columns, run = true) => request('POST', `/api/tables/${id}/columns`, { columns, run }),
  updateColumn: (id, body) => request('PATCH', `/api/columns/${id}`, body),
  deleteColumn: (id) => request('DELETE', `/api/columns/${id}`),
  suggestColumns: (id) => request('POST', `/api/tables/${id}/suggest-columns`, {}),
  runTable: (id, body = {}) => request('POST', `/api/tables/${id}/run`, body),
  tableProgress: (id) => request('GET', `/api/tables/${id}/progress`),
  editCell: (tableId, columnId, documentId, value) =>
    request('PATCH', `/api/tables/${tableId}/cells/${columnId}/${documentId}`, { value }),
  memo: (id, focus) => request('POST', `/api/tables/${id}/memo`, { focus }),

  // Assistant
  listThreads: (ws) => request('GET', `/api/workspaces/${ws}/threads`),
  createThread: (ws) => request('POST', `/api/workspaces/${ws}/threads`, {}),
  getThread: (id) => request('GET', `/api/threads/${id}`),
  deleteThread: (id) => request('DELETE', `/api/threads/${id}`),

  // Playbooks
  listPlaybooks: () => request('GET', '/api/playbooks'),
  getPlaybook: (key) => request('GET', `/api/playbooks/${key}`),
  listReviews: (ws) => request('GET', `/api/workspaces/${ws}/reviews`),
  startReview: (documentId, body) => request('POST', `/api/documents/${documentId}/review`, body),
  getReview: (id) => request('GET', `/api/reviews/${id}`),
  deleteReview: (id) => request('DELETE', `/api/reviews/${id}`),
};

/**
 * POST a message and consume the server-sent event stream.
 * `handlers` may define onSources, onDelta, onDone, onError.
 * Returns an abort function.
 */
export function streamMessage(threadId, payload, handlers) {
  const controller = new AbortController();

  (async () => {
    try {
      const response = await fetch(`/api/threads/${threadId}/messages`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
        signal: controller.signal,
      });

      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(data.error || `Request failed (${response.status})`);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        const frames = buffer.split('\n\n');
        buffer = frames.pop() ?? '';
        for (const frame of frames) {
          const line = frame.split('\n').find((l) => l.startsWith('data: '));
          if (!line) continue;
          let event;
          try { event = JSON.parse(line.slice(6)); } catch { continue; }

          if (event.type === 'sources') handlers.onSources?.(event.sources);
          else if (event.type === 'delta') handlers.onDelta?.(event.text);
          else if (event.type === 'error') handlers.onError?.(new Error(event.error));
          else if (event.type === 'done') handlers.onDone?.(event);
        }
      }
    } catch (error) {
      if (error.name !== 'AbortError') handlers.onError?.(error);
    }
  })();

  return () => controller.abort();
}
