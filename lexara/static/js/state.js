// A single mutable store with change notification. Views read from it and
// re-render on the events they care about.

import { api } from './api.js';

const listeners = new Map();

export const state = {
  llmReady: false,
  workspaces: [],
  workspaceId: null,
  documents: [],
  view: 'vault',
  // per-view memory so switching tabs doesn't lose your place
  tableId: null,
  threadId: null,
  reviewId: null,
  scopeDocumentIds: [],
};

export function on(event, handler) {
  if (!listeners.has(event)) listeners.set(event, new Set());
  listeners.get(event).add(handler);
  return () => listeners.get(event).delete(handler);
}

export function emit(event, detail) {
  for (const handler of listeners.get(event) ?? []) handler(detail);
}

export const workspace = () => state.workspaces.find((w) => w.id === state.workspaceId) ?? null;

export const readyDocuments = () => state.documents.filter((d) => d.status === 'ready');

export const documentById = (id) => state.documents.find((d) => d.id === id) ?? null;

export async function loadWorkspaces() {
  const { workspaces } = await api.listWorkspaces();
  state.workspaces = workspaces;
  emit('workspaces');
  return workspaces;
}

export async function loadDocuments() {
  if (!state.workspaceId) {
    state.documents = [];
  } else {
    const { documents } = await api.listDocuments(state.workspaceId);
    state.documents = documents;
  }
  emit('documents');
  return state.documents;
}

export async function selectWorkspace(id) {
  if (state.workspaceId === id) return;
  state.workspaceId = id;
  state.tableId = null;
  state.threadId = null;
  state.reviewId = null;
  state.scopeDocumentIds = [];
  localStorage.setItem('lexara.workspace', id ?? '');
  await loadDocuments();
  emit('workspace');
}

export function restoreWorkspaceId() {
  return localStorage.getItem('lexara.workspace') || null;
}
