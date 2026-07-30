// Boot, rail rendering and view routing.

import { api } from './api.js';
import { $, clear, closeDrawer, confirmDialog, el, modal, plural, toast } from './ui.js';
import {
  loadDocuments, loadWorkspaces, on, restoreWorkspaceId, selectWorkspace, state, workspace,
} from './state.js';

import * as vault from './views/vault.js';
import * as review from './views/review.js';
import * as assistant from './views/assistant.js';
import * as playbookReview from './views/playbooks.js';

const VIEWS = { vault, review, assistant, playbooks: playbookReview };

let activeView = null;

// ---------------------------------------------------------------- routing

async function show(name) {
  if (!VIEWS[name]) name = 'vault';
  if (activeView && activeView !== name) VIEWS[activeView].teardown?.();
  activeView = name;
  state.view = name;
  localStorage.setItem('lexara.view', name);

  for (const button of document.querySelectorAll('.nav-item')) {
    button.classList.toggle('active', button.dataset.view === name);
  }

  const view = VIEWS[name];
  $('#view-title').textContent = view.meta.title;
  $('#view-subtitle').textContent = view.meta.subtitle;

  const root = $('#view');
  clear(root);
  try {
    await view.render(root);
  } catch (error) {
    clear(root);
    root.append(el('div', { class: 'view-pad' }, [
      el('p', { class: 'small', style: 'color:var(--high)', text: error.message }),
    ]));
  }
  paintTopbar();
}

function paintTopbar() {
  const bar = $('#topbar-actions');
  clear(bar);
  if (!state.workspaceId) return;
  const view = VIEWS[activeView];
  for (const node of view.actions?.() ?? []) bar.append(node);
}

// ---------------------------------------------------------------- rail

function paintRail() {
  const list = $('#matter-list');
  clear(list);

  for (const item of state.workspaces) {
    list.append(el('li', {}, [
      el('button', {
        class: `matter-btn ${item.id === state.workspaceId ? 'active' : ''}`,
        onclick: () => choose(item.id),
        oncontextmenu: (event) => { event.preventDefault(); removeWorkspace(item); },
      }, [
        el('strong', { text: item.name }),
        el('span', {
          text: [
            item.client,
            plural(item.counts.documents, 'doc'),
            item.counts.tables ? plural(item.counts.tables, 'review') : null,
          ].filter(Boolean).join(' · '),
        }),
      ]),
    ]));
  }

  if (!state.workspaces.length) {
    list.append(el('li', {}, [
      el('p', { class: 'small', style: 'padding:8px 9px;color:#767d8c', text: 'No matters yet.' }),
    ]));
  }

  $('#rail-nav').hidden = !state.workspaceId;
  paintCounts();
}

function paintCounts() {
  const current = workspace();
  $('#count-documents').textContent = state.documents.length || '';
  $('#count-tables').textContent = current?.counts?.tables || '';
}

async function choose(id) {
  await selectWorkspace(id);
  await loadWorkspaces();
  paintRail();
  await show(state.view);
}

async function createWorkspace() {
  const values = await modal({
    title: 'New matter',
    fields: [
      { name: 'name', label: 'Matter name', placeholder: 'Project Atlas — vendor diligence' },
      { name: 'client', label: 'Client (optional)', placeholder: 'Northwind Holdings' },
    ],
    confirmLabel: 'Create matter',
  });
  if (!values?.name) return;

  const created = await api.createWorkspace(values);
  await loadWorkspaces();
  await selectWorkspace(created.id);
  paintRail();
  await show('vault');
  toast('Matter created. Upload documents to get started.');
}

async function removeWorkspace(item) {
  const ok = await confirmDialog(
    'Delete matter',
    `“${item.name}” will be deleted along with its documents, reviews and threads.`,
  );
  if (!ok) return;

  await api.deleteWorkspace(item.id);
  if (state.workspaceId === item.id) {
    state.workspaceId = null;
    await loadDocuments();
  }
  await loadWorkspaces();
  const next = state.workspaces[0];
  if (next && !state.workspaceId) await selectWorkspace(next.id);
  paintRail();
  await show(state.view);
  toast('Matter deleted.');
}

// ---------------------------------------------------------------- boot

async function boot() {
  $('#new-matter').onclick = createWorkspace;
  $('#drawer-close').onclick = closeDrawer;
  $('#drawer-scrim').onclick = closeDrawer;

  for (const button of document.querySelectorAll('.nav-item')) {
    button.onclick = () => show(button.dataset.view);
  }

  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') closeDrawer();
  });
  window.addEventListener('lexara:topbar', paintTopbar);

  on('documents', paintCounts);

  try {
    const health = await api.health();
    state.llmReady = health.llm_configured;
    $('#llm-status').className = `status-dot ${health.llm_configured ? 'on' : 'off'}`;
    $('#llm-status-text').textContent = health.llm_configured
      ? health.model
      : 'no API key — read-only';
    $('#llm-status-text').title = health.llm_configured
      ? `Model: ${health.model}`
      : 'Set ANTHROPIC_API_KEY to enable review, assistant and playbooks.';
  } catch {
    $('#llm-status-text').textContent = 'server unreachable';
  }

  await loadWorkspaces();

  const remembered = restoreWorkspaceId();
  const target = state.workspaces.find((w) => w.id === remembered) ?? state.workspaces[0];
  if (target) await selectWorkspace(target.id);
  paintRail();

  if (!state.workspaceId) {
    activeView = 'vault';
    $('#view-title').textContent = 'Welcome to Lexara';
    $('#view-subtitle').textContent = 'Create a matter to hold the documents you are working on.';
    $('#view').append(el('div', { class: 'view-pad' }, [
      el('div', { class: 'empty' }, [
        el('div', { class: 'empty-glyph', text: '◆' }),
        el('h3', { text: 'Start with a matter' }),
        el('p', {
          text: 'A matter holds a set of documents plus everything you do with them — '
            + 'tabular reviews, matter Q&A, and playbook checks.',
        }),
        el('button', { class: 'btn btn-primary', text: 'New matter', onclick: createWorkspace }),
      ]),
    ]));
    return;
  }

  await show(localStorage.getItem('lexara.view') || 'vault');
}

boot();
