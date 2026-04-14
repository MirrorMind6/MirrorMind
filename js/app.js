// app.js — Router + all views.
// Hash-based routing: #/, #/paste, #/version/:id, #/diff/:id

// ─── Bootstrap ───────────────────────────────────────────────────────────────

window.addEventListener('load',       route);
window.addEventListener('hashchange', route);

function route() {
  const hash = window.location.hash || '#/';
  const app  = document.getElementById('app');

  if (hash === '#/' || hash === '#') {
    renderTimeline(app);
  } else if (hash === '#/paste') {
    renderPaste(app);
  } else if (hash.startsWith('#/version/')) {
    renderVersion(app, hash.split('/')[2]);
  } else if (hash.startsWith('#/diff/')) {
    renderDiff(app, hash.split('/')[2]);
  } else {
    renderTimeline(app);
  }
}

// ─── Timeline ────────────────────────────────────────────────────────────────

function renderTimeline(app) {
  const versions = Storage.getAll();

  app.innerHTML = `
    <header class="nav">
      <span class="nav-title">MirrorMind</span>
      <a href="#/paste" class="btn-icon" aria-label="New version">
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round">
          <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="16"/><line x1="8" y1="12" x2="16" y2="12"/>
        </svg>
      </a>
    </header>

    <main class="scroll-area">
      ${versions.length === 0 ? emptyState() : `
        <ul class="card-list">
          ${versions.map(v => versionRow(v)).join('')}
        </ul>
      `}
    </main>
  `;
}

function emptyState() {
  return `
    <div class="empty">
      <div class="empty-icon">📋</div>
      <h2>No versions yet</h2>
      <p>Paste a summary from your Claude conversation to start tracking your framework.</p>
      <a href="#/paste" class="btn-primary">Paste first version</a>
    </div>
  `;
}

function versionRow(v) {
  const prev  = Storage.getPrevious(v.versionNumber);
  const stats = prev ? Diff.stats(prev.content, v.content) : 'Initial version';
  return `
    <li>
      <a href="#/version/${v.id}" class="card row">
        <div class="row-main">
          <div class="row-top">
            <span class="badge">v${v.versionNumber}</span>
            <span class="row-title">${esc(v.autoTitle)}</span>
          </div>
          <div class="row-meta">${formatDate(v.timestamp)} · ${esc(stats)}</div>
        </div>
        <span class="chevron">›</span>
      </a>
    </li>
  `;
}

// ─── Paste ───────────────────────────────────────────────────────────────────

function renderPaste(app) {
  const versions   = Storage.getAll();
  const nextNumber = versions.length > 0 ? Math.max(...versions.map(v => v.versionNumber)) + 1 : 1;

  app.innerHTML = `
    <header class="nav">
      <a href="#/" class="btn-back">‹ Back</a>
      <span class="nav-title">New Version</span>
      <span class="badge">v${nextNumber}</span>
    </header>

    <main class="paste-area">
      <p class="paste-hint">Paste your Claude summary below</p>
      <textarea id="paste-input" class="paste-editor" placeholder="Paste here…" autofocus spellcheck="false"></textarea>
    </main>

    <footer class="bottom-bar">
      <button id="save-btn" class="btn-primary" disabled>Save version</button>
    </footer>
  `;

  const input   = document.getElementById('paste-input');
  const saveBtn = document.getElementById('save-btn');

  input.addEventListener('input', () => {
    saveBtn.disabled = input.value.trim().length === 0;
  });

  saveBtn.addEventListener('click', () => {
    const content = input.value.trim();
    if (!content) return;
    Storage.add(content);
    window.location.hash = '#/';
  });

  // Focus the textarea after a short delay (iOS needs this)
  setTimeout(() => input.focus(), 100);
}

// ─── Version Detail ───────────────────────────────────────────────────────────

function renderVersion(app, id) {
  const version = Storage.getById(id);
  if (!version) { window.location.hash = '#/'; return; }

  const prev = Storage.getPrevious(version.versionNumber);

  app.innerHTML = `
    <header class="nav">
      <a href="#/" class="btn-back">‹ Back</a>
      <span class="nav-title">${version.label || 'v' + version.versionNumber}</span>
    </header>

    <main class="scroll-area">
      <div class="detail-header card">
        <div class="detail-meta">
          <span class="badge">v${version.versionNumber}</span>
          <span class="detail-date">${formatDate(version.timestamp)}</span>
        </div>
        <h2 class="detail-title">${esc(version.autoTitle)}</h2>
      </div>

      <div class="action-row">
        <button id="copy-btn" class="action-card">
          <span class="action-icon">📋</span>
          <span id="copy-label">Copy output</span>
        </button>
        ${prev ? `
        <a href="#/diff/${version.id}" class="action-card">
          <span class="action-icon">↔️</span>
          <span>What changed</span>
        </a>` : ''}
      </div>

      <div class="card content-card">
        <pre class="content-text">${esc(version.content)}</pre>
      </div>
    </main>
  `;

  document.getElementById('copy-btn').addEventListener('click', async () => {
    const ok = await copyToClipboard(version.content);
    if (ok) {
      const label = document.getElementById('copy-label');
      label.textContent = 'Copied!';
      setTimeout(() => { label.textContent = 'Copy output'; }, 2000);
    }
  });
}

// ─── Diff ─────────────────────────────────────────────────────────────────────

function renderDiff(app, id) {
  const version = Storage.getById(id);
  if (!version) { window.location.hash = '#/'; return; }

  const prev = Storage.getPrevious(version.versionNumber);
  if (!prev)  { window.location.hash = `#/version/${id}`; return; }

  const lines = Diff.compute(prev.content, version.content);
  const stats = Diff.stats(prev.content, version.content);

  app.innerHTML = `
    <header class="nav">
      <a href="#/version/${id}" class="btn-back">‹ Back</a>
      <span class="nav-title">What changed</span>
    </header>

    <main class="scroll-area">
      <div class="diff-header card">
        <span>v${prev.versionNumber} → v${version.versionNumber}</span>
        <span class="diff-stats">${esc(stats)}</span>
      </div>

      <div class="diff-body card">
        ${lines.map(l => `
          <div class="diff-line diff-${l.type}">
            <span class="diff-prefix">${l.type === 'added' ? '+' : l.type === 'removed' ? '−' : ' '}</span>
            <span class="diff-text">${esc(l.text) || '&nbsp;'}</span>
          </div>
        `).join('')}
      </div>
    </main>
  `;
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

async function copyToClipboard(text) {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    // Fallback for older iOS
    const el = Object.assign(document.createElement('textarea'), {
      value: text,
      style: 'position:fixed;opacity:0',
    });
    document.body.appendChild(el);
    el.focus(); el.select();
    const ok = document.execCommand('copy');
    document.body.removeChild(el);
    return ok;
  }
}

function formatDate(iso) {
  return new Date(iso).toLocaleDateString('en-US', {
    month: 'short', day: 'numeric', year: 'numeric',
    hour: 'numeric', minute: '2-digit',
  });
}

function esc(str) {
  return String(str ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}
