// Tabular review: documents down the side, questions across the top, one
// model call per cell. The grid streams in as cells finish.

import { api } from '../api.js';
import {
  $, clear, confirmDialog, drawer, el, markdown, modal, plural, toast,
} from '../ui.js';
import { loadDocuments, readyDocuments, state } from '../state.js';
import { openDocument } from './vault.js';

const KIND_LABELS = {
  text: 'Text', yes_no: 'Yes / No', date: 'Date',
  number: 'Number', currency: 'Currency', list: 'List',
};

const KIND_OPTIONS = Object.entries(KIND_LABELS).map(([value, label]) => ({ value, label }));

const STARTER_COLUMNS = [
  { header: 'Parties', prompt: 'Who are the contracting parties, as named in the document?', kind: 'list' },
  { header: 'Effective date', prompt: 'What is the effective date or commencement date?', kind: 'date' },
  { header: 'Term', prompt: 'What is the initial term, and does it renew automatically?', kind: 'text' },
  { header: 'Governing law', prompt: 'What law governs the agreement?', kind: 'text' },
  { header: 'Liability cap', prompt: 'What is the cap on aggregate liability, and what does it exclude?', kind: 'text' },
  { header: 'Termination for convenience', prompt: 'May either party terminate for convenience, and on what notice?', kind: 'text' },
  { header: 'Assignment on change of control', prompt: 'Is assignment restricted, and is a change of control treated as an assignment?', kind: 'yes_no' },
];

let snapshot = null;
let tables = [];
let pollTimer = null;

export const meta = {
  title: 'Tabular review',
  subtitle: 'Ask the same questions of every document and get a grid you can audit.',
};

export function actions() {
  if (!snapshot) return [];
  return [
    el('button', { class: 'btn', text: 'Draft memo', onclick: draftMemo }),
    el('button', {
      class: 'btn', text: 'Export CSV',
      onclick: () => window.open(`/api/tables/${snapshot.table.id}/export.csv`, '_blank'),
    }),
    el('button', { class: 'btn btn-primary', text: 'Run review', onclick: () => run({}) }),
  ];
}

export function teardown() {
  clearTimeout(pollTimer);
  pollTimer = null;
}

export async function render(root) {
  clear(root);
  root.append(el('div', { class: 'view-pad' }, [
    el('p', { class: 'small muted', html: '<span class="spinner"></span> Loading reviews…' }),
  ]));

  try {
    tables = (await api.listTables(state.workspaceId)).tables;
  } catch (error) {
    return renderError(root, error);
  }

  if (!tables.length) return renderEmpty(root);

  if (!state.tableId || !tables.some((t) => t.id === state.tableId)) {
    state.tableId = tables[0].id;
  }
  try {
    snapshot = await api.getTable(state.tableId);
  } catch (error) {
    return renderError(root, error);
  }

  paint(root);
}

function renderError(root, error) {
  clear(root);
  root.append(el('div', { class: 'view-pad' }, [
    el('p', { class: 'small', style: 'color:var(--high)', text: error.message }),
  ]));
}

function renderEmpty(root) {
  snapshot = null;
  clear(root);
  root.append(el('div', { class: 'view-pad' }, [
    el('div', { class: 'empty' }, [
      el('div', { class: 'empty-glyph', text: '▦' }),
      el('h3', { text: 'No reviews yet' }),
      el('p', {
        text: 'A review puts your documents down the side and your questions across the top. '
          + 'Every cell is answered from the document itself and carries the quote it came from.',
      }),
      el('button', { class: 'btn btn-primary', text: 'New review', onclick: createTable }),
    ]),
  ]));
  refreshTopbar();
}

function paint(root) {
  clear(root);
  const shell = el('div', { class: 'view-flush' });
  shell.append(toolbar(), gridScroll());
  root.append(shell);
  refreshTopbar();
  schedulePoll();
}

function refreshTopbar() {
  window.dispatchEvent(new CustomEvent('lexara:topbar'));
}

// ---------------------------------------------------------------- toolbar

function toolbar() {
  const picker = el('select', {
    style: 'width:auto;min-width:190px',
    onchange: async (event) => {
      state.tableId = event.target.value;
      snapshot = await api.getTable(state.tableId);
      paint($('#view'));
    },
  }, tables.map((t) => el('option', {
    value: t.id, text: t.name, selected: t.id === state.tableId,
  })));

  const { progress } = snapshot;
  const percent = progress.total ? Math.round((progress.done + progress.error) / progress.total * 100) : 0;

  return el('div', { class: 'grid-toolbar' }, [
    picker,
    el('button', { class: 'btn btn-sm', text: 'New', onclick: createTable }),
    el('button', { class: 'btn btn-sm', text: 'Rename', onclick: renameTable }),
    el('button', { class: 'btn btn-sm btn-danger', text: 'Delete', onclick: deleteTable }),

    el('span', { style: 'width:1px;height:20px;background:var(--line);margin:0 3px' }),

    el('button', { class: 'btn btn-sm', text: 'Add column', onclick: () => addColumn() }),
    el('button', { class: 'btn btn-sm', text: 'Suggest columns', onclick: suggestColumns }),
    el('button', { class: 'btn btn-sm', text: 'Documents', onclick: pickRows }),
    el('button', {
      class: 'btn btn-sm', text: 'Fill blanks',
      onclick: () => run({ only_empty: true }),
    }),

    el('div', { style: 'margin-left:auto;display:flex;align-items:center;gap:9px' }, [
      progress.running ? el('span', { class: 'spinner' }) : null,
      el('span', { class: 'small muted', text: `${progress.done + progress.error} / ${progress.total} cells` }),
      el('div', { class: 'progress-bar' }, [el('div', { style: `width:${percent}%` })]),
      progress.error
        ? el('span', { class: 'chip chip-high', text: `${progress.error} failed` })
        : null,
    ]),
  ]);
}

// ---------------------------------------------------------------- grid

function gridScroll() {
  const wrapper = el('div', { class: 'grid-scroll' });
  const { columns, rows } = snapshot;

  if (!rows.length) {
    wrapper.append(el('div', { class: 'empty' }, [
      el('h3', { text: 'No documents in this review' }),
      el('p', { text: 'Choose which of the matter’s documents belong in this grid.' }),
      el('button', { class: 'btn btn-primary', text: 'Choose documents', onclick: pickRows }),
    ]));
    return wrapper;
  }
  if (!columns.length) {
    wrapper.append(el('div', { class: 'empty' }, [
      el('h3', { text: 'No columns yet' }),
      el('p', { text: 'Each column is a question asked of every document in the grid.' }),
      el('div', { style: 'display:flex;gap:8px;justify-content:center;flex-wrap:wrap' }, [
        el('button', { class: 'btn btn-primary', text: 'Suggest columns', onclick: suggestColumns }),
        el('button', { class: 'btn', text: 'Use standard contract columns', onclick: addStarterColumns }),
        el('button', { class: 'btn', text: 'Add column', onclick: () => addColumn() }),
      ]),
    ]));
    return wrapper;
  }

  const head = el('tr', {}, [el('th', { class: 'col-doc', text: 'Document' })]);
  for (const column of columns) {
    head.append(el('th', {}, [
      el('div', { class: 'col-head' }, [
        el('div', { class: 'col-head-main' }, [
          el('span', { class: 'col-head-name', text: column.header, title: column.prompt }),
          el('span', { class: 'col-head-kind', text: KIND_LABELS[column.kind] || column.kind }),
        ]),
        el('button', {
          class: 'icon-btn col-menu', text: '⋯', title: 'Column options',
          onclick: () => editColumn(column),
        }),
      ]),
    ]));
  }

  const body = el('tbody');
  for (const row of snapshot.rows) {
    const tr = el('tr', {}, [
      el('td', { class: 'col-doc' }, [
        el('div', { class: 'doc-cell-name doc-title', text: row.title, onclick: () => openDocument(row.document_id) }),
        el('div', { class: 'doc-cell-meta', text: `${row.pages ? `${row.pages} pp · ` : ''}${row.words.toLocaleString()} words` }),
      ]),
    ]);
    for (const column of snapshot.columns) {
      tr.append(cellNode(column, row));
    }
    body.append(tr);
  }

  wrapper.append(el('table', { class: 'grid' }, [el('thead', {}, [head]), body]));
  return wrapper;
}

function cellNode(column, row) {
  const key = `${column.id}:${row.document_id}`;
  const cell = snapshot.cells[key];
  const td = el('td', {
    class: 'cell cell-wrap',
    dataset: { key },
    onclick: () => openCell(column, row),
  });
  paintCell(td, cell);
  return td;
}

function paintCell(td, cell) {
  clear(td);
  td.classList.toggle('cell-edited', Boolean(cell?.edited));

  if (!cell || cell.status === 'empty') {
    td.append(el('span', { class: 'cell-empty', text: '—' }));
    return;
  }
  if (cell.status === 'queued' || cell.status === 'running') {
    td.append(el('span', { class: 'dot-pulse' }));
    return;
  }
  if (cell.status === 'error') {
    td.append(el('span', { class: 'cell-error', text: 'Failed', title: cell.reasoning || '' }));
    return;
  }

  td.append(el('div', { class: 'cell-value', text: cell.value || '—' }));
  const meta = el('div', { class: 'cell-meta' });
  if (cell.confidence) {
    meta.append(el('span', { class: `conf conf-${cell.confidence}`, text: cell.confidence }));
  }
  if (cell.page) meta.append(el('span', { class: 'small muted', text: `p.${cell.page}` }));
  if (cell.edited) meta.append(el('span', { class: 'chip chip-accent', text: 'edited' }));
  if (meta.childNodes.length) td.append(meta);
}

// ---------------------------------------------------------------- polling

function schedulePoll() {
  clearTimeout(pollTimer);
  if (!snapshot?.progress.running) return;

  pollTimer = setTimeout(async () => {
    try {
      const data = await api.tableProgress(snapshot.table.id);
      snapshot.cells = data.cells;
      snapshot.progress = data.progress;

      for (const [key, cell] of Object.entries(data.cells)) {
        const td = document.querySelector(`.cell[data-key="${CSS.escape(key)}"]`);
        if (td) paintCell(td, cell);
      }
      const view = $('#view');
      const scroll = view.querySelector('.grid-scroll');
      const toolbarNode = view.querySelector('.grid-toolbar');
      if (toolbarNode && scroll) toolbarNode.replaceWith(toolbar());

      if (!data.progress.running) {
        toast(data.progress.error
          ? `Review finished with ${plural(data.progress.error, 'failed cell')}.`
          : 'Review complete.');
      }
      schedulePoll();
    } catch {
      schedulePoll();
    }
  }, 1500);
}

// ---------------------------------------------------------------- actions

async function run(options) {
  if (!snapshot) return;
  if (!state.llmReady) return toast('Set ANTHROPIC_API_KEY to run reviews.', 'error');

  try {
    const data = await api.runTable(snapshot.table.id, options);
    if (!data.queued) return toast('Nothing to run — every cell is already filled.');
    toast(`Queued ${plural(data.queued, 'cell')}.`);
    snapshot = data.snapshot;
    paint($('#view'));
  } catch (error) {
    toast(error.message, 'error');
  }
}

async function createTable() {
  const values = await modal({
    title: 'New review',
    fields: [{
      name: 'name', label: 'Name', value: 'Contract review',
      placeholder: 'e.g. Lease portfolio — key terms',
    }],
    body: el('p', {
      class: 'small muted',
      text: 'Every ready document in the matter is added as a row. You can change that afterwards.',
    }),
    confirmLabel: 'Create',
  });
  if (!values?.name) return;

  const table = await api.createTable(state.workspaceId, {
    name: values.name,
    document_ids: readyDocuments().map((d) => d.id),
  });
  state.tableId = table.table.id;
  toast('Review created. Add columns to get started.');
  await render($('#view'));
}

async function renameTable() {
  const values = await modal({
    title: 'Rename review',
    fields: [{ name: 'name', label: 'Name', value: snapshot.table.name }],
  });
  if (!values?.name) return;
  await api.renameTable(snapshot.table.id, values.name);
  await render($('#view'));
}

async function deleteTable() {
  const ok = await confirmDialog('Delete review', `“${snapshot.table.name}” and all of its extracted cells will be deleted.`);
  if (!ok) return;
  await api.deleteTable(snapshot.table.id);
  state.tableId = null;
  toast('Review deleted.');
  await render($('#view'));
}

async function addColumn(preset = {}) {
  const values = await modal({
    title: 'Add column',
    fields: [
      { name: 'header', label: 'Column header', value: preset.header || '', placeholder: 'Governing law' },
      {
        name: 'prompt', label: 'Question asked of each document', type: 'textarea', rows: 3,
        value: preset.prompt || '',
        placeholder: 'What law governs the agreement, and which courts have jurisdiction?',
        hint: 'Be specific. The model answers only from the document and quotes its source.',
      },
      { name: 'kind', label: 'Answer type', type: 'select', options: KIND_OPTIONS, value: preset.kind || 'text' },
    ],
    confirmLabel: 'Add and run',
  });
  if (!values?.header) return;

  await api.addColumns(snapshot.table.id, [values], state.llmReady);
  await render($('#view'));
}

async function editColumn(column) {
  const values = await modal({
    title: 'Edit column',
    fields: [
      { name: 'header', label: 'Column header', value: column.header },
      { name: 'prompt', label: 'Question', type: 'textarea', rows: 3, value: column.prompt },
      { name: 'kind', label: 'Answer type', type: 'select', options: KIND_OPTIONS, value: column.kind },
    ],
    body: el('button', {
      class: 'btn btn-sm btn-danger', text: 'Delete this column',
      onclick: async () => {
        $('#modal-scrim').hidden = true;
        await api.deleteColumn(column.id);
        await render($('#view'));
      },
    }),
    confirmLabel: 'Save and re-run',
  });
  if (!values?.header) return;

  await api.updateColumn(column.id, values);
  if (state.llmReady) await api.runTable(snapshot.table.id, { column_ids: [column.id] });
  await render($('#view'));
}

async function addStarterColumns() {
  await api.addColumns(snapshot.table.id, STARTER_COLUMNS, state.llmReady);
  toast(`Added ${plural(STARTER_COLUMNS.length, 'column')}.`);
  await render($('#view'));
}

async function suggestColumns() {
  if (!state.llmReady) return toast('Set ANTHROPIC_API_KEY to use suggestions.', 'error');
  if (!snapshot.rows.length) return toast('Add documents to the review first.');

  toast('Reading the document set…');
  let suggested;
  try {
    suggested = (await api.suggestColumns(snapshot.table.id)).columns;
  } catch (error) {
    return toast(error.message, 'error');
  }
  if (!suggested?.length) return toast('No suggestions came back.');

  const boxes = suggested.map((column) => {
    const input = el('input', { type: 'checkbox', checked: true });
    input.style.width = 'auto';
    input._column = column;
    return el('label', { class: 'scope-item', style: 'align-items:flex-start;padding:6px 0' }, [
      input,
      el('span', { style: 'white-space:normal' }, [
        el('strong', { text: column.header }),
        el('span', { class: 'chip', style: 'margin-left:6px', text: KIND_LABELS[column.kind] || column.kind }),
        el('div', { class: 'small muted', text: column.prompt }),
      ]),
    ]);
  });

  const ok = await modal({
    title: 'Suggested columns',
    body: el('div', {}, [
      el('p', { class: 'small muted', style: 'margin-bottom:10px', text: 'Uncheck anything you do not need.' }),
      el('div', { style: 'max-height:46vh;overflow-y:auto' }, boxes),
    ]),
    confirmLabel: 'Add selected',
  });
  if (!ok) return;

  const chosen = boxes
    .map((box) => box.querySelector('input'))
    .filter((input) => input.checked)
    .map((input) => input._column);
  if (!chosen.length) return;

  await api.addColumns(snapshot.table.id, chosen, state.llmReady);
  toast(`Added ${plural(chosen.length, 'column')}.`);
  await render($('#view'));
}

async function pickRows() {
  await loadDocuments();
  const current = new Set(snapshot.rows.map((r) => r.document_id));

  const boxes = state.documents.map((doc) => {
    const input = el('input', {
      type: 'checkbox',
      checked: current.has(doc.id) || (current.size === 0 && doc.status === 'ready'),
      disabled: doc.status !== 'ready',
    });
    input.style.width = 'auto';
    input._id = doc.id;
    return el('label', { class: 'scope-item' }, [
      input,
      el('span', { text: doc.title }),
      doc.status !== 'ready' ? el('span', { class: 'chip chip-medium', text: 'no text' }) : null,
    ]);
  });

  const ok = await modal({
    title: 'Documents in this review',
    body: el('div', { style: 'max-height:50vh;overflow-y:auto' }, boxes),
    confirmLabel: 'Save',
  });
  if (!ok) return;

  const chosen = boxes
    .map((box) => box.querySelector('input'))
    .filter((input) => input.checked)
    .map((input) => input._id);

  await api.setRows(snapshot.table.id, chosen);
  await render($('#view'));
}

// ---------------------------------------------------------------- cell detail

function openCell(column, row) {
  const cell = snapshot.cells[`${column.id}:${row.document_id}`] || {};

  const valueInput = el('textarea', { rows: 3, value: cell.value || '' });

  drawer(column.header,
    el('div', { class: 'drawer-section' }, [
      el('h3', { text: 'Document' }),
      el('button', {
        class: 'btn btn-sm', text: row.title,
        onclick: () => openDocument(row.document_id, cell.quote || ''),
      }),
    ]),
    el('div', { class: 'drawer-section' }, [
      el('h3', { text: 'Question' }),
      el('p', { class: 'small', text: column.prompt }),
    ]),
    el('div', { class: 'drawer-section' }, [
      el('h3', { text: 'Answer' }),
      valueInput,
      el('div', { style: 'display:flex;gap:8px;margin-top:8px;align-items:center' }, [
        el('button', {
          class: 'btn btn-sm btn-primary', text: 'Save override',
          onclick: async () => {
            const updated = await api.editCell(snapshot.table.id, column.id, row.document_id, valueInput.value);
            snapshot.cells[`${column.id}:${row.document_id}`] = updated;
            const td = document.querySelector(`.cell[data-key="${CSS.escape(`${column.id}:${row.document_id}`)}"]`);
            if (td) paintCell(td, updated);
            toast('Answer overridden.');
          },
        }),
        el('button', {
          class: 'btn btn-sm', text: 'Re-run cell',
          onclick: async () => {
            if (!state.llmReady) return toast('Set ANTHROPIC_API_KEY to re-run.', 'error');
            await api.runTable(snapshot.table.id, {
              column_ids: [column.id], document_ids: [row.document_id],
            });
            toast('Re-running…');
            snapshot.progress.running = true;
            schedulePoll();
          },
        }),
        cell.confidence
          ? el('span', { class: `conf conf-${cell.confidence}`, text: `${cell.confidence} confidence` })
          : null,
      ]),
    ]),
    cell.quote ? el('div', { class: 'drawer-section' }, [
      el('h3', { text: `Source${cell.page ? ` — page ${cell.page}` : ''}` }),
      el('div', { class: 'quote-block', text: cell.quote }),
      el('button', {
        class: 'btn btn-sm', style: 'margin-top:8px', text: 'Show in document',
        onclick: () => openDocument(row.document_id, cell.quote),
      }),
    ]) : null,
    cell.reasoning ? el('div', { class: 'drawer-section' }, [
      el('h3', { text: cell.status === 'error' ? 'Error' : 'Reasoning' }),
      el('p', { class: 'small muted', text: cell.reasoning }),
    ]) : null,
  );
}

// ---------------------------------------------------------------- memo

async function draftMemo() {
  if (!state.llmReady) return toast('Set ANTHROPIC_API_KEY to draft a memo.', 'error');
  if (!snapshot?.progress.done) return toast('Run the review first.', 'error');

  const values = await modal({
    title: 'Draft review memo',
    fields: [{
      name: 'focus', label: 'Anything the memo should focus on? (optional)',
      type: 'textarea', rows: 2,
      placeholder: 'e.g. flag every agreement we cannot assign without consent',
    }],
    confirmLabel: 'Draft',
  });
  if (!values) return;

  drawer('Review memo', el('p', { class: 'small muted', html: '<span class="spinner"></span> Drafting…' }));
  try {
    const { memo: text } = await api.memo(snapshot.table.id, values.focus);
    drawer('Review memo',
      el('div', { class: 'drawer-section' }, [
        el('button', {
          class: 'btn btn-sm', text: 'Copy markdown',
          onclick: () => { navigator.clipboard.writeText(text); toast('Copied.'); },
        }),
      ]),
      el('div', { class: 'msg-body', html: markdown(text) }),
    );
  } catch (error) {
    drawer('Review memo', el('p', { class: 'small', style: 'color:var(--high)', text: error.message }));
  }
}
