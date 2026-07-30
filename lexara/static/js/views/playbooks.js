// Playbook review: measure one document against a set of negotiation positions
// and get drafting-ready redlines back.

import { api } from '../api.js';
import { $, clear, confirmDialog, el, formatDate, modal, plural, toast } from '../ui.js';
import { readyDocuments, state } from '../state.js';
import { openDocument } from './vault.js';

const STATUS_CHIP = {
  deviation: { label: 'Deviation', cls: 'chip-high' },
  missing:   { label: 'Missing',   cls: 'chip-medium' },
  unclear:   { label: 'Unclear',   cls: 'chip-low' },
  compliant: { label: 'Compliant', cls: 'chip-good' },
};

const RECOMMENDATION_CHIP = {
  sign: 'chip-good', negotiate: 'chip-medium', escalate: 'chip-high',
};

let playbooks = [];
let runs = [];
let current = null;
let pollTimer = null;

export const meta = {
  title: 'Playbook review',
  subtitle: 'Check a contract against your standard positions and get redlines for the gaps.',
};

export function actions() {
  return [
    current
      ? el('button', {
          class: 'btn', text: 'Export memo',
          onclick: () => window.open(`/api/reviews/${current.id}/export.md`, '_blank'),
        })
      : null,
    el('button', { class: 'btn btn-primary', text: 'New review', onclick: startReview }),
  ].filter(Boolean);
}

export function teardown() {
  clearTimeout(pollTimer);
  pollTimer = null;
}

export async function render(root) {
  clear(root);

  [playbooks, runs] = await Promise.all([
    api.listPlaybooks().then((d) => d.playbooks),
    api.listReviews(state.workspaceId).then((d) => d.reviews),
  ]);

  if (state.reviewId && runs.some((r) => r.id === state.reviewId)) {
    current = await api.getReview(state.reviewId);
  } else {
    current = null;
    state.reviewId = null;
  }

  const page = el('div', { class: 'view-pad' });
  page.append(current ? detail() : list());
  root.append(page);
  refreshTopbar();
  schedulePoll();
}

function refreshTopbar() {
  window.dispatchEvent(new CustomEvent('lexara:topbar'));
}

// ---------------------------------------------------------------- list

function list() {
  const wrap = el('div');

  if (!runs.length) {
    wrap.append(el('div', { class: 'empty' }, [
      el('div', { class: 'empty-glyph', text: '◎' }),
      el('h3', { text: 'No playbook reviews yet' }),
      el('p', {
        text: 'A playbook is the set of positions you take into a negotiation. Lexara checks a '
          + 'document against every rule, flags what falls short, and drafts the replacement language.',
      }),
      el('button', { class: 'btn btn-primary', text: 'Review a document', onclick: startReview }),
    ]));
  } else {
    wrap.append(
      el('div', { class: 'section-head' }, [
        el('h2', { text: plural(runs.length, 'review') }),
      ]),
      el('div', { class: 'run-list' }, runs.map(runRow)),
    );
  }

  wrap.append(
    el('div', { class: 'section-head' }, [
      el('h2', { text: 'Playbooks' }),
      el('p', { text: 'Built-in position sets. You can also paste your own rules when starting a review.' }),
    ]),
    el('div', { class: 'run-list' }, playbooks.map((playbook) =>
      el('button', {
        class: 'run-item',
        onclick: () => previewPlaybook(playbook.key),
      }, [
        el('div', { style: 'flex:1;min-width:0' }, [
          el('strong', { text: playbook.name }),
          el('div', { class: 'muted small', text: playbook.description }),
        ]),
        el('span', { class: 'chip', text: plural(playbook.rule_count, 'rule') }),
      ]))),
  );

  return wrap;
}

function runRow(run) {
  const badge = run.status === 'running'
    ? el('span', { class: 'chip chip-accent', html: '<span class="spinner"></span> running' })
    : run.status === 'error'
      ? el('span', { class: 'chip chip-high', text: 'failed' })
      : el('span', { class: 'chip chip-good', text: 'done' });

  return el('button', {
    class: 'run-item',
    onclick: async () => {
      state.reviewId = run.id;
      await render($('#view'));
    },
  }, [
    el('div', { style: 'flex:1;min-width:0' }, [
      el('strong', { text: run.document_title }),
      el('div', { class: 'muted small', text: `${run.playbook_name} · ${formatDate(run.created_at)}` }),
    ]),
    badge,
    el('span', {
      class: 'icon-btn', text: '×', title: 'Delete review',
      onclick: async (event) => {
        event.stopPropagation();
        const ok = await confirmDialog('Delete review', `The review of “${run.document_title}” will be deleted.`);
        if (!ok) return;
        await api.deleteReview(run.id);
        if (state.reviewId === run.id) state.reviewId = null;
        await render($('#view'));
      },
    }),
  ]);
}

// ---------------------------------------------------------------- detail

function detail() {
  const wrap = el('div');

  wrap.append(el('button', {
    class: 'btn btn-sm btn-ghost', style: 'margin-bottom:14px', text: '← All reviews',
    onclick: async () => { state.reviewId = null; await render($('#view')); },
  }));

  if (current.status === 'running') {
    wrap.append(el('div', { class: 'empty' }, [
      el('div', { class: 'spinner', style: 'width:22px;height:22px;border-width:3px' }),
      el('h3', { style: 'margin-top:14px', text: 'Reviewing…' }),
      el('p', { text: `Checking “${current.document_title}” against ${current.playbook_name}.` }),
    ]));
    return wrap;
  }
  if (current.status === 'error') {
    wrap.append(el('div', { class: 'card card-pad' }, [
      el('h3', { style: 'color:var(--high);margin-bottom:6px', text: 'The review failed' }),
      el('p', { class: 'small muted', text: current.error }),
    ]));
    return wrap;
  }

  const counts = current.counts;
  wrap.append(
    el('div', { class: 'card card-pad', style: 'margin-bottom:16px' }, [
      el('div', { style: 'display:flex;gap:10px;align-items:baseline;flex-wrap:wrap;margin-bottom:9px' }, [
        el('h2', { style: 'font-size:15px;font-weight:600', text: current.document_title }),
        el('span', { class: 'muted small', text: current.playbook_name }),
        el('span', {
          class: `chip ${RECOMMENDATION_CHIP[current.recommendation] || ''}`,
          text: (current.recommendation || 'n/a').toUpperCase(),
        }),
        el('button', {
          class: 'btn btn-sm btn-ghost', style: 'margin-left:auto', text: 'Open document',
          onclick: () => openDocument(current.document_id),
        }),
      ]),
      el('p', { style: 'line-height:1.65', text: current.summary }),
    ]),
    el('div', { class: 'stat-row' }, [
      stat(counts.deviation, 'Deviations'),
      stat(counts.missing, 'Missing'),
      stat(counts.unclear, 'Unclear'),
      stat(counts.compliant, 'Compliant'),
    ]),
  );

  for (const finding of current.findings) wrap.append(findingCard(finding));
  wrap.append(el('p', {
    class: 'small muted', style: 'margin-top:18px;text-align:center',
    text: 'Generated from an AI review. Verify every finding against the source document.',
  }));
  return wrap;
}

function stat(value, label) {
  return el('div', { class: 'stat' }, [
    el('b', { text: String(value ?? 0) }),
    el('span', { text: label }),
  ]);
}

function findingCard(finding) {
  const severity = String(finding.severity || 'none').toLowerCase();
  const status = STATUS_CHIP[finding.status] || { label: finding.status, cls: '' };
  const open = severity === 'high' || finding.status === 'deviation' || finding.status === 'missing';

  const body = el('div', { class: 'finding-body', hidden: !open });
  if (finding.quote) {
    body.append(
      el('h4', { text: `Language at issue${finding.page ? ` — page ${finding.page}` : ''}` }),
      el('div', { class: 'quote-block', text: finding.quote }),
      el('button', {
        class: 'btn btn-sm', style: 'margin-top:8px', text: 'Show in document',
        onclick: () => openDocument(current.document_id, finding.quote),
      }),
    );
  }
  if (finding.analysis) body.append(el('h4', { text: 'Analysis' }), el('p', { text: finding.analysis }));
  if (finding.redline) {
    body.append(
      el('h4', { text: 'Proposed language' }),
      el('div', { class: 'redline', text: finding.redline }),
      el('button', {
        class: 'btn btn-sm', style: 'margin-top:8px', text: 'Copy',
        onclick: () => { navigator.clipboard.writeText(finding.redline); toast('Redline copied.'); },
      }),
    );
  }
  if (!body.childNodes.length) {
    body.append(el('p', { class: 'small muted', text: 'No further detail was recorded for this rule.' }));
  }

  const head = el('div', {
    class: 'finding-head',
    onclick: () => { body.hidden = !body.hidden; },
  }, [
    el('span', { class: `chip ${status.cls}`, text: status.label }),
    el('h3', { text: finding.rule }),
    finding.clause ? el('span', { class: 'small muted', text: finding.clause }) : null,
    severity !== 'none'
      ? el('span', { class: `chip chip-${severity}`, text: severity })
      : null,
  ]);

  return el('div', { class: `finding finding-${severity}` }, [head, body]);
}

// ---------------------------------------------------------------- start

async function startReview() {
  const documents = readyDocuments();
  if (!documents.length) return toast('Upload a document first.', 'error');
  if (!state.llmReady) return toast('Set ANTHROPIC_API_KEY to run reviews.', 'error');

  const customRules = el('textarea', {
    rows: 5,
    placeholder: 'One rule per line:\nLiability cap — at least 12 months of fees\nTermination for convenience — 30 days’ notice',
  });
  const customBlock = el('div', { hidden: true }, [
    el('label', { class: 'field' }, [
      el('span', { text: 'Your rules' }),
      customRules,
      el('small', { text: 'Use “Title — standard” on each line. The part before the dash becomes the rule name.' }),
    ]),
  ]);

  const playbookSelect = el('select', {}, [
    ...playbooks.map((p) => el('option', { value: p.key, text: `${p.name} (${p.rule_count} rules)` })),
    el('option', { value: '__custom__', text: 'Custom playbook…' }),
  ]);
  playbookSelect.onchange = () => { customBlock.hidden = playbookSelect.value !== '__custom__'; };

  const documentSelect = el('select', {}, documents.map((d) =>
    el('option', { value: d.id, text: d.title })));

  const ok = await modal({
    title: 'New playbook review',
    body: el('div', {}, [
      el('label', { class: 'field' }, [el('span', { text: 'Document' }), documentSelect]),
      el('label', { class: 'field' }, [el('span', { text: 'Playbook' }), playbookSelect]),
      customBlock,
    ]),
    confirmLabel: 'Run review',
  });
  if (!ok) return;

  const payload = playbookSelect.value === '__custom__'
    ? { playbook: { name: 'Custom playbook', perspective: 'client', rules: parseRules(customRules.value) } }
    : { playbook_key: playbookSelect.value };

  if (payload.playbook && !payload.playbook.rules.length) {
    return toast('Add at least one rule.', 'error');
  }

  try {
    const run = await api.startReview(documentSelect.value, payload);
    state.reviewId = run.id;
    toast('Review started.');
    await render($('#view'));
  } catch (error) {
    toast(error.message, 'error');
  }
}

function parseRules(text) {
  return text.split('\n').map((line) => line.trim()).filter(Boolean).map((line) => {
    const [title, ...rest] = line.split(/\s+[—–-]\s+/);
    return { title: title.trim(), standard: rest.join(' - ').trim() || title.trim() };
  });
}

async function previewPlaybook(key) {
  const playbook = await api.getPlaybook(key);
  modal({
    title: playbook.name,
    body: el('div', {}, [
      el('p', { class: 'small muted', style: 'margin-bottom:12px', text: `We act for the ${playbook.perspective}.` }),
      el('div', { style: 'max-height:52vh;overflow-y:auto' }, playbook.rules.map((rule, index) =>
        el('div', { style: 'padding:8px 0;border-bottom:1px solid var(--line)' }, [
          el('strong', { class: 'small', text: `${index + 1}. ${rule.title}` }),
          el('p', { class: 'small muted', style: 'margin-top:2px', text: rule.standard }),
        ]))),
    ]),
    confirmLabel: 'Close',
  });
}

// ---------------------------------------------------------------- polling

function schedulePoll() {
  clearTimeout(pollTimer);
  const running = current?.status === 'running' || runs.some((r) => r.status === 'running');
  if (!running) return;
  pollTimer = setTimeout(() => render($('#view')).catch(() => schedulePoll()), 2500);
}
