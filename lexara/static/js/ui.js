// DOM helpers plus the three shared overlays: toast, modal, drawer.

export const $ = (selector, root = document) => root.querySelector(selector);
export const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

/** Create an element. `props` sets properties; `html`/`text` set content. */
export function el(tag, props = {}, children = []) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props)) {
    if (value === undefined || value === null || value === false) continue;
    if (key === 'class') node.className = value;
    else if (key === 'text') node.textContent = value;
    else if (key === 'html') node.innerHTML = value;
    else if (key === 'dataset') Object.assign(node.dataset, value);
    else if (key.startsWith('on') && typeof value === 'function') {
      node.addEventListener(key.slice(2).toLowerCase(), value);
    } else if (key in node && key !== 'style') node[key] = value;
    else node.setAttribute(key, value);
  }
  for (const child of [children].flat()) {
    if (child === null || child === undefined || child === false) continue;
    node.append(child.nodeType ? child : document.createTextNode(String(child)));
  }
  return node;
}

export const clear = (node) => { while (node.firstChild) node.firstChild.remove(); };

export function escapeHtml(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

// ---------------------------------------------------------------- toasts

export function toast(message, kind = 'info') {
  const node = el('div', { class: `toast ${kind === 'error' ? 'toast-error' : ''}`, text: message });
  $('#toasts').append(node);
  setTimeout(() => {
    node.style.opacity = '0';
    node.style.transition = 'opacity .25s';
    setTimeout(() => node.remove(), 260);
  }, kind === 'error' ? 5200 : 3200);
}

// ---------------------------------------------------------------- modal

let modalResolve = null;

/**
 * Show a modal. `fields` renders labelled inputs and resolves to their values;
 * resolves to null when cancelled.
 */
export function modal({ title, fields = [], body = null, confirmLabel = 'Save', danger = false }) {
  const scrim = $('#modal-scrim');
  const bodyNode = $('#modal-body');
  const actions = $('#modal-actions');

  $('#modal-title').textContent = title;
  clear(bodyNode);
  clear(actions);

  const inputs = new Map();
  for (const field of fields) {
    const control = field.type === 'textarea'
      ? el('textarea', { rows: field.rows || 3, value: field.value || '', placeholder: field.placeholder || '' })
      : field.type === 'select'
        ? el('select', {}, (field.options || []).map((option) =>
            el('option', { value: option.value, text: option.label, selected: option.value === field.value })))
        : el('input', { type: 'text', value: field.value || '', placeholder: field.placeholder || '' });

    inputs.set(field.name, control);
    bodyNode.append(el('label', { class: 'field' }, [
      el('span', { text: field.label }),
      control,
      field.hint ? el('small', { text: field.hint }) : null,
    ]));
  }
  if (body) bodyNode.append(body);

  const close = (result) => {
    scrim.hidden = true;
    document.removeEventListener('keydown', onKey);
    modalResolve?.(result);
    modalResolve = null;
  };
  const submit = () => {
    const values = {};
    for (const [name, control] of inputs) values[name] = control.value.trim();
    close(fields.length ? values : true);
  };
  const onKey = (event) => {
    if (event.key === 'Escape') close(null);
    if (event.key === 'Enter' && (event.metaKey || event.ctrlKey)) submit();
  };

  actions.append(
    el('button', { class: 'btn', text: 'Cancel', onclick: () => close(null) }),
    el('button', {
      class: `btn ${danger ? 'btn-danger' : 'btn-primary'}`,
      text: confirmLabel,
      onclick: submit,
    }),
  );

  scrim.hidden = false;
  scrim.onclick = (event) => { if (event.target === scrim) close(null); };
  document.addEventListener('keydown', onKey);
  setTimeout(() => (inputs.values().next().value || $('#modal-actions .btn-primary'))?.focus(), 40);

  return new Promise((resolve) => { modalResolve = resolve; });
}

export function confirmDialog(title, message, confirmLabel = 'Delete') {
  return modal({
    title,
    body: el('p', { class: 'small muted', text: message }),
    confirmLabel,
    danger: true,
  });
}

// ---------------------------------------------------------------- drawer

export function drawer(title, ...nodes) {
  $('#drawer-title').textContent = title;
  const body = $('#drawer-body');
  clear(body);
  body.append(...nodes.filter(Boolean));
  $('#drawer').hidden = false;
  $('#drawer-scrim').hidden = false;
}

export function closeDrawer() {
  $('#drawer').hidden = true;
  $('#drawer-scrim').hidden = true;
}

// ---------------------------------------------------------------- format

export function formatBytes(bytes) {
  if (!bytes) return '—';
  const units = ['B', 'KB', 'MB', 'GB'];
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) { value /= 1024; unit += 1; }
  return `${value < 10 && unit > 0 ? value.toFixed(1) : Math.round(value)} ${units[unit]}`;
}

export function formatDate(iso) {
  if (!iso) return '';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' });
}

export function plural(count, singular, pluralForm = `${singular}s`) {
  return `${count} ${count === 1 ? singular : pluralForm}`;
}

/** Minimal markdown → HTML for assistant replies and memos. Input is escaped first. */
export function markdown(source) {
  const lines = escapeHtml(source).split('\n');
  const out = [];
  let inCode = false;
  let listType = null;

  const closeList = () => { if (listType) { out.push(`</${listType}>`); listType = null; } };

  for (let raw of lines) {
    if (raw.trim().startsWith('```')) {
      closeList();
      out.push(inCode ? '</code></pre>' : '<pre><code>');
      inCode = !inCode;
      continue;
    }
    if (inCode) { out.push(raw + '\n'); continue; }

    const line = raw.trim();
    if (!line) { closeList(); continue; }

    const heading = line.match(/^(#{1,4})\s+(.*)$/);
    if (heading) {
      closeList();
      const level = Math.min(heading[1].length + 1, 4);
      out.push(`<h${level}>${inline(heading[2])}</h${level}>`);
      continue;
    }
    if (/^([-*_])\1{2,}$/.test(line)) { closeList(); out.push('<hr>'); continue; }
    if (line.startsWith('&gt;')) {
      closeList();
      out.push(`<blockquote>${inline(line.replace(/^&gt;\s?/, ''))}</blockquote>`);
      continue;
    }

    const bullet = line.match(/^[-*•]\s+(.*)$/);
    const numbered = line.match(/^\d+[.)]\s+(.*)$/);
    if (bullet || numbered) {
      const wanted = bullet ? 'ul' : 'ol';
      if (listType !== wanted) { closeList(); out.push(`<${wanted}>`); listType = wanted; }
      out.push(`<li>${inline((bullet || numbered)[1])}</li>`);
      continue;
    }

    closeList();
    out.push(`<p>${inline(line)}</p>`);
  }
  closeList();
  if (inCode) out.push('</code></pre>');
  return out.join('');
}

function inline(text) {
  return text
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/(^|[\s(])\*([^*\n]+)\*/g, '$1<em>$2</em>')
    .replace(/(^|[\s(])_([^_\n]+)_/g, '$1<em>$2</em>')
    .replace(/\[(\d{1,2})\]/g, '<button class="cite" data-cite="$1">$1</button>');
}
