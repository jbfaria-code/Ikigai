// The vault: upload documents, browse them, read the extracted text.

import { api } from '../api.js';
import {
  $, clear, confirmDialog, drawer, el, escapeHtml, formatBytes, formatDate,
  modal, plural, toast,
} from '../ui.js';
import { documentById, loadDocuments, state } from '../state.js';

const STATUS_CHIPS = {
  ready:     { label: 'Indexed',   cls: 'chip-good' },
  needs_ocr: { label: 'Needs OCR', cls: 'chip-medium' },
  empty:     { label: 'No text',   cls: 'chip-medium' },
  failed:    { label: 'Failed',    cls: 'chip-high' },
};

export const meta = {
  title: 'Vault',
  subtitle: 'Every document in the matter, extracted and indexed for search.',
};

export function actions() {
  return [
    el('button', { class: 'btn', text: 'Search', onclick: openSearch }),
    el('button', {
      class: 'btn btn-primary',
      text: 'Upload documents',
      onclick: () => $('#file-input')?.click(),
    }),
  ];
}

export function render(root) {
  clear(root);
  const page = el('div', { class: 'view-pad' });

  page.append(
    el('input', {
      type: 'file', id: 'file-input', multiple: true, hidden: true,
      accept: '.pdf,.docx,.txt,.md,.markdown',
      onchange: (event) => { upload(event.target.files); event.target.value = ''; },
    }),
    dropzone(),
  );

  if (state.documents.length) {
    page.append(
      el('div', { class: 'section-head' }, [
        el('h2', { text: plural(state.documents.length, 'document') }),
        el('p', {
          text: `${plural(state.documents.reduce((sum, d) => sum + d.pages, 0), 'page')} · `
            + `${state.documents.reduce((sum, d) => sum + d.words, 0).toLocaleString()} words indexed`,
        }),
      ]),
      table(),
    );
  } else {
    page.append(el('div', { class: 'empty' }, [
      el('div', { class: 'empty-glyph', text: '▤' }),
      el('h3', { text: 'No documents yet' }),
      el('p', {
        text: 'Upload contracts, policies, or filings. Lexara extracts the text, '
          + 'indexes it for search, and makes it available to every other tool in the matter.',
      }),
    ]));
  }

  root.append(page);
}

function dropzone() {
  const zone = el('div', {
    class: 'dropzone',
    onclick: () => $('#file-input')?.click(),
    ondragover: (event) => { event.preventDefault(); zone.classList.add('over'); },
    ondragleave: () => zone.classList.remove('over'),
    ondrop: (event) => {
      event.preventDefault();
      zone.classList.remove('over');
      upload(event.dataTransfer.files);
    },
  }, [
    el('strong', { text: 'Drop files here, or click to browse' }),
    el('span', { class: 'small', text: 'PDF, Word (.docx), plain text and markdown · up to 25 MB each' }),
  ]);
  return zone;
}

function table() {
  const body = el('tbody');

  for (const doc of state.documents) {
    const chip = STATUS_CHIPS[doc.status] ?? { label: doc.status, cls: '' };
    body.append(el('tr', {}, [
      el('td', {}, [
        el('div', { class: 'doc-title', text: doc.title, onclick: () => openDocument(doc.id) }),
        el('div', { class: 'doc-file', text: doc.filename }),
      ]),
      el('td', { class: 'col-tight' }, [
        el('span', { class: `chip ${chip.cls}`, text: chip.label, title: doc.error || '' }),
      ]),
      el('td', { class: 'col-tight small muted', text: doc.kind.toUpperCase() }),
      el('td', { class: 'col-tight small muted', text: doc.pages ? `${doc.pages}` : '—' }),
      el('td', { class: 'col-tight small muted', text: doc.words ? doc.words.toLocaleString() : '—' }),
      el('td', { class: 'col-tight small muted', text: formatBytes(doc.size_bytes) }),
      el('td', { class: 'col-tight small muted', text: formatDate(doc.created_at) }),
      el('td', { class: 'col-tight' }, [
        el('div', { class: 'row-actions' }, [
          el('button', { class: 'btn btn-sm btn-ghost', text: 'Download',
            onclick: () => window.open(`/api/documents/${doc.id}/file`, '_blank') }),
          el('button', { class: 'btn btn-sm btn-ghost', text: 'Rename',
            onclick: () => rename(doc) }),
          el('button', { class: 'btn btn-sm btn-ghost btn-danger', text: 'Delete',
            onclick: () => remove(doc) }),
        ]),
      ]),
    ]));
  }

  return el('div', { class: 'card' }, [
    el('table', { class: 'doc-table' }, [
      el('thead', {}, [
        el('tr', {}, ['Document', 'Status', 'Type', 'Pages', 'Words', 'Size', 'Added', '']
          .map((label) => el('th', { text: label }))),
      ]),
      body,
    ]),
  ]);
}

async function upload(fileList) {
  const files = [...(fileList || [])];
  if (!files.length) return;
  if (!state.workspaceId) return toast('Create a matter first.', 'error');

  toast(`Uploading ${plural(files.length, 'file')}…`);
  try {
    const result = await api.uploadDocuments(state.workspaceId, files);
    for (const rejected of result.rejected || []) {
      toast(`${rejected.filename}: ${rejected.error}`, 'error');
    }
    const ocr = (result.documents || []).filter((d) => d.status === 'needs_ocr');
    if (ocr.length) toast(`${plural(ocr.length, 'file')} had no selectable text — OCR needed.`, 'error');
    if (result.documents?.length) toast(`Added ${plural(result.documents.length, 'document')}.`);
    await loadDocuments();
  } catch (error) {
    toast(error.message, 'error');
  }
}

async function rename(doc) {
  const values = await modal({
    title: 'Rename document',
    fields: [{ name: 'title', label: 'Title', value: doc.title }],
  });
  if (!values?.title) return;
  await api.renameDocument(doc.id, values.title);
  await loadDocuments();
}

async function remove(doc) {
  const ok = await confirmDialog(
    'Delete document',
    `“${doc.title}” will be removed from the matter, along with any review cells and citations that reference it.`,
  );
  if (!ok) return;
  await api.deleteDocument(doc.id);
  toast('Document deleted.');
  await loadDocuments();
}

// ---------------------------------------------------------------- viewer

export async function openDocument(documentId, highlight = '') {
  const doc = documentById(documentId);
  drawer(doc?.title || 'Document', el('p', { class: 'small muted', text: 'Loading…' }));

  try {
    const { text } = await api.documentText(documentId);
    const body = el('div', { class: 'doc-text' });
    body.innerHTML = highlight ? highlightIn(text, highlight) : escapeHtml(text);

    drawer(doc?.title || 'Document',
      el('div', { class: 'drawer-section' }, [
        el('div', { class: 'topbar-actions', style: 'justify-content:flex-start' }, [
          el('button', {
            class: 'btn btn-sm', text: 'Catalogue with AI',
            onclick: (event) => catalogue(documentId, event.target),
          }),
          el('button', {
            class: 'btn btn-sm', text: 'Download original',
            onclick: () => window.open(`/api/documents/${documentId}/file`, '_blank'),
          }),
        ]),
      ]),
      el('div', { class: 'drawer-section', id: 'catalogue-slot' }),
      el('div', { class: 'drawer-section' }, [el('h3', { text: 'Extracted text' }), body]),
    );

    if (highlight) {
      setTimeout(() => $('mark', body)?.scrollIntoView({ block: 'center', behavior: 'smooth' }), 60);
    }
  } catch (error) {
    toast(error.message, 'error');
  }
}

async function catalogue(documentId, button) {
  const slot = $('#catalogue-slot');
  button.disabled = true;
  clear(slot);
  slot.append(el('p', { class: 'small muted', html: '<span class="spinner"></span> Reading the document…' }));

  try {
    const data = await api.intake(documentId);
    clear(slot);
    slot.append(
      el('h3', { text: 'Catalogue' }),
      el('div', { class: 'card card-pad small' }, [
        row('Type', data.doc_type),
        row('Parties', (data.parties || []).join(' · ')),
        row('Effective date', data.effective_date),
        row('Governing law', data.governing_law),
        el('p', { class: 'muted', style: 'margin-top:8px', text: data.summary || '' }),
      ]),
    );
  } catch (error) {
    clear(slot);
    slot.append(el('p', { class: 'small', style: 'color:var(--high)', text: error.message }));
  } finally {
    button.disabled = false;
  }
}

function row(label, value) {
  if (!value) return null;
  return el('div', { style: 'display:flex;gap:8px;margin-bottom:3px' }, [
    el('span', { class: 'muted', style: 'min-width:104px', text: label }),
    el('span', { text: value }),
  ]);
}

function highlightIn(text, needle) {
  const trimmed = needle.trim().slice(0, 300);
  if (!trimmed) return escapeHtml(text);

  const index = text.toLowerCase().indexOf(trimmed.toLowerCase());
  if (index !== -1) {
    return escapeHtml(text.slice(0, index))
      + `<mark>${escapeHtml(text.slice(index, index + trimmed.length))}</mark>`
      + escapeHtml(text.slice(index + trimmed.length));
  }

  // The quote may be normalised differently; fall back to its longest run of words.
  const words = trimmed.split(/\s+/).filter((w) => w.length > 3);
  if (words.length < 3) return escapeHtml(text);
  const probe = words.slice(0, 6).join(' ');
  const loose = text.toLowerCase().indexOf(probe.toLowerCase());
  if (loose === -1) return escapeHtml(text);
  return escapeHtml(text.slice(0, loose))
    + `<mark>${escapeHtml(text.slice(loose, loose + probe.length))}</mark>`
    + escapeHtml(text.slice(loose + probe.length));
}

// ---------------------------------------------------------------- search

async function openSearch() {
  if (!state.documents.length) return toast('Upload a document first.', 'error');

  const input = el('input', { type: 'search', placeholder: 'e.g. limitation of liability cap' });
  const results = el('div', { style: 'margin-top:12px' });

  const run = async () => {
    const query = input.value.trim();
    if (!query) return;
    clear(results);
    results.append(el('p', { class: 'small muted', html: '<span class="spinner"></span> Searching…' }));
    try {
      const data = await api.search(state.workspaceId, query);
      clear(results);
      if (!data.results.length) {
        results.append(el('p', { class: 'small muted', text: 'No passages matched.' }));
        return;
      }
      for (const hit of data.results) {
        results.append(el('button', {
          class: 'run-item', style: 'display:block;margin-bottom:6px',
          onclick: () => { document.querySelector('#modal-scrim').hidden = true; openDocument(hit.document_id, hit.preview.slice(0, 120)); },
        }, [
          el('strong', { text: hit.title }),
          hit.page ? el('span', { class: 'muted small', text: ` · p.${hit.page}` }) : null,
          el('p', { class: 'small muted', style: 'margin-top:3px', text: hit.preview.slice(0, 220) + '…' }),
        ]));
      }
    } catch (error) {
      clear(results);
      results.append(el('p', { class: 'small', style: 'color:var(--high)', text: error.message }));
    }
  };

  input.addEventListener('keydown', (event) => { if (event.key === 'Enter') run(); });

  modal({
    title: 'Search the vault',
    body: el('div', {}, [
      el('label', { class: 'field' }, [el('span', { text: 'Query' }), input]),
      el('button', { class: 'btn btn-sm', text: 'Search', onclick: run }),
      results,
    ]),
    confirmLabel: 'Done',
  });
  setTimeout(() => input.focus(), 50);
}
