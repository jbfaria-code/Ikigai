// Matter Q&A. Answers stream in with numbered citations that open the source.

import { api, streamMessage } from '../api.js';
import { $, clear, drawer, el, markdown, toast } from '../ui.js';
import { readyDocuments, state } from '../state.js';
import { openDocument } from './vault.js';

const SUGGESTIONS = [
  'Summarise the key commercial terms across these documents.',
  'Which agreements can the counterparty terminate for convenience?',
  'What are the notice requirements for termination?',
  'Where do the liability caps differ from each other?',
  'Flag anything that restricts assignment on a change of control.',
];

let threads = [];
let messages = [];
let sources = [];
let streaming = false;
let cancelStream = null;

export const meta = {
  title: 'Assistant',
  subtitle: 'Ask questions across the matter. Every answer cites the passage it came from.',
};

export function actions() {
  return [el('button', { class: 'btn', text: 'New thread', onclick: newThread })];
}

export function teardown() {
  cancelStream?.();
  cancelStream = null;
  streaming = false;
}

export async function render(root) {
  clear(root);

  if (!readyDocuments().length) {
    root.append(el('div', { class: 'view-pad' }, [
      el('div', { class: 'empty' }, [
        el('div', { class: 'empty-glyph', text: '◈' }),
        el('h3', { text: 'Nothing to ask about yet' }),
        el('p', { text: 'Upload documents to the vault and the assistant will answer from them, with citations.' }),
      ]),
    ]));
    return;
  }

  threads = (await api.listThreads(state.workspaceId)).threads;
  if (!threads.length) {
    const thread = await api.createThread(state.workspaceId);
    threads = [thread];
  }
  if (!state.threadId || !threads.some((t) => t.id === state.threadId)) {
    state.threadId = threads[0].id;
  }
  messages = (await api.getThread(state.threadId)).messages;

  const shell = el('div', { class: 'chat' });
  shell.append(sidebar(), main());
  root.append(shell);
  paintLog();
  scrollDown();
}

// ---------------------------------------------------------------- sidebar

function sidebar() {
  const list = el('div', { class: 'thread-list' }, threads.map((thread) =>
    el('button', {
      class: `thread-item ${thread.id === state.threadId ? 'active' : ''}`,
      title: thread.title,
      text: thread.title,
      onclick: async () => {
        if (streaming) return toast('Wait for the current answer to finish.');
        state.threadId = thread.id;
        await render($('#view'));
      },
    })));

  return el('aside', { class: 'chat-side' }, [
    el('div', { class: 'chat-side-head' }, [
      el('button', { class: 'btn btn-sm', style: 'width:100%', text: '+ New thread', onclick: newThread }),
    ]),
    list,
    scopePanel(),
  ]);
}

function scopePanel() {
  const documents = readyDocuments();
  const all = el('input', {
    type: 'checkbox',
    checked: state.scopeDocumentIds.length === 0,
    onchange: (event) => {
      state.scopeDocumentIds = event.target.checked ? [] : documents.map((d) => d.id);
      render($('#view'));
    },
  });
  all.style.width = 'auto';

  const items = documents.map((doc) => {
    const box = el('input', {
      type: 'checkbox',
      checked: state.scopeDocumentIds.length === 0 || state.scopeDocumentIds.includes(doc.id),
      onchange: (event) => {
        const current = new Set(
          state.scopeDocumentIds.length ? state.scopeDocumentIds : documents.map((d) => d.id),
        );
        if (event.target.checked) current.add(doc.id); else current.delete(doc.id);
        state.scopeDocumentIds = current.size === documents.length ? [] : [...current];
        const label = $('#scope-count');
        if (label) label.textContent = scopeLabel();
      },
    });
    box.style.width = 'auto';
    return el('label', { class: 'scope-item', title: doc.title }, [box, el('span', { text: doc.title })]);
  });

  return el('div', { class: 'scope-bar' }, [
    el('div', { style: 'display:flex;justify-content:space-between;align-items:center' }, [
      el('strong', { style: 'font-size:11px;letter-spacing:.06em;text-transform:uppercase;color:var(--ink-4)', text: 'Scope' }),
      el('span', { class: 'small muted', id: 'scope-count', text: scopeLabel() }),
    ]),
    el('label', { class: 'scope-item', style: 'margin-top:6px' }, [all, el('span', { text: 'All documents' })]),
    el('div', { class: 'scope-list' }, items),
  ]);
}

function scopeLabel() {
  const total = readyDocuments().length;
  const chosen = state.scopeDocumentIds.length || total;
  return chosen === total ? `all ${total}` : `${chosen} of ${total}`;
}

// ---------------------------------------------------------------- main

function main() {
  const textarea = el('textarea', {
    rows: 1, id: 'composer',
    placeholder: 'Ask about the documents in this matter…',
    oninput: (event) => {
      event.target.style.height = 'auto';
      event.target.style.height = `${Math.min(event.target.scrollHeight, 190)}px`;
    },
    onkeydown: (event) => {
      if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();
        send();
      }
    },
  });

  return el('div', { class: 'chat-main' }, [
    el('div', { class: 'chat-log', id: 'chat-log' }, [el('div', { class: 'chat-inner', id: 'chat-inner' })]),
    el('div', { class: 'composer' }, [
      el('div', { class: 'composer-inner' }, [
        el('div', { class: 'composer-box' }, [
          textarea,
          el('button', { class: 'btn btn-primary', id: 'send-btn', text: 'Ask', onclick: send }),
        ]),
        el('p', { class: 'composer-hint', text: 'Answers are drawn only from this matter’s documents. Verify citations before relying on them.' }),
      ]),
    ]),
  ]);
}

function paintLog() {
  const inner = $('#chat-inner');
  clear(inner);

  if (!messages.length) {
    inner.append(el('div', { style: 'padding:26px 0' }, [
      el('h3', { style: 'font-size:16px;font-weight:600;margin-bottom:5px', text: 'Ask about this matter' }),
      el('p', { class: 'small muted', text: `${readyDocuments().length} documents are indexed and in scope.` }),
      el('div', { class: 'suggestions' }, SUGGESTIONS.map((question) =>
        el('button', {
          class: 'suggestion', text: question,
          onclick: () => { $('#composer').value = question; send(); },
        }))),
    ]));
    return;
  }

  for (const message of messages) inner.append(messageNode(message));
}

function messageNode(message) {
  const node = el('div', { class: `msg msg-${message.role}` }, [
    el('div', { class: 'msg-role', text: message.role === 'user' ? 'You' : 'Lexara' }),
  ]);

  const body = el('div', { class: 'msg-body' });
  if (message.role === 'user') body.textContent = message.content;
  else body.innerHTML = markdown(message.content);
  node.append(body);

  if (message.citations?.length) node.append(sourcesNode(message.citations));
  wireCitations(body, message.citations || []);
  return node;
}

function sourcesNode(citations) {
  return el('div', { class: 'sources' }, citations.map((source) =>
    el('button', {
      class: 'source-pill',
      title: source.snippet,
      onclick: () => openDocument(source.document_id, source.snippet),
    }, [
      el('b', { text: source.n }),
      el('span', { text: source.title + (source.page ? ` · p.${source.page}` : '') }),
    ])));
}

function wireCitations(body, citations) {
  for (const button of body.querySelectorAll('.cite')) {
    const number = Number(button.dataset.cite);
    const source = citations.find((c) => c.n === number);
    button.title = source ? `${source.title}${source.page ? ` · p.${source.page}` : ''}` : 'Source';
    button.onclick = () => {
      if (!source) return;
      drawer(source.title,
        el('div', { class: 'drawer-section' }, [
          el('h3', { text: `Excerpt ${source.n}${source.page ? ` — page ${source.page}` : ''}` }),
          el('div', { class: 'quote-block', text: source.snippet }),
        ]),
        el('button', {
          class: 'btn btn-sm', text: 'Open full document',
          onclick: () => openDocument(source.document_id, source.snippet),
        }),
      );
    };
  }
}

// ---------------------------------------------------------------- sending

async function send() {
  if (streaming) return;
  const textarea = $('#composer');
  const content = textarea.value.trim();
  if (!content) return;
  if (!state.llmReady) return toast('Set ANTHROPIC_API_KEY to use the assistant.', 'error');

  textarea.value = '';
  textarea.style.height = 'auto';
  streaming = true;
  $('#send-btn').disabled = true;

  const inner = $('#chat-inner');
  if (!messages.length) clear(inner);
  messages.push({ role: 'user', content, citations: [] });
  inner.append(messageNode(messages.at(-1)));

  const answerNode = el('div', { class: 'msg msg-assistant' }, [
    el('div', { class: 'msg-role', text: 'Lexara' }),
  ]);
  const body = el('div', { class: 'msg-body' , html: '<span class="spinner"></span>' });
  answerNode.append(body);
  inner.append(answerNode);
  scrollDown();

  let buffer = '';
  sources = [];

  cancelStream = streamMessage(state.threadId, {
    content,
    document_ids: state.scopeDocumentIds.length ? state.scopeDocumentIds : null,
  }, {
    onSources: (received) => { sources = received; },
    onDelta: (text) => {
      buffer += text;
      body.innerHTML = markdown(buffer);
      scrollDown();
    },
    onError: (error) => {
      body.innerHTML = '';
      body.append(el('p', { style: 'color:var(--high)', text: error.message }));
      finish();
    },
    onDone: async ({ citations }) => {
      const message = { role: 'assistant', content: buffer, citations: citations || [] };
      messages.push(message);
      answerNode.replaceWith(messageNode(message));
      scrollDown();
      finish();
      // The first message renames the thread; keep the sidebar honest.
      const refreshed = (await api.listThreads(state.workspaceId)).threads;
      if (refreshed.find((t) => t.id === state.threadId)?.title !== threads.find((t) => t.id === state.threadId)?.title) {
        threads = refreshed;
        const side = document.querySelector('.chat-side');
        if (side) side.replaceWith(sidebar());
      }
    },
  });
}

function finish() {
  streaming = false;
  cancelStream = null;
  const button = $('#send-btn');
  if (button) button.disabled = false;
}

function scrollDown() {
  const log = $('#chat-log');
  if (log) log.scrollTop = log.scrollHeight;
}

async function newThread() {
  if (streaming) return toast('Wait for the current answer to finish.');
  const thread = await api.createThread(state.workspaceId);
  state.threadId = thread.id;
  await render($('#view'));
  $('#composer')?.focus();
}
