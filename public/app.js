// ─── State ───────────────────────────────────────────────────────────────────
const state = {
  messages: [],       // { role: 'user'|'assistant', content: string }
  exchangeCount: 0,   // number of completed back-and-forth turns
  isStreaming: false,
  ttsEnabled: false,
  isListening: false,
};

// ─── DOM refs ─────────────────────────────────────────────────────────────────
const messagesEl    = document.getElementById('messages');
const userInput     = document.getElementById('user-input');
const sendBtn       = document.getElementById('send-btn');
const micBtn        = document.getElementById('mic-btn');
const ttsToggle     = document.getElementById('tts-toggle');
const ttsLabel      = document.getElementById('tts-label');
const synthesizeBtn = document.getElementById('synthesize-btn');
const resultsOverlay= document.getElementById('results-overlay');
const loadingOverlay= document.getElementById('loading-overlay');
const closeResults  = document.getElementById('close-results');

// ─── Helpers ──────────────────────────────────────────────────────────────────
function scrollToBottom() {
  messagesEl.scrollTo({ top: messagesEl.scrollHeight, behavior: 'smooth' });
}

function createMessageEl(role) {
  const wrap = document.createElement('div');
  wrap.className = `message ${role}`;

  const avatar = document.createElement('div');
  avatar.className = 'message-avatar';
  avatar.textContent = role === 'ai' ? '✦' : 'You';

  const body = document.createElement('div');
  body.className = 'message-body';

  const name = document.createElement('div');
  name.className = 'message-name';
  name.textContent = role === 'ai' ? 'Ikigai Coach' : 'You';

  const text = document.createElement('div');
  text.className = 'message-text';

  body.appendChild(name);
  body.appendChild(text);
  wrap.appendChild(avatar);
  wrap.appendChild(body);
  messagesEl.appendChild(wrap);
  return text;
}

function setInputEnabled(enabled) {
  userInput.disabled = !enabled;
  sendBtn.disabled   = !enabled;
  if (enabled) {
    userInput.value = '';
    autoResize();
    sendBtn.disabled = true;
    userInput.focus();
  }
}

function updateSynthesizeBtn() {
  const ready = state.exchangeCount >= 4;
  synthesizeBtn.disabled = !ready;
  synthesizeBtn.title = ready
    ? 'Generate your Ikigai map and report'
    : `Have a few more exchanges first (${state.exchangeCount}/4)`;
}

// ─── Stream SSE ───────────────────────────────────────────────────────────────
async function streamSSE(url, body, onChunk) {
  const resp = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });

  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    const lines = buffer.split('\n');
    buffer = lines.pop(); // keep incomplete line

    for (const line of lines) {
      if (!line.startsWith('data: ')) continue;
      const payload = line.slice(6);
      if (payload === '[DONE]') return;
      try {
        const obj = JSON.parse(payload);
        if (obj.text) onChunk(obj.text);
        if (obj.error) throw new Error(obj.error);
      } catch (e) {
        if (e.message && !e.message.includes('JSON')) throw e;
      }
    }
  }
}

// ─── Welcome ──────────────────────────────────────────────────────────────────
async function loadWelcome() {
  setInputEnabled(false);
  const textEl = createMessageEl('ai');
  textEl.classList.add('typing-cursor');
  let full = '';

  await streamSSE('/api/welcome', {}, (chunk) => {
    full += chunk;
    textEl.textContent = full;
    scrollToBottom();
  });

  textEl.classList.remove('typing-cursor');
  state.messages.push({ role: 'assistant', content: full });
  speak(full);
  setInputEnabled(true);
}

// ─── Send message ─────────────────────────────────────────────────────────────
async function sendMessage() {
  const text = userInput.value.trim();
  if (!text || state.isStreaming) return;

  // Add user message
  const userEl = createMessageEl('user');
  userEl.textContent = text;
  state.messages.push({ role: 'user', content: text });
  userInput.value = '';
  autoResize();
  scrollToBottom();

  state.isStreaming = true;
  setInputEnabled(false);

  // AI response
  const aiEl = createMessageEl('ai');
  aiEl.classList.add('typing-cursor');
  let full = '';

  try {
    await streamSSE('/api/chat', { messages: state.messages }, (chunk) => {
      full += chunk;
      aiEl.textContent = full;
      scrollToBottom();
    });
  } catch (err) {
    aiEl.textContent = 'Something went wrong. Please try again.';
    console.error(err);
  }

  aiEl.classList.remove('typing-cursor');
  state.messages.push({ role: 'assistant', content: full });
  state.exchangeCount++;
  updateSynthesizeBtn();
  speak(full);

  state.isStreaming = false;
  setInputEnabled(true);
}

// ─── Auto-resize textarea ─────────────────────────────────────────────────────
function autoResize() {
  userInput.style.height = 'auto';
  userInput.style.height = Math.min(userInput.scrollHeight, 160) + 'px';
}

// ─── Build SVG Ikigai Diagram ─────────────────────────────────────────────────
function buildDiagram(data) {
  const W = 520, H = 520, cx = 260, cy = 260, r = 148;
  const colors = {
    love:  { fill: '#FDECEA', stroke: '#E8524A' },
    good:  { fill: '#FEF6E4', stroke: '#F5A623' },
    needs: { fill: '#E8F4FD', stroke: '#4A90D9' },
    paid:  { fill: '#EAF6F0', stroke: '#5BAD8A' },
  };

  // Circle centers: top, right, bottom, left
  const circles = {
    love:  { x: cx,       y: cy - 92 },
    good:  { x: cx + 92,  y: cy      },
    needs: { x: cx,       y: cy + 92 },
    paid:  { x: cx - 92,  y: cy      },
  };

  const ns = 'http://www.w3.org/2000/svg';

  const svg = document.createElementNS(ns, 'svg');
  svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
  svg.setAttribute('xmlns', ns);

  const defs = document.createElementNS(ns, 'defs');
  // Clip paths for each circle (to contain text)
  Object.entries(circles).forEach(([key, c]) => {
    const cp = document.createElementNS(ns, 'clipPath');
    cp.setAttribute('id', `clip-${key}`);
    const circle = document.createElementNS(ns, 'circle');
    circle.setAttribute('cx', c.x);
    circle.setAttribute('cy', c.y);
    circle.setAttribute('r', r);
    cp.appendChild(circle);
    defs.appendChild(cp);
  });
  svg.appendChild(defs);

  // Draw circles
  Object.entries(circles).forEach(([key, c]) => {
    const col = colors[key];
    const circle = document.createElementNS(ns, 'circle');
    circle.setAttribute('cx', c.x);
    circle.setAttribute('cy', c.y);
    circle.setAttribute('r', r);
    circle.setAttribute('fill', col.fill);
    circle.setAttribute('stroke', col.stroke);
    circle.setAttribute('stroke-width', '1.5');
    circle.setAttribute('fill-opacity', '0.75');
    svg.appendChild(circle);
  });

  // Center highlight
  const centerCircle = document.createElementNS(ns, 'circle');
  centerCircle.setAttribute('cx', cx);
  centerCircle.setAttribute('cy', cy);
  centerCircle.setAttribute('r', 46);
  centerCircle.setAttribute('fill', 'rgba(123,94,167,0.15)');
  centerCircle.setAttribute('stroke', '#7B5EA7');
  centerCircle.setAttribute('stroke-width', '1.5');
  svg.appendChild(centerCircle);

  // Helper: add text label
  function addText(x, y, lines, { size = 11, color = '#1A1714', bold = false, italic = false } = {}) {
    const g = document.createElementNS(ns, 'g');
    const lineH = size * 1.4;
    const startY = y - ((lines.length - 1) * lineH) / 2;
    lines.forEach((line, i) => {
      const t = document.createElementNS(ns, 'text');
      t.setAttribute('x', x);
      t.setAttribute('y', startY + i * lineH);
      t.setAttribute('text-anchor', 'middle');
      t.setAttribute('dominant-baseline', 'middle');
      t.setAttribute('font-size', size);
      t.setAttribute('font-family', italic ? 'Lora, serif' : 'Inter, sans-serif');
      t.setAttribute('font-weight', bold ? '600' : '400');
      t.setAttribute('font-style', italic ? 'italic' : 'normal');
      t.setAttribute('fill', color);
      t.textContent = line;
      g.appendChild(t);
    });
    return g;
  }

  // Circle title labels (outer areas)
  const labelOffset = 62;
  svg.appendChild(addText(cx, circles.love.y - labelOffset, ['WHAT YOU', 'LOVE'], { size: 10.5, color: '#E8524A', bold: true }));
  svg.appendChild(addText(circles.good.x + labelOffset, cy, ['WHAT YOU\'RE', 'GOOD AT'], { size: 10.5, color: '#D48B1A', bold: true }));
  svg.appendChild(addText(cx, circles.needs.y + labelOffset, ['WHAT THE', 'WORLD NEEDS'], { size: 10.5, color: '#2E7CC4', bold: true }));
  svg.appendChild(addText(circles.paid.x - labelOffset, cy, ['WHAT YOU CAN', 'BE PAID FOR'], { size: 10.5, color: '#3A8A64', bold: true }));

  // Intersection labels
  svg.appendChild(addText(cx + 68, cy - 68, ['PASSION'], { size: 9.5, color: '#C0607B', bold: true }));
  svg.appendChild(addText(cx + 68, cy + 68, ['PROFESSION'], { size: 9.5, color: '#D4832A', bold: true }));
  svg.appendChild(addText(cx - 68, cy + 68, ['VOCATION'], { size: 9.5, color: '#4AA88A', bold: true }));
  svg.appendChild(addText(cx - 68, cy - 68, ['MISSION'], { size: 9.5, color: '#6B7FD7', bold: true }));

  // Center label
  svg.appendChild(addText(cx, cy, ['IKIGAI'], { size: 12, color: '#7B5EA7', bold: true }));

  document.getElementById('ikigai-diagram').appendChild(svg);
}

// ─── Populate results ──────────────────────────────────────────────────────────
function populateResults(data) {
  // Diagram
  buildDiagram(data);

  // Dimension lists
  const lists = {
    love:  document.getElementById('list-love'),
    good_at: document.getElementById('list-good'),
    world_needs: document.getElementById('list-needs'),
    paid_for: document.getElementById('list-paid'),
  };

  Object.entries(lists).forEach(([key, el]) => {
    (data.ikigai_map[key] || []).forEach(item => {
      const li = document.createElement('li');
      li.textContent = item;
      el.appendChild(li);
    });
  });

  // Intersections
  document.getElementById('int-passion').textContent    = data.intersections.passion    || '';
  document.getElementById('int-profession').textContent = data.intersections.profession || '';
  document.getElementById('int-mission').textContent    = data.intersections.mission    || '';
  document.getElementById('int-vocation').textContent   = data.intersections.vocation   || '';
  document.getElementById('int-ikigai').textContent     = data.intersections.ikigai     || '';

  // Report
  document.getElementById('report-text').textContent = data.report || '';

  // Opportunities
  const oppList = document.getElementById('opportunities-list');
  (data.opportunities || []).forEach(opp => {
    const card = document.createElement('div');
    card.className = 'opportunity-card';
    card.innerHTML = `
      <div class="opp-title">${opp.title}</div>
      <div class="opp-type">${opp.type}</div>
      <div class="opp-description">${opp.description}</div>
      <div class="opp-why">${opp.why}</div>
    `;
    oppList.appendChild(card);
  });
}

// ─── Synthesize ───────────────────────────────────────────────────────────────
async function synthesize() {
  loadingOverlay.classList.remove('hidden');

  try {
    const resp = await fetch('/api/synthesize', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ messages: state.messages }),
    });

    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    if (data.error) throw new Error(data.error);

    populateResults(data);
    loadingOverlay.classList.add('hidden');
    resultsOverlay.classList.remove('hidden');
    resultsOverlay.scrollTop = 0;
  } catch (err) {
    loadingOverlay.classList.add('hidden');
    alert('Failed to generate your Ikigai: ' + err.message);
    console.error(err);
  }
}

// ─── Text-to-Speech (OpenAI) ─────────────────────────────────────────────────
let currentAudio = null;

async function speak(text) {
  if (!state.ttsEnabled) return;
  stopSpeaking();

  try {
    const resp = await fetch('/api/tts', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text }),
    });
    if (!resp.ok) return;

    const blob = await resp.blob();
    const url  = URL.createObjectURL(blob);
    currentAudio = new Audio(url);
    currentAudio.play();
    currentAudio.onended = () => URL.revokeObjectURL(url);
  } catch (err) {
    console.warn('TTS error:', err);
  }
}

function stopSpeaking() {
  if (currentAudio) {
    currentAudio.pause();
    currentAudio = null;
  }
}

ttsToggle.addEventListener('click', () => {
  state.ttsEnabled = !state.ttsEnabled;
  ttsToggle.classList.toggle('active', state.ttsEnabled);
  ttsLabel.textContent = state.ttsEnabled ? 'Reading aloud' : 'Read aloud';
  if (state.ttsEnabled) {
    speak('Read aloud is now on.');
  } else {
    stopSpeaking();
  }
});

// ─── Speech-to-Text ───────────────────────────────────────────────────────────
const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
let recognition = null;

if (SpeechRecognition) {
  recognition = new SpeechRecognition();
  recognition.continuous      = false;
  recognition.interimResults  = true;
  recognition.lang            = 'en-US';

  let savedText = '';

  recognition.onstart = () => {
    state.isListening = true;
    micBtn.classList.add('listening');
    micBtn.title = 'Listening… click to stop';
    savedText = userInput.value;
  };

  recognition.onresult = (e) => {
    const transcript = Array.from(e.results)
      .map(r => r[0].transcript)
      .join('');
    userInput.value = savedText + (savedText && !savedText.endsWith(' ') ? ' ' : '') + transcript;
    autoResize();
    sendBtn.disabled = !userInput.value.trim();
  };

  recognition.onerror = (e) => {
    console.warn('Speech recognition error:', e.error);
    stopListening();
  };

  recognition.onend = () => stopListening();

  function stopListening() {
    state.isListening = false;
    micBtn.classList.remove('listening');
    micBtn.title = 'Click to speak';
    sendBtn.disabled = !userInput.value.trim() || state.isStreaming;
  }

  micBtn.addEventListener('click', () => {
    if (state.isListening) {
      recognition.stop();
    } else {
      try { recognition.start(); } catch (e) { console.warn(e); }
    }
  });
} else {
  micBtn.style.display = 'none';
  console.info('SpeechRecognition not supported in this browser.');
}

// ─── Event listeners ──────────────────────────────────────────────────────────
sendBtn.addEventListener('click', sendMessage);

userInput.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
});

userInput.addEventListener('input', () => {
  autoResize();
  sendBtn.disabled = !userInput.value.trim() || state.isStreaming;
});

synthesizeBtn.addEventListener('click', synthesize);

closeResults.addEventListener('click', () => {
  resultsOverlay.classList.add('hidden');
});

document.getElementById('print-btn').addEventListener('click', () => {
  window.print();
});

// ─── Init ─────────────────────────────────────────────────────────────────────
loadWelcome();
