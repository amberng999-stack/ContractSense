let API_BASE = 'https://nexhack-2026.onrender.com';
const HOSTED_API = 'https://nexhack-2026.onrender.com';

// ═══════════════════════════════════════════
// BACKEND STATUS CHECKER
// ═══════════════════════════════════════════
async function checkBackend() {
  const dot   = document.getElementById('status-dot');
  const label = document.getElementById('status-label');

  dot.className   = 'status-dot checking';
  label.textContent = 'Checking...';

  const targets = [];
  if (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1' || !window.location.hostname) {
    targets.push('http://127.0.0.1:8000');
  }
  targets.push(HOSTED_API);

  for (const url of targets) {
    try {
      const res = await fetch(`${url}/health`, { signal: AbortSignal.timeout(2000) });
      if (res.ok) {
        API_BASE = url;
        dot.className     = 'status-dot online';
        label.textContent = `Backend online (${url.includes('127.0.0.1') || url.includes('localhost') ? 'Local' : 'Cloud'})`;
        return;
      }
    } catch (err) {
      // Continue to check other targets
    }
  }

  API_BASE = targets[0];
  dot.className     = 'status-dot offline';
  label.textContent = 'Backend offline';
}

// Check on load, then every 15 seconds
window.addEventListener('DOMContentLoaded', () => {
  checkBackend();
  setInterval(checkBackend, 15000);
});

function goPage(name) {
  closeHistoryDetail();
  if (name === 'scanner') {
    resetScanner();
  }
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
  document.getElementById('page-' + name).classList.add('active');
  
  const pages = ['home', 'scanner', 'autoscan', 'history', 'settings'];
  const idx = pages.indexOf(name);
  if (idx !== -1) {
    document.querySelectorAll('.nav-btn')[idx].classList.add('active');
  }
}

// ═══════════════════════════════════════════
// CONTRACT RENDERER — builds PDF-style page
// Maps backend "findings" → visual clauses
// ═══════════════════════════════════════════
function renderContractPage(contract, containerEl, issueListEl, chipOk, chipWarn, chipBad, suggestionTextEl, copyBtn) {
  let ok=0, warn=0, bad=0;
  const issues = [];

  contract.sections.forEach(sec => sec.clauses.forEach(c => {
    if (c.status === 'ok') ok++;
    else if (c.status === 'warn') { warn++; issues.push(c); }
    else if (c.status === 'bad')  { bad++;  issues.push(c); }
  }));

  chipOk.textContent  = `✓ ${ok} safe`;
  chipWarn.textContent = `⚠ ${warn} warn`;
  chipBad.textContent  = `✕ ${bad} critical`;

  // Build contract page HTML — only show header rows that have real content,
  // so when the document has no extractable title/meta, nothing fake or
  // empty is displayed. This keeps the view to just the real document text.
  let html = '';
  if (contract.title) html += `<div class="doc-title">${contract.title}</div>`;
  if (contract.subtitle) html += `<div class="doc-subtitle">${contract.subtitle}</div>`;
  if (contract.title || contract.subtitle) html += `<hr>`;
  if (contract.meta && contract.meta.length) {
    html += `<div class="doc-meta">
      ${contract.meta.map(m => `<strong>${m.split(':')[0]}:</strong>${m.substring(m.indexOf(':')+1)}<br>`).join('')}
    </div><hr>`;
  }

  contract.sections.forEach(sec => {
    if (sec.title) html += `<div class="sec-title">${sec.title}</div>`;
    sec.clauses.forEach(c => {
      const hlClass = c.status === 'bad' ? 'hl-red' : c.status === 'warn' ? 'hl-amber' : '';
      const safeId  = c.id.replace(/\./g, '_');
      const inner   = hlClass
        ? `<span class="${hlClass}"
             onclick="pickIssue('${c.id}','${containerEl.id}','${issueListEl.id}','${suggestionTextEl.id}','${copyBtn.id}')"
             title="${(c.issue||'').replace(/'/g,"&#39;")}">
             ${c.text}
           </span>`
        : `<span>${c.text}</span>`;
      html += `<div class="clause-line" id="${containerEl.id}-clause-${safeId}">${inner}</div>`;
    });
  });

  // Signature block
  html += `
    <div class="sig-block">
      <div class="sig-col">
        <div class="sig-line"></div>
        <strong>${contract.sig[0]}</strong><br>Authorised Signatory<br>Date: ___________
      </div>
      <div class="sig-col">
        <div class="sig-line"></div>
        <strong>${contract.sig[1]}</strong><br>Authorised Signatory<br>Date: ___________
      </div>
    </div>
    <div class="doc-footer">This document is for compliance screening only. Not legal advice.</div>
  `;

  containerEl.innerHTML = html;

  // Build issues list
  issueListEl.innerHTML = issues.map(c => {
    const safeId = c.id.replace(/\./g, '_');
    const lawText = c.law ? `${c.law} — ` : '';
    const descSnippet = (c.desc || '').substring(0, 90);
    return `
      <div class="issue-item" id="${issueListEl.id}-issue-${safeId}"
        data-status="${c.status}"
        onclick="pickIssue('${c.id}','${containerEl.id}','${issueListEl.id}','${suggestionTextEl.id}','${copyBtn.id}')">
        <div class="issue-top">
          <div class="issue-badge ${c.status}">${c.id}</div>
          <div class="issue-name">${c.issue || c.title || ''}</div>
        </div>
        <div class="issue-desc">${lawText}${descSnippet}${descSnippet.length >= 90 ? '…' : ''}</div>
      </div>
    `;
  }).join('');
}

// Renders only the issues sidebar (no text document body) for PDF-native mode.
// `pdfHandle` is the handle returned by renderPdfNative — passed down so
// clicking an issue scrolls and highlights the matching box on the real PDF.
function renderIssuesList(contract, issueListEl, chipOk, chipWarn, chipBad, suggestionTextEl, copyBtn, pdfHandle) {
  const issues = [];
  let ok = 0, warn = 0, bad = 0;
  contract.sections.forEach(sec => sec.clauses.forEach(c => {
    if (c.status === 'ok') ok++;
    else if (c.status === 'warn') { warn++; issues.push(c); }
    else if (c.status === 'bad')  { bad++;  issues.push(c); }
  }));
  chipOk.textContent   = `✓ ${ok} safe`;
  chipWarn.textContent = `⚠ ${warn} warn`;
  chipBad.textContent  = `✕ ${bad} critical`;

  issueListEl.innerHTML = issues.map(c => {
    const safeId = (c.findingId || c.id).replace(/[^a-zA-Z0-9]/g, '_');
    const lawText = c.law ? `${c.law} — ` : '';
    const descSnippet = (c.desc || '').substring(0, 90);
    return `
      <div class="issue-item" id="${issueListEl.id}-issue-${safeId}"
        data-finding-id="${c.findingId || ''}"
        data-status="${c.status}"
        onclick="onIssueClick(this, '${issueListEl.id}', '${suggestionTextEl.id}', '${copyBtn.id}')">
        <div class="issue-top">
          <div class="issue-badge ${c.status}">${c.id}</div>
          <div class="issue-name">${c.issue || ''}</div>
        </div>
        <div class="issue-desc">${lawText}${descSnippet}${descSnippet.length >= 90 ? '…' : ''}</div>
      </div>
    `;
  }).join('');
}

// Called when user clicks an issue item in PDF-native mode.
// Reads the finding_id from the element's data attribute, highlights
// the corresponding boxes on the real PDF, and shows the suggestion.
function onIssueClick(el, issueListElId, suggestionTextElId, copyBtnId) {
  const findingId = el.dataset.findingId;
  const contract  = _activeContract;
  if (!contract || !findingId) return;

  // Highlight in issues sidebar
  const issueList = document.getElementById(issueListElId);
  issueList.querySelectorAll('.issue-item').forEach(i => i.classList.remove('active'));
  el.classList.add('active');

  // Scroll + activate the highlight on the real PDF
  if (contract._pdfViewerHandle) {
    contract._pdfViewerHandle.scrollToFinding(findingId);
  }

  // Find the clause to get its suggestion
  const clause = contract.sections.flatMap(s => s.clauses).find(c => c.findingId === findingId);
  if (!clause) return;

  const sEl = document.getElementById(suggestionTextElId);
  if (sEl) {
    const getLawTextWithPage = (lawText) => {
      if (!lawText) return { text: '', url: '#' };
      const lower = lawText.toLowerCase();
      
      if (lower.includes('employment act 1955') || lower.includes('employment act')) {
        let pageInfo = ' (Ref. PDF Act 265)';
        if (lower.includes('60a')) pageInfo = ' (Ref. PDF Page 55)';
        else if (lower.includes('37')) pageInfo = ' (Ref. PDF Page 34)';
        else if (lower.includes('60fa')) pageInfo = ' (Ref. PDF Page 59)';
        else if (lower.includes('12')) pageInfo = ' (Ref. PDF Page 16)';
        return {
          text: `📖 ${lawText}${pageInfo} ↗`,
          url: 'https://lom.agc.gov.my/act-detail.php?language=BI&act=265'
        };
      }
      if (lower.includes('pdpa') || lower.includes('personal data protection')) {
        let pageInfo = ' (Ref. PDF Act 709)';
        if (lower.includes('6')) pageInfo = ' (Ref. PDF Page 15)';
        return {
          text: `📖 ${lawText}${pageInfo} ↗`,
          url: 'https://lom.agc.gov.my/act-detail.php?language=BI&act=709'
        };
      }
      if (lower.includes('companies act')) {
        let pageInfo = ' (Ref. PDF Act 778)';
        if (lower.includes('66')) pageInfo = ' (Ref. PDF Page 44)';
        else if (lower.includes('213')) pageInfo = ' (Ref. PDF Page 121)';
        else if (lower.includes('235')) pageInfo = ' (Ref. PDF Page 130)';
        return {
          text: `📖 ${lawText}${pageInfo} ↗`,
          url: 'https://lom.agc.gov.my/act-detail.php?language=BI&act=778'
        };
      }
      if (lower.includes('contracts act 1950') || lower.includes('contracts act')) {
        let pageInfo = ' (Ref. PDF Act 136)';
        if (lower.includes('75')) pageInfo = ' (Ref. PDF Page 45)';
        else if (lower.includes('28')) pageInfo = ' (Ref. PDF Page 24)';
        else if (lower.includes('29')) pageInfo = ' (Ref. PDF Page 25)';
        else if (lower.includes('10')) pageInfo = ' (Ref. PDF Page 16)';
        else if (lower.includes('13')) pageInfo = ' (Ref. PDF Page 18)';
        else if (lower.includes('30')) pageInfo = ' (Ref. PDF Page 26)';
        return {
          text: `📖 ${lawText}${pageInfo} ↗`,
          url: 'https://lom.agc.gov.my/act-detail.php?language=BI&act=136'
        };
      }
      
      return {
        text: `📖 ${lawText} ↗`,
        url: `https://www.google.com/search?q=${encodeURIComponent(lawText + " Malaysia")}`
      };
    };

    const lawMeta = getLawTextWithPage(clause.law);
    const lawBadgeHtml = clause.law
      ? `<a href="${lawMeta.url}" target="_blank" class="sug-law-badge" title="Click to view official Malaysian Law Document">
           ${lawMeta.text}
         </a>`
      : '';

    sEl.innerHTML = `
      <div class="sug-details">
        ${lawBadgeHtml}
        <div class="sug-explanation">
          <strong>Full Issue Explanation:</strong><br>
          ${renderMarkdown(clause.desc || 'No explanation available.')}
        </div>
        <div class="sug-rewrite-wrap">
          <strong>Suggested Compliant Rewrite:</strong>
          <div class="sug-rewrite-content">${renderMarkdown(clause.suggestion || 'No suggestion available.')}</div>
        </div>
      </div>
    `;
  }

  const boxId = suggestionTextElId === 'suggestion-text' ? 'suggestion-box' : 'history-suggestion-box';
  const boxEl = document.getElementById(boxId);
  if (boxEl) boxEl.classList.remove('collapsed');

  const btn = document.getElementById(copyBtnId);
  if (btn && clause.suggestion) {
    btn.onclick = () => {
      navigator.clipboard.writeText(clause.suggestion).catch(() => {});
      btn.textContent = 'Copied!';
      setTimeout(() => btn.textContent = 'Copy suggestion', 2000);
    };
  }
}

// Activate a finding by ID from a PDF highlight click (bottom-up: PDF → sidebar).
function activateFindingById(findingId, contract, issueListEl, suggestionTextEl, copyBtn, pdfHandle) {
  const safeId = findingId.replace(/[^a-zA-Z0-9]/g, '_');
  const el = document.getElementById(`${issueListEl.id}-issue-${safeId}`);

  issueListEl.querySelectorAll('.issue-item').forEach(i => i.classList.remove('active'));
  if (el) {
    el.classList.add('active');
    el.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }

  if (pdfHandle) pdfHandle.scrollToFinding(findingId);

  const clause = contract.sections.flatMap(s => s.clauses).find(c => c.findingId === findingId);
  if (!clause) return;
  if (suggestionTextEl) suggestionTextEl.innerHTML = renderMarkdown(clause.suggestion || 'No suggestion available.');

  const boxId = suggestionTextEl.id === 'suggestion-text' ? 'suggestion-box' : 'history-suggestion-box';
  const boxEl = document.getElementById(boxId);
  if (boxEl) boxEl.classList.remove('collapsed');

  if (copyBtn && clause.suggestion) {
    copyBtn.onclick = () => {
      navigator.clipboard.writeText(clause.suggestion).catch(() => {});
      copyBtn.textContent = 'Copied!';
      setTimeout(() => copyBtn.textContent = 'Copy suggestion', 2000);
    };
  }
}

function pickIssue(clauseId, containerElId, issueListElId, suggestionTextElId, copyBtnId) {
  // Search active contract (scanner or history)
  const allClauses = _activeContract
    ? _activeContract.sections.flatMap(s => s.clauses)
    : CONTRACTS.flatMap(ct => ct.sections.flatMap(s => s.clauses));
  const clause = allClauses.find(c => c.id === clauseId);
  if (!clause) return;

  // Highlight clause in document
  const container = document.getElementById(containerElId);
  container.querySelectorAll('.clause-line').forEach(el => el.style.outline = 'none');
  const safeId   = clauseId.replace(/\./g, '_');
  const clauseEl = document.getElementById(`${containerElId}-clause-${safeId}`);
  if (clauseEl) {
    clauseEl.style.outline      = '2px solid var(--accent)';
    clauseEl.style.borderRadius = '3px';
    clauseEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }

  // Highlight in issue list
  const issueList = document.getElementById(issueListElId);
  issueList.querySelectorAll('.issue-item').forEach(el => el.classList.remove('active'));
  const issueEl = document.getElementById(`${issueListElId}-issue-${safeId}`);
  if (issueEl) { issueEl.classList.add('active'); issueEl.scrollIntoView({ behavior: 'smooth', block: 'nearest' }); }

  // Show suggestion
  const sEl = document.getElementById(suggestionTextElId);
  if (sEl) sEl.innerHTML = renderMarkdown(clause.suggestion || 'No suggestion available.');

  const boxId = suggestionTextElId === 'suggestion-text' ? 'suggestion-box' : 'history-suggestion-box';
  const boxEl = document.getElementById(boxId);
  if (boxEl) boxEl.classList.remove('collapsed');

  const btn = document.getElementById(copyBtnId);
  if (btn && clause.suggestion) {
    btn.onclick = () => {
      navigator.clipboard.writeText(clause.suggestion).catch(() => {});
      btn.textContent = 'Copied!';
      setTimeout(() => btn.textContent = 'Copy suggestion', 2000);
    };
  }
}

// Holds the contract currently shown in the scanner result
let _activeContract = null;

// ═══════════════════════════════════════════
// BACKEND RESPONSE → FRONTEND CONTRACT FORMAT
// Maps ClauseFinding[] from /api/contracts/analyze
// into the sections/clauses shape our renderer expects
// ═══════════════════════════════════════════
function mapApiResponseToContract(apiResponse, file) {
  const now    = new Date();
  const date   = now.toLocaleDateString('en-MY', { day:'2-digit', month:'short', year:'numeric' });
  const time   = now.toLocaleTimeString('en-MY', { hour:'2-digit', minute:'2-digit' });

  // Group findings by category, preserving the order categories first appear in
  // (this matches the original document's section order, since the backend
  // now walks the contract section-by-section, clause-by-clause).
  const findingMap = {};
  const categoryOrder = [];
  (apiResponse.findings || []).forEach(f => {
    if (!findingMap[f.category]) {
      findingMap[f.category] = [];
      categoryOrder.push(f.category);
    }
    findingMap[f.category].push(f);
  });

  // Build sections from grouped findings, using the REAL clause id
  // (e.g. "1.1", "2.3") extracted from the start of each excerpt when present.
  // For documents with no numbered-clause structure (e.g. plain prose,
  // study notes, unstructured text), fall back to a clean internal counter —
  // never the raw backend rule id (e.g. "broad-liability-waiver-1"), which
  // is meant for tracking only and should never appear in the UI.
  // `findingId` is kept separately (the backend's original finding.id) so
  // it can be used to link clicks to the matching PDF highlight box.
  let fallbackCounter = 0;
  const sections = categoryOrder.map(category => ({
    title: category,
    clauses: findingMap[category].map(f => {
      const idMatch = f.excerpt.match(/^(\d{1,2}\.\d{1,2})\s+/);
      fallbackCounter++;
      const realId   = idMatch ? idMatch[1] : `c${fallbackCounter}`;
      const cleanText = idMatch ? f.excerpt.slice(idMatch[0].length) : f.excerpt;
      return {
        id:         realId,
        findingId:  f.id,
        text:       cleanText,
        status:     severityToStatus(f.severity),
        issue:      f.severity === 'low' ? null : f.title,
        law:        f.law_section || null,
        desc:       f.explanation || null,
        suggestion: f.recommendation || null,
        rewrite:    f.rewrite || null,
      };
    })
  }));

  // If no findings at all, show a single "all clear" section
  if (sections.length === 0) {
    sections.push({
      title: 'Review Summary',
      clauses: [{
        id: '1',
        findingId: null,
        text: 'No risky or hidden clauses were detected in this contract.',
        status: 'ok',
        issue: null, law: null, desc: null, suggestion: null,
      }]
    });
  }

  // Determine overall status for history
  const overallStatus = apiResponse.risk_level === 'critical' || apiResponse.risk_level === 'high'
    ? 'critical'
    : apiResponse.risk_level === 'medium'
    ? 'issues'
    : 'safe';

  // Derive the document title from the document's OWN text — never from
  // the uploaded filename. Many real documents open with a heading line
  // (e.g. "NON-DISCLOSURE AGREEMENT", "EMPLOYMENT CONTRACT"); use that if
  // it looks like a real title. Otherwise, don't fabricate one.
  const rawText = apiResponse.contract_text || '';
  const extractedTitle = extractDocumentTitle(rawText);

  return {
    id:       apiResponse.id || Date.now(),
    filename: apiResponse.file_name || (file ? file.name : ''),
    company:  apiResponse.company || '—',
    date:     apiResponse.date || date,
    time:     apiResponse.time || time,
    status:   overallStatus,
    title:    extractedTitle, // may be '' — renderer hides the title row when empty
    subtitle: '',
    meta:     [], // no fabricated File/Scanned/Summary header — just the real document
    sig:      ['Authorised Signatory', 'Authorised Signatory'],
    sections,
    llmReview: apiResponse.llm_review || null,
    // Kept for the AI chat — sends the full contract + raw findings as context
    rawText,
    apiFindings: apiResponse.findings || [],
    // PDF-native rendering: present only when the upload was a PDF the
    // backend could extract word coordinates from. When present, the
    // viewer renders the REAL PDF via PDF.js with highlight overlays
    // instead of the reconstructed HTML text renderer.
    pdfBase64:      apiResponse.pdf_base64 || null,
    pageSizes:      apiResponse.page_sizes || null,
    highlightBoxes: apiResponse.highlight_boxes || null,
  };
}

// Pulls a plausible title from the start of the real document text.
// Looks for a short, mostly-uppercase first line/sentence (typical of
// document headings like "EMPLOYMENT CONTRACT" or "NON-DISCLOSURE
// AGREEMENT"). Returns '' if nothing reasonable is found — callers should
// not fabricate a fallback from the filename.
function extractDocumentTitle(text) {
  if (!text) return '';
  const firstChunk = text.trim().slice(0, 200);
  // Try to grab the first run of words before a long lowercase sentence starts
  const match = firstChunk.match(/^([A-Z][A-Z0-9 ,&'\-]{4,60})(?=[A-Z][a-z]|\s\d|$)/);
  if (match) return match[1].trim();
  return '';
}

function severityToStatus(severity) {
  if (severity === 'critical' || severity === 'high') return 'bad';
  if (severity === 'medium') return 'warn';
  return 'ok';
}

// Detects when the backend's "reply" text is actually a raw error message
// (e.g. OpenAI quota/billing errors, missing API key) so the UI can show
// a short, friendly message instead of dumping the full error text.
function isAiErrorText(text) {
  return /^(error|ai capabilities are not available|openai client library)/i.test((text || '').trim());
}

// ═══════════════════════════════════════════
// SCANNER — FILE UPLOAD
// ═══════════════════════════════════════════
let _selectedFile = null;

function handleFile(input) {
  if (!input.files[0]) return;
  _selectedFile = input.files[0];
  document.getElementById('file-name').textContent = _selectedFile.name;
  document.getElementById('file-size').textContent = (_selectedFile.size / 1024).toFixed(1) + ' KB';
  document.getElementById('file-preview').classList.add('show');
  document.getElementById('scan-btn').disabled = false;
}

function handleDrop(e) {
  e.preventDefault();
  document.getElementById('upload-zone').classList.remove('drag');
  const f = e.dataTransfer.files[0]; if (!f) return;
  _selectedFile = f;
  document.getElementById('file-name').textContent = f.name;
  document.getElementById('file-size').textContent = (f.size / 1024).toFixed(1) + ' KB';
  document.getElementById('file-preview').classList.add('show');
  document.getElementById('scan-btn').disabled = false;
}

function removeFile() {
  _selectedFile = null;
  document.getElementById('file-preview').classList.remove('show');
  document.getElementById('scan-btn').disabled = true;
  document.getElementById('file-input').value = '';
}

function togglePill(el) { el.classList.toggle('active'); }

// ═══════════════════════════════════════════
// SCANNER — CALL REAL BACKEND API
// ═══════════════════════════════════════════
async function startScan() {
  if (!_selectedFile) return;

  const btn   = document.getElementById('scan-btn');
  const bar   = document.getElementById('progress-bar');
  const fill  = document.getElementById('progress-fill');
  const label = document.getElementById('progress-label');

  btn.disabled = true;
  bar.classList.add('show');

  // Animate progress while waiting for API
  const steps = [
    'Uploading contract…',
    'Extracting text…',
    'Checking Malaysian laws…',
    'Analysing risk clauses…',
    'Generating report…',
  ];
  let stepIdx = 0;
  fill.style.width = '5%';
  label.textContent = steps[0];

  const progressTimer = setInterval(() => {
    if (stepIdx < steps.length - 1) {
      stepIdx++;
      fill.style.width = `${(stepIdx / steps.length) * 85}%`;
      label.textContent = steps[stepIdx];
    }
  }, 800);

  try {
    // Build form data — matches FastAPI endpoint
    const formData = new FormData();
    formData.append('file', _selectedFile);
    formData.append('jurisdiction', 'Malaysia');
    formData.append('language', 'English');

    const response = await fetch(`${API_BASE}/api/contracts/analyze`, {
      method: 'POST',
      body: formData,
    });

    clearInterval(progressTimer);

    if (!response.ok) {
      const err = await response.json().catch(() => ({ detail: 'Unknown error' }));
      throw new Error(err.detail || `Server error ${response.status}`);
    }

    const apiData = await response.json();

    fill.style.width = '100%';
    label.textContent = 'Done!';

    await new Promise(r => setTimeout(r, 400));

    const contract = mapApiResponseToContract(apiData, _selectedFile);
    _activeContract = contract;
    _chatHistory = []; // fresh conversation context for this contract

    // Save to history (persisted to localStorage so it survives refresh)
    SCAN_HISTORY.unshift(contract);
    saveLocalScanHistory();
    buildHistoryList();

    showResults(contract);

  } catch (err) {
    clearInterval(progressTimer);
    fill.style.width  = '100%';
    fill.style.background = '#E84040';
    label.textContent = `Error: ${err.message}`;
    btn.disabled = false;
    console.error('Scan failed:', err);
  }
}

function showResults(contract) {
  toggleSeverityFilter(null, 'scanner');
  document.getElementById('upload-view').style.display = 'none';
  document.getElementById('progress-bar').classList.remove('show');
  document.getElementById('progress-fill').style.background = '';

  const hasIssues = contract.sections.some(s => s.clauses.some(c => c.status !== 'ok'));

  if (!hasIssues) {
    document.getElementById('safe-result').classList.add('show');
    return;
  }

  document.getElementById('results-filename').textContent = contract.filename;
  document.getElementById('results-view').classList.add('show');

  const allC = contract.sections.flatMap(s => s.clauses);
  document.getElementById('s-chip-ok').textContent   = `✓ ${allC.filter(c=>c.status==='ok').length} safe`;
  document.getElementById('s-chip-warn').textContent = `⚠ ${allC.filter(c=>c.status==='warn').length} warn`;
  document.getElementById('s-chip-bad').textContent  = `✕ ${allC.filter(c=>c.status==='bad').length} critical`;

  if (contract.pdfBase64) {
    // PDF-native mode: render the REAL PDF via PDF.js with coordinate highlights
    document.getElementById('contract-page-content').style.display = 'none';
    const pdfViewerEl = document.getElementById('pdf-viewer');
    pdfViewerEl.style.display = 'flex';

    renderPdfNative(
      pdfViewerEl,
      contract.pdfBase64,
      contract.pageSizes,
      contract.highlightBoxes,
    ).then(handle => {
      contract._pdfViewerHandle = handle;

      // Wire up PDF highlight click → sidebar + suggestion
      window.onPdfHighlightClick = (findingId) => {
        activateFindingById(findingId, contract,
          document.getElementById('issues-list'),
          document.getElementById('suggestion-text'),
          document.getElementById('copy-btn'),
          handle,
        );
      };
    });

    // Build issues list only (no HTML text document to render)
    renderIssuesList(
      contract,
      document.getElementById('issues-list'),
      document.getElementById('chip-ok'),
      document.getElementById('chip-warn'),
      document.getElementById('chip-bad'),
      document.getElementById('suggestion-text'),
      document.getElementById('copy-btn'),
      null, // no text container
    );

  } else {
    // Fallback text mode: for non-PDF uploads (txt, docx) or PDFs where
    // coordinate extraction failed — same old reconstructed-HTML approach
    document.getElementById('pdf-viewer').style.display = 'none';
    const textEl = document.getElementById('contract-page-content');
    textEl.style.display = '';
    renderContractPage(
      contract,
      textEl,
      document.getElementById('issues-list'),
      document.getElementById('chip-ok'),
      document.getElementById('chip-warn'),
      document.getElementById('chip-bad'),
      document.getElementById('suggestion-text'),
      document.getElementById('copy-btn'),
    );
  }

  // Show LLM review in suggestion box if available
  if (contract.llmReview) {
    const reviewText = contract.llmReview.review || '';
    document.getElementById('suggestion-text').innerHTML = isAiErrorText(reviewText)
      ? 'Error. Please try again.'
      : renderMarkdown(reviewText);
  }
}

function resetScanner() {
  _activeContract = null;
  _selectedFile   = null;
  document.getElementById('results-view').classList.remove('show');
  document.getElementById('safe-result').classList.remove('show');
  document.getElementById('upload-view').style.display = 'block';
  document.getElementById('file-preview').classList.remove('show');
  document.getElementById('scan-btn').disabled = true;
  document.getElementById('progress-fill').style.width = '0%';
  document.getElementById('progress-label').textContent = '';
  document.getElementById('file-input').value = '';
}

// ═══════════════════════════════════════════
// HISTORY — persisted in SQLite database, falling back to localStorage/seed data
// ═══════════════════════════════════════════
const HISTORY_STORAGE_KEY = 'contractsense_scan_history_v1';

function loadLocalScanHistory() {
  try {
    const raw = localStorage.getItem(HISTORY_STORAGE_KEY);
    if (raw) {
      const saved = JSON.parse(raw);
      if (Array.isArray(saved) && saved.length > 0) return saved;
    }
  } catch (e) {
    console.error('Failed to load scan history from localStorage:', e);
  }
  return [...CONTRACTS];
}

function saveLocalScanHistory() {
  try {
    localStorage.setItem(HISTORY_STORAGE_KEY, JSON.stringify(SCAN_HISTORY));
  } catch (e) {
    console.error('Failed to save scan history to localStorage:', e);
  }
}

let SCAN_HISTORY = loadLocalScanHistory();

async function loadScanHistory(isSilent = false, searchQuery = '') {
  const btn = document.getElementById('btn-refresh-history');
  if (btn && !isSilent) btn.textContent = '🔄 Syncing...';
  
  try {
    let url = `${API_BASE}/api/history`;
    if (searchQuery) {
      url += `?search=${encodeURIComponent(searchQuery)}`;
    }
    const res = await fetch(url);
    if (res.ok) {
      const dbHistory = await res.json();
      if (dbHistory && dbHistory.length > 0) {
        SCAN_HISTORY = dbHistory;
      } else if (searchQuery) {
        SCAN_HISTORY = [];
      } else {
        SCAN_HISTORY = loadLocalScanHistory();
      }
    } else {
      SCAN_HISTORY = loadLocalScanHistory();
    }
  } catch (err) {
    console.error('Failed to fetch history from database:', err);
    SCAN_HISTORY = loadLocalScanHistory();
  }
  
  buildHistoryList();
  updateAutomatedScansCount();
  
  if (btn && !isSilent) {
    btn.textContent = '🔄 Refresh list';
  }
}

let _historySearchTimeout = null;
function onHistorySearch() {
  clearTimeout(_historySearchTimeout);
  _historySearchTimeout = setTimeout(async () => {
    const query = document.getElementById('history-search-input').value.trim();
    await loadScanHistory(false, query);
  }, 300);
}

async function checkEmailConnectionStatus() {
  try {
    const res = await fetch(`${API_BASE}/api/automation/email-config`);
    if (!res.ok) throw new Error(`Server status ${res.status}`);
    const data = await res.json();
    
    const dot = document.getElementById('email-status-dot');
    const label = document.getElementById('email-status-label');
    const form = document.getElementById('email-connect-form');
    const connView = document.getElementById('email-connected-view');
    const emailLabel = document.getElementById('connected-email-label');
    
    if (data.is_connected) {
      if (dot) {
        dot.className = 'status-dot online';
        dot.style.background = 'var(--green)';
        dot.style.boxShadow = '0 0 8px var(--green)';
      }
      if (label) label.textContent = 'Connected';
      if (form) form.style.display = 'none';
      if (connView) connView.style.display = 'block';
      if (emailLabel) emailLabel.textContent = data.email_address;
    } else {
      if (dot) {
        dot.className = 'status-dot offline';
        dot.style.background = 'var(--text3)';
        dot.style.boxShadow = 'none';
      }
      if (label) label.textContent = 'Disconnected';
      if (form) form.style.display = 'block';
      if (connView) connView.style.display = 'none';
    }
  } catch (err) {
    console.error('Failed to check email connection status:', err);
  }
}

async function connectEmailInbox() {
  const server = document.getElementById('imap-server').value.trim();
  const portInput = document.getElementById('imap-port').value.trim();
  const email = document.getElementById('email-address').value.trim();
  const password = document.getElementById('email-password').value.trim();
  
  const btn = document.getElementById('btn-connect-email');
  const errorMsg = document.getElementById('email-error-msg');
  
  const port = parseInt(portInput, 10);
  
  if (!server || !portInput || isNaN(port) || !email || !password) {
    if (errorMsg) {
      errorMsg.textContent = 'Please fill in all email settings fields.';
      errorMsg.style.display = 'block';
    }
    return;
  }
  
  if (errorMsg) errorMsg.style.display = 'none';
  if (btn) {
    btn.disabled = true;
    btn.textContent = '🔌 Connecting...';
  }
  
  try {
    const res = await fetch(`${API_BASE}/api/automation/email-config`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        imap_server: server,
        imap_port: port,
        email_address: email,
        email_password: password
      })
    });
    
    if (!res.ok) {
      const data = await res.json().catch(() => ({ detail: 'Unknown error' }));
      throw new Error(data.detail || `Server error ${res.status}`);
    }
    
    // Clear password input
    document.getElementById('email-password').value = '';
    
    // Check status
    await checkEmailConnectionStatus();
    
  } catch (err) {
    console.error('Email connection failed:', err);
    if (errorMsg) {
      errorMsg.textContent = err.message;
      errorMsg.style.display = 'block';
    }
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = '🔌 Connect Inbox';
    }
  }
}

async function disconnectEmailInbox() {
  if (!confirm('Disconnect your email inbox? The backend will stop automated email monitoring.')) return;
  
  const btn = document.getElementById('btn-disconnect-email');
  if (btn) {
    btn.disabled = true;
    btn.textContent = 'Disconnecting...';
  }
  
  try {
    const res = await fetch(`${API_BASE}/api/automation/email-config`, {
      method: 'DELETE'
    });
    
    if (!res.ok) throw new Error(`Server returned ${res.status}`);
    
    await checkEmailConnectionStatus();
  } catch (err) {
    console.error('Failed to disconnect email:', err);
    alert('Failed to disconnect email inbox.');
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = '🔌 Disconnect Inbox';
    }
  }
}

function updateAutomatedScansCount() {
  const count = SCAN_HISTORY.filter(c => c.is_automated).length;
  const el = document.getElementById('automated-scans-count');
  if (el) el.textContent = count;
}

function buildHistoryList(filter = 'all') {
  // 1. General history table
  const body = document.getElementById('history-table-body');
  if (body) {
    const rows = SCAN_HISTORY.filter(c => filter === 'all' || c.status === filter);
    body.innerHTML = rows.map(c => `
      <div class="table-row">
        <div class="date-col">${c.date}<div class="time">${c.time}</div></div>
        <span class="contract-link" onclick="openHistoryDetail(${c.id})">${c.filename}</span>
        <span class="company-col">${c.company}</span>
        <span><div class="status-badge ${c.status}">${
          c.status === 'safe' ? '✓ Safe' : c.status === 'issues' ? '⚠ Issues' : '✕ Critical'
        }</div></span>
        <span style="display:flex;gap:4px">
          <button class="view-btn" onclick="openHistoryDetail(${c.id})">View</button>
          <button class="view-btn" style="border-color:var(--red);color:var(--red)" onclick="deleteHistoryItem(${c.id}, event)">✕</button>
        </span>
      </div>
    `).join('');
  }

  // 2. Automatically scanned contracts table (Auto-Scan tab)
  const autoBody = document.getElementById('autoscan-table-body');
  if (autoBody) {
    const autoRows = SCAN_HISTORY.filter(c => c.is_automated);
    autoBody.innerHTML = autoRows.map(c => `
      <div class="table-row">
        <div class="date-col">${c.date}<div class="time">${c.time}</div></div>
        <span class="contract-link" onclick="openHistoryDetail(${c.id})">${c.filename}</span>
        <span class="company-col">${c.company}</span>
        <span><div class="status-badge ${c.status}">${
          c.status === 'safe' ? '✓ Safe' : c.status === 'issues' ? '⚠ Issues' : '✕ Critical'
        }</div></span>
        <span style="display:flex;gap:4px">
          <button class="view-btn" onclick="openHistoryDetail(${c.id})">View</button>
          <button class="view-btn" style="border-color:var(--red);color:var(--red)" onclick="deleteHistoryItem(${c.id}, event)">✕</button>
        </span>
      </div>
    `).join('');
  }
}

function filterHistory(btn, filter) {
  document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  buildHistoryList(filter);
}

async function clearScanHistory() {
  if (!confirm('Clear all scan history from database? This cannot be undone.')) return;
  try {
    await fetch(`${API_BASE}/api/history`, { method: 'DELETE' });
    SCAN_HISTORY = [];
    localStorage.removeItem(HISTORY_STORAGE_KEY);
    buildHistoryList();
    updateAutomatedScansCount();
  } catch (err) {
    console.error('Failed to clear history:', err);
    alert('Failed to clear database history.');
  }
}

async function deleteHistoryItem(id, event) {
  if (event) event.stopPropagation();
  if (!confirm('Delete this contract scan from database?')) return;
  try {
    const res = await fetch(`${API_BASE}/api/history/${id}`, { method: 'DELETE' });
    if (!res.ok) throw new Error(`Server returned ${res.status}`);
    
    SCAN_HISTORY = SCAN_HISTORY.filter(c => c.id !== id);
    const localSaved = localStorage.getItem(HISTORY_STORAGE_KEY);
    if (localSaved) {
      const parsed = JSON.parse(localSaved);
      const updated = parsed.filter(c => c.id !== id);
      localStorage.setItem(HISTORY_STORAGE_KEY, JSON.stringify(updated));
    }
    
    buildHistoryList();
    updateAutomatedScansCount();
  } catch (err) {
    console.error('Failed to delete history item:', err);
    alert('Failed to delete item from database.');
  }
}

async function triggerAutoScan() {
  const btn = document.getElementById('btn-trigger-scan');
  const statusText = document.getElementById('auto-status-text');
  
  if (btn) btn.disabled = true;
  if (statusText) statusText.textContent = 'Scanning auto_import folder...';
  
  try {
    const res = await fetch(`${API_BASE}/api/automation/scan`, { method: 'POST' });
    if (!res.ok) throw new Error(`Server returned ${res.status}`);
    const data = await res.json();
    
    if (statusText) {
      statusText.textContent = `Active · Monitoring folders (${data.imported_count} new contracts imported)`;
    }
    
    await loadScanHistory();
    
    setTimeout(() => {
      if (statusText) statusText.textContent = 'Active · Monitoring folders';
    }, 4000);
    
  } catch (err) {
    console.error('Automation trigger failed:', err);
    if (statusText) statusText.textContent = 'Active · Folder scan failed';
    setTimeout(() => {
      if (statusText) statusText.textContent = 'Active · Monitoring folders';
    }, 4000);
  } finally {
    if (btn) btn.disabled = false;
  }
}

async function openHistoryDetail(id) {
  toggleSeverityFilter(null, 'history');
  
  let contract = SCAN_HISTORY.find(c => c.id === id);
  if (!contract) return;

  // Clear previous details and show premium loading state immediately
  document.getElementById('hd-title').textContent = 'Generating compliance report...';
  
  // Fill exactly 3 dummy elements to satisfy children[0]/[1]/[2] references safely before real rendering
  document.getElementById('hd-chips').innerHTML = '<div class="chip">...</div><div class="chip">...</div><div class="chip">...</div>';
  document.getElementById('hd-issue-chips').innerHTML = '';
  
  document.getElementById('history-issues-list').innerHTML = `
    <div class="loading-indicator loading-indicator-pulse">
      <div class="spinner"></div>
      <div>Analysing contract clauses...</div>
    </div>
  `;
  document.getElementById('history-pdf-viewer').innerHTML = `
    <div class="loading-indicator">
      <div class="spinner"></div>
      <div>Rendering document layout...</div>
    </div>
  `;
  document.getElementById('history-page-content').innerHTML = '';
  document.getElementById('history-page-content').style.display = 'none';
  document.getElementById('history-pdf-viewer').style.display = 'flex';
  document.getElementById('history-suggestion-box').classList.add('collapsed');

  const detailOverlay = document.getElementById('history-detail');
  if (detailOverlay) detailOverlay.classList.add('show');

  // Load detailed scan results if they are not in memory
  if (!contract.sections) {
    try {
      const res = await fetch(`${API_BASE}/api/history/${id}`);
      if (!res.ok) throw new Error(`Server returned ${res.status}`);
      const dbDetail = await res.json();
      
      const mapped = mapApiResponseToContract(dbDetail, { name: dbDetail.file_name });
      mapped.id = id; // preserve DB id
      
      const idx = SCAN_HISTORY.findIndex(c => c.id === id);
      if (idx !== -1) {
        SCAN_HISTORY[idx] = mapped;
      }
      contract = mapped;
    } catch (err) {
      console.error('Failed to load contract details:', err);
      document.getElementById('hd-title').textContent = 'Error Loading Report';
      document.getElementById('history-issues-list').innerHTML = `
        <div style="padding: 40px 20px; text-align: center; color: var(--red)">
          ✕ Failed to load contract details.
        </div>
      `;
      document.getElementById('history-pdf-viewer').innerHTML = `
        <div style="padding: 40px 20px; text-align: center; color: var(--text3)">
          Please close and try again.
        </div>
      `;
      return;
    }
  }

  _activeContract = contract;
  _chatHistory = []; // fresh conversation context for this contract

  document.getElementById('hd-title').textContent = contract.filename;

  const allC = contract.sections.flatMap(s => s.clauses);
  const ok   = allC.filter(c => c.status === 'ok').length;
  const warn = allC.filter(c => c.status === 'warn').length;
  const bad  = allC.filter(c => c.status === 'bad').length;

  document.getElementById('hd-chips').innerHTML = `
    <div class="chip ok">✓ ${ok}</div>
    <div class="chip warn">⚠ ${warn}</div>
    <div class="chip bad">✕ ${bad}</div>
  `;
  document.getElementById('hd-issue-chips').innerHTML = `
    <div class="chip ok" onclick="toggleSeverityFilter('ok', 'history')">✓ ${ok} safe</div>
    <div class="chip warn" onclick="toggleSeverityFilter('warn', 'history')">⚠ ${warn} warn</div>
    <div class="chip bad" onclick="toggleSeverityFilter('bad', 'history')">✕ ${bad} critical</div>
  `;

  if (contract.pdfBase64) {
    // PDF-native mode for history too
    document.getElementById('history-page-content').style.display = 'none';
    const pdfViewerEl = document.getElementById('history-pdf-viewer');
    pdfViewerEl.style.display = 'flex';

    renderPdfNative(
      pdfViewerEl,
      contract.pdfBase64,
      contract.pageSizes,
      contract.highlightBoxes,
    ).then(handle => {
      contract._pdfViewerHandle = handle;
      window.onPdfHighlightClick = (findingId) => {
        activateFindingById(findingId, contract,
          document.getElementById('history-issues-list'),
          document.getElementById('history-suggestion-text'),
          document.getElementById('h-copy-btn'),
          handle,
        );
      };
    });

    renderIssuesList(
      contract,
      document.getElementById('history-issues-list'),
      document.getElementById('hd-chips').children[0],
      document.getElementById('hd-chips').children[1],
      document.getElementById('hd-chips').children[2],
      document.getElementById('history-suggestion-text'),
      document.getElementById('h-copy-btn'),
      null,
    );
  } else {
    // Fallback text mode for non-PDF history contracts
    document.getElementById('history-pdf-viewer').style.display = 'none';
    const textEl = document.getElementById('history-page-content');
    textEl.style.display = '';
    renderContractPage(
      contract,
      textEl,
      document.getElementById('history-issues-list'),
      document.getElementById('hd-chips').children[0],
      document.getElementById('hd-chips').children[1],
      document.getElementById('hd-chips').children[2],
      document.getElementById('history-suggestion-text'),
      document.getElementById('h-copy-btn'),
    );
  }

  document.getElementById('history-detail').classList.add('show');
}

function closeHistoryDetail() {
  _activeContract = null;
  document.getElementById('history-detail').classList.remove('show');
}


// ═══════════════════════════════════════════
// AI CHAT
// ═══════════════════════════════════════════
// ═══════════════════════════════════════════
// SIDEBAR TOGGLE — hide/show issues panel for a larger contract view
// ═══════════════════════════════════════════
function toggleSidebar(context) {
  const btnLabelId = context === 'scanner' ? 'scanner-sidebar-toggle-label' : 'history-sidebar-toggle-label';
  const btnId = context === 'scanner' ? 'scanner-sidebar-toggle' : 'history-sidebar-toggle';

  const panel = document.querySelector(
    context === 'scanner' ? '.results-layout .issues-panel' : '.hd-issues-panel'
  );
  const label = document.getElementById(btnLabelId);
  const btn   = document.getElementById(btnId);
  if (!panel) return;

  const collapsed = panel.classList.toggle('collapsed');
  if (btn) btn.classList.toggle('collapsed', collapsed);
  if (label) label.textContent = collapsed ? 'Show panel' : 'Hide panel';
}

function toggleChat() { document.getElementById('chat-box').classList.toggle('open'); }
function toggleBig()  { document.getElementById('chat-box').classList.toggle('big'); }

// Keeps the running conversation in the {role, content} shape the backend expects
let _chatHistory = [];

async function sendMsg() {
  const inp = document.getElementById('chat-input');
  const val = inp.value.trim();
  if (!val) return;

  const msgs = document.getElementById('chat-messages');
  msgs.innerHTML += `<div class="msg user"><div class="msg-avatar">👤</div><div class="msg-bubble">${escapeHtml(val)}</div></div>`;
  inp.value = '';
  msgs.scrollTop = msgs.scrollHeight;

  // Typing indicator
  const typingId = `typing-${Date.now()}`;
  msgs.innerHTML += `<div class="msg ai" id="${typingId}"><div class="msg-avatar">🤖</div><div class="msg-bubble">Thinking…</div></div>`;
  msgs.scrollTop = msgs.scrollHeight;

  // Build context from whichever contract is currently open (scanner result or history).
  // If no contract is loaded, send empty context — the AI can still answer
  // general Malaysian law questions from its own knowledge.
  const contractText = _activeContract?.rawText || '';
  const rawFindings  = _activeContract?.apiFindings || [];

  try {
    const res = await fetch(`${API_BASE}/api/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        message: val,
        contract_text: contractText,
        findings: rawFindings,
        chat_history: _chatHistory,
      }),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: `Server error ${res.status}` }));
      throw new Error(err.detail || `Server error ${res.status}`);
    }

    const data = await res.json();
    const reply = data.reply || 'No response received.';

    // The backend can return a long raw error string as a normal reply
    // (e.g. OpenAI quota/billing errors) — catch that case too and show
    // a short, friendly message instead of dumping the full error.
    const displayReply = isAiErrorText(reply) ? 'Error. Please try again.' : reply;

    document.getElementById(typingId).querySelector('.msg-bubble').innerHTML = renderMarkdown(displayReply);

    if (!isAiErrorText(reply)) {
      _chatHistory.push({ role: 'user', content: val });
      _chatHistory.push({ role: 'assistant', content: reply });
    }

  } catch (err) {
    document.getElementById(typingId).querySelector('.msg-bubble').innerHTML = 'Error. Please try again.';
    console.error('Chat failed:', err);
  }

  msgs.scrollTop = msgs.scrollHeight;
}

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

// ═══════════════════════════════════════════
// RESIZABLE PANEL UTILITIES
// ═══════════════════════════════════════════
function makeResizable(dividerId, panelClass) {
  const divider = document.getElementById(dividerId);
  if (!divider) return;
  const layout = divider.parentElement;
  const panel = layout.querySelector(panelClass);
  if (!panel) return;
  
  let isDragging = false;
  
  divider.addEventListener('mousedown', (e) => {
    isDragging = true;
    divider.classList.add('dragging');
    panel.classList.add('dragging');
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
    e.preventDefault();
  });
  
  document.addEventListener('mousemove', (e) => {
    if (!isDragging) return;
    const layoutRect = layout.getBoundingClientRect();
    const newWidth = layoutRect.right - e.clientX;
    if (newWidth > 200 && newWidth < 800) {
      panel.style.width = `${newWidth}px`;
      panel.style.flex = 'none';
    }
  });
  
  document.addEventListener('mouseup', () => {
    if (isDragging) {
      isDragging = false;
      divider.classList.remove('dragging');
      panel.classList.remove('dragging');
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
    }
  });
}

function makeDraggable(el) {
  if (!el) return;
  let pos1 = 0, pos2 = 0, pos3 = 0, pos4 = 0;
  let hasMoved = false;

  el.addEventListener('mousedown', dragMouseDown);

  function dragMouseDown(e) {
    e = e || window.event;
    if (e.button !== 0) return;
    pos3 = e.clientX;
    pos4 = e.clientY;
    hasMoved = false;
    document.addEventListener('mouseup', closeDragElement);
    document.addEventListener('mousemove', elementDrag);
    e.preventDefault();
  }

  function elementDrag(e) {
    e = e || window.event;
    pos1 = pos3 - e.clientX;
    pos2 = pos4 - e.clientY;
    pos3 = e.clientX;
    pos4 = e.clientY;
    
    const newTop = el.offsetTop - pos2;
    const newLeft = el.offsetLeft - pos1;
    
    const padding = 10;
    const maxTop = window.innerHeight - el.offsetHeight - padding;
    const maxLeft = window.innerWidth - el.offsetWidth - padding;
    
    el.style.top = `${Math.max(padding, Math.min(newTop, maxTop))}px`;
    el.style.left = `${Math.max(padding, Math.min(newLeft, maxLeft))}px`;
    el.style.bottom = 'auto';
    el.style.right = 'auto';
    
    if (Math.abs(pos1) > 2 || Math.abs(pos2) > 2) {
      hasMoved = true;
    }
  }

  function closeDragElement() {
    document.removeEventListener('mouseup', closeDragElement);
    document.removeEventListener('mousemove', elementDrag);
  }

  el.addEventListener('click', (e) => {
    if (hasMoved) {
      e.stopImmediatePropagation();
      e.preventDefault();
      hasMoved = false;
    }
  }, { capture: true });
}

// Initialize resize & drag handlers after DOM load
window.addEventListener('DOMContentLoaded', () => {
  makeResizable('scanner-resize-divider', '.issues-panel');
  makeResizable('history-resize-divider', '.hd-issues-panel');
  makeDraggable(document.querySelector('.chat-fab'));
});

// ═══════════════════════════════════════════
// MARKDOWN TO HTML RENDERER
// ═══════════════════════════════════════════
function renderMarkdown(text) {
  if (!text) return '';
  
  let html = text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');

  // Bold text: **text** -> <strong>text</strong>
  html = html.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
  
  // Italic text: *text* -> <em>text</em>
  html = html.replace(/\*(.*?)\*/g, '<em>$1</em>');

  // Headings
  html = html.replace(/^#### (.*?)$/gm, '<h4>$1</h4>');
  html = html.replace(/^### (.*?)$/gm, '<h3>$1</h3>');
  html = html.replace(/^## (.*?)$/gm, '<h2>$1</h2>');
  html = html.replace(/^# (.*?)$/gm, '<h1>$1</h1>');

  // Bullet items: - item -> <li>item</li>
  html = html.replace(/^\s*-\s+(.*?)$/gm, '<li>$1</li>');

  const blocks = html.split('\n\n');
  const renderedBlocks = blocks.map(block => {
    block = block.trim();
    if (!block) return '';
    if (block.startsWith('<h') || block.startsWith('<li') || block.startsWith('<ul') || block.startsWith('<ol')) {
      return block;
    }
    return `<p>${block.replace(/\n/g, '<br>')}</p>`;
  });

  return renderedBlocks.join('\n');
}

// ═══════════════════════════════════════════
// INIT
// ═══════════════════════════════════════════
loadScanHistory();
checkEmailConnectionStatus();

// Automatically sync history and connection status every 4 seconds in the background
setInterval(() => {
  const historyPage = document.getElementById('page-history');
  const autoScanPage = document.getElementById('page-autoscan');
  const settingsPage = document.getElementById('page-settings');
  
  const isHistoryActive = historyPage && historyPage.classList.contains('active');
  const isAutoScanActive = autoScanPage && autoScanPage.classList.contains('active');
  const isSettingsActive = settingsPage && settingsPage.classList.contains('active');
  
  if (isHistoryActive || isAutoScanActive || isSettingsActive) {
    loadScanHistory(true); // silent sync without button text blinking
    checkEmailConnectionStatus();
  }
}, 4000);

// ═══════════════════════════════════════════
// SEVERITY STATUS CHIP FILTERING
// ═══════════════════════════════════════════
let _activeFilters = {
  scanner: null,
  history: null
};

function toggleSeverityFilter(status, context) {
  const current = _activeFilters[context];
  const newFilter = (status === null || current === status) ? null : status;
  _activeFilters[context] = newFilter;

  // 1. Update chip active states in the header
  const containerId = context === 'scanner' ? 'results-view' : 'history-detail';
  const container = document.getElementById(containerId);
  if (!container) return;

  const chips = container.querySelectorAll('.status-chips .chip');
  chips.forEach(chip => {
    let chipStatus = '';
    if (chip.classList.contains('ok')) chipStatus = 'ok';
    else if (chip.classList.contains('warn')) chipStatus = 'warn';
    else if (chip.classList.contains('bad')) chipStatus = 'bad';

    if (newFilter && chipStatus === newFilter) {
      chip.classList.add('active');
    } else {
      chip.classList.remove('active');
    }
  });

  // 2. Filter the issues list
  const listId = context === 'scanner' ? 'issues-list' : 'history-issues-list';
  const listEl = document.getElementById(listId);
  if (listEl) {
    const items = listEl.querySelectorAll('.issue-item');
    items.forEach(item => {
      const itemStatus = item.dataset.status;
      if (!newFilter || itemStatus === newFilter) {
        item.style.display = 'block';
      } else {
        item.style.display = 'none';
      }
    });
  }

  // 3. Filter PDF highlights (if rendering PDF)
  const pdfId = context === 'scanner' ? 'pdf-viewer' : 'history-pdf-viewer';
  const pdfEl = document.getElementById(pdfId);
  if (pdfEl && pdfEl.style.display !== 'none') {
    const highlights = pdfEl.querySelectorAll('.pdf-highlight');
    highlights.forEach(hl => {
      const isCriticalOrHigh = hl.classList.contains('sev-critical') || hl.classList.contains('sev-high');
      const isMedium = hl.classList.contains('sev-medium');
      let hlStatus = 'ok';
      if (isCriticalOrHigh) hlStatus = 'bad';
      else if (isMedium) hlStatus = 'warn';

      if (!newFilter || hlStatus === newFilter) {
        hl.style.display = 'block';
      } else {
        hl.style.display = 'none';
      }
    });
  }

  // 4. Filter text highlights (if in plain text mode)
  const textId = context === 'scanner' ? 'contract-page-content' : 'history-page-content';
  const textEl = document.getElementById(textId);
  if (textEl && textEl.style.display !== 'none') {
    textEl.classList.remove('filter-only-bad', 'filter-only-warn', 'filter-only-ok');
    if (newFilter === 'bad') {
      textEl.classList.add('filter-only-bad');
    } else if (newFilter === 'warn') {
      textEl.classList.add('filter-only-warn');
    } else if (newFilter === 'ok') {
      textEl.classList.add('filter-only-ok');
    }
  }
}

function dismissSuggestion(context) {
  const boxId = context === 'scanner' ? 'suggestion-box' : 'history-suggestion-box';
  const box = document.getElementById(boxId);
  if (box) {
    box.classList.add('collapsed');
  }
}

// ═══════════════════════════════════════════
// DOCUMENT EDITOR ROUTINES
// ═══════════════════════════════════════════
let _editorSourcePage = 'scanner'; // 'scanner' or 'history'
let _editorIssues = [];
let _editorWizardIndex = 0;
let _editorMode = 'auto'; // 'auto' or 'manual'
let _editorAppliedSuggestions = [];

function openEditorFromScanner() {
  if (!_activeContract) return;
  _editorSourcePage = 'scanner';
  openEditor();
}

function openEditorFromHistory() {
  if (!_activeContract) return;
  _editorSourcePage = 'history';
  document.getElementById('history-detail').classList.remove('show');
  openEditor();
}

function openEditor() {
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  document.getElementById('page-editor').classList.add('active');
  
  document.getElementById('editor-filename').textContent = `Editing: ${_activeContract.filename}`;
  
  const paper = document.getElementById('editor-textarea');
  const rawText = _activeContract.rawText || '';
  
  const paragraphs = rawText.split('\n').map(line => {
    const clean = line.trim();
    return `<p>${clean || '&nbsp;'}</p>`;
  }).join('');
  paper.innerHTML = paragraphs;
  
  makeResizable('editor-resize-divider', '.editor-sidebar');
  
  _editorIssues = [];
  _activeContract.sections.forEach(sec => {
    sec.clauses.forEach(c => {
      if ((c.status === 'bad' || c.status === 'warn') && (c.rewrite || c.suggestion)) {
        _editorIssues.push({
          id: c.id,
          findingId: c.findingId,
          title: c.issue || 'Compliance Issue',
          originalText: c.text.trim(),
          rewrite: c.rewrite || c.suggestion,
          law: c.law
        });
      }
    });
  });
  
  _editorWizardIndex = 0;
  _editorAppliedSuggestions = [];
  document.getElementById('applied-list').innerHTML = '';
  
  setEditMode('auto');
  updateWizardUI();
}

function backToSourcePage() {
  document.getElementById('page-editor').classList.remove('active');
  if (_editorSourcePage === 'scanner') {
    goPage('scanner');
    if (_activeContract) {
      showResults(_activeContract);
    }
  } else {
    goPage('history');
    if (_activeContract) {
      openHistoryDetail(_activeContract.id);
    }
  }
}

function setEditMode(mode) {
  _editorMode = mode;
  document.getElementById('btn-mode-auto').classList.toggle('active', mode === 'auto');
  document.getElementById('btn-mode-manual').classList.toggle('active', mode === 'manual');
  
  document.getElementById('pane-auto-edit').classList.toggle('active', mode === 'auto');
  document.getElementById('pane-manual-review').classList.toggle('active', mode === 'manual');
  
  if (mode === 'manual') {
    highlightWizardClause();
  } else {
    removeWizardHighlight();
  }
}

function updateWizardUI() {
  const wizard = document.getElementById('review-wizard');
  const noIssues = document.getElementById('editor-no-issues');
  
  if (_editorIssues.length === 0 || _editorWizardIndex >= _editorIssues.length) {
    wizard.style.display = 'none';
    noIssues.style.display = 'block';
    removeWizardHighlight();
    return;
  }
  
  wizard.style.display = 'block';
  noIssues.style.display = 'none';
  
  const current = _editorIssues[_editorWizardIndex];
  document.getElementById('wizard-step-label').textContent = `Issue ${_editorWizardIndex + 1} of ${_editorIssues.length}`;
  document.getElementById('wizard-issue-title').textContent = `${current.title}`;
  document.getElementById('wizard-original-text').textContent = current.originalText;
  document.getElementById('wizard-rewrite-text').value = current.rewrite;
  
  if (_editorMode === 'manual') {
    highlightWizardClause();
  }
}

function highlightWizardClause() {
  removeWizardHighlight();
  
  if (_editorWizardIndex >= _editorIssues.length) return;
  const current = _editorIssues[_editorWizardIndex];
  const textToFind = current.originalText;
  if (!textToFind) return;
  
  const paper = document.getElementById('editor-textarea');
  const paragraphs = paper.getElementsByTagName('p');
  
  for (let p of paragraphs) {
    const text = (p.innerText || p.textContent).trim();
    if (text.includes(textToFind) || textToFind.includes(text)) {
      p.scrollIntoView({ behavior: 'smooth', block: 'center' });
      p.style.outline = '2px solid var(--accent)';
      p.style.borderRadius = '4px';
      p.style.background = 'rgba(79, 142, 247, 0.05)';
      p.setAttribute('data-wizard-hl', 'true');
      break;
    }
  }
}

function removeWizardHighlight() {
  const paper = document.getElementById('editor-textarea');
  const elements = paper.querySelectorAll('[data-wizard-hl="true"]');
  elements.forEach(el => {
    el.style.outline = 'none';
    el.style.background = 'none';
    el.removeAttribute('data-wizard-hl');
  });
}

function confirmWizardStep() {
  if (_editorWizardIndex >= _editorIssues.length) return;
  
  const current = _editorIssues[_editorWizardIndex];
  const editedRewrite = document.getElementById('wizard-rewrite-text').value.trim();
  
  if (!editedRewrite) return;
  
  const paper = document.getElementById('editor-textarea');
  const paragraphs = paper.getElementsByTagName('p');
  let replaced = false;
  
  for (let p of paragraphs) {
    const text = (p.innerText || p.textContent).trim();
    if (text.includes(current.originalText)) {
      p.innerHTML = text.replace(current.originalText, editedRewrite);
      p.setAttribute('data-wizard-hl', 'true');
      replaced = true;
      break;
    } else if (current.originalText.includes(text)) {
      p.innerHTML = editedRewrite;
      p.setAttribute('data-wizard-hl', 'true');
      replaced = true;
      break;
    }
  }
  
  if (replaced) {
    showReplacementAlert();
  }
  
  _editorWizardIndex++;
  updateWizardUI();
}

function skipWizardStep() {
  _editorWizardIndex++;
  updateWizardUI();
}

function showReplacementAlert() {
  const paper = document.getElementById('editor-textarea');
  const updated = paper.querySelector('[data-wizard-hl="true"]');
  if (updated) {
    updated.style.background = 'rgba(46, 204, 143, 0.2)';
    setTimeout(() => {
      updated.style.background = 'none';
      updated.style.outline = 'none';
      updated.removeAttribute('data-wizard-hl');
    }, 800);
  }
}

function applyAllSuggestions() {
  if (_editorIssues.length === 0) {
    alert('No compliance issues found to apply suggestions.');
    return;
  }
  
  const paper = document.getElementById('editor-textarea');
  const paragraphs = paper.getElementsByTagName('p');
  const listEl = document.getElementById('applied-list');
  listEl.innerHTML = '';
  
  let count = 0;
  
  _editorIssues.forEach(issue => {
    for (let p of paragraphs) {
      const text = (p.innerText || p.textContent).trim();
      if (text.includes(issue.originalText)) {
        p.innerHTML = text.replace(issue.originalText, issue.rewrite);
        
        const logItem = document.createElement('div');
        logItem.className = 'applied-item';
        logItem.innerHTML = `
          <div class="applied-item-top">✓ Applied: ${issue.title}</div>
          <div class="applied-item-desc">Replaced unilateral/risky terms with compliant clause.</div>
        `;
        listEl.appendChild(logItem);
        
        count++;
        break;
      } else if (issue.originalText.includes(text)) {
        p.innerHTML = issue.rewrite;
        
        const logItem = document.createElement('div');
        logItem.className = 'applied-item';
        logItem.innerHTML = `
          <div class="applied-item-top">✓ Applied: ${issue.title}</div>
          <div class="applied-item-desc">Replaced unilateral/risky terms with compliant clause.</div>
        `;
        listEl.appendChild(logItem);
        
        count++;
        break;
      }
    }
  });
  
  alert(`Successfully auto-applied ${count} suggestion(s) to the contract.`);
  _editorIssues = [];
  updateWizardUI();
}

async function saveEditorChanges() {
  if (!_activeContract) return;
  
  const paper = document.getElementById('editor-textarea');
  const paragraphs = Array.from(paper.getElementsByTagName('p')).map(p => p.innerText || p.textContent);
  const newText = paragraphs.join('\n');
  
  try {
    const res = await fetch(`${API_BASE}/api/history/${_activeContract.id}/text`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ contract_text: newText })
    });
    
    if (!res.ok) throw new Error(`Server returned ${res.status}`);
    
    _activeContract.rawText = newText;
    
    const idx = SCAN_HISTORY.findIndex(c => c.id === _activeContract.id);
    if (idx !== -1) {
      SCAN_HISTORY[idx].rawText = newText;
    }
    saveLocalScanHistory();
    
    alert('Changes saved successfully to database!');
  } catch (err) {
    console.error('Save failed:', err);
    alert(`Failed to save changes: ${err.message}`);
  }
}

function exportEditedDoc() {
  if (!_activeContract) return;
  
  const paper = document.getElementById('editor-textarea');
  const paragraphs = Array.from(paper.getElementsByTagName('p')).map(p => p.innerText || p.textContent);
  const docText = paragraphs.join('\n');
  
  exportAsDoc(_activeContract.filename, docText);
}

function exportAsDoc(filename, text) {
  const header = "<html xmlns:o='urn:schemas-microsoft-com:office:office' "+
        "xmlns:w='urn:schemas-microsoft-com:office:word' "+
        "xmlns='http://www.w3.org/TR/REC-html40'>"+
        "<head><title>Export to Word</title><style>body { font-family: 'Times New Roman', serif; line-height: 1.5; padding: 20px; }</style></head><body>";
  const footer = "</body></html>";
  
  const formattedText = text.split('\n').map(p => p.trim() ? `<p>${p}</p>` : '<br>').join('');
  const html = header + formattedText + footer;

  const blob = new Blob(['\\ufeff' + html], {
    type: 'application/msword'
  });
  
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename.replace(/\\.[^/.]+$/, "") + "_edited.doc";
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}


