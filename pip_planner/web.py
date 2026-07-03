from __future__ import annotations

import argparse
import json
from http import HTTPStatus
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from urllib.parse import unquote, urlparse
import uuid

from .genome import GENOME_NONE_ID, list_genomes
from .model import safe_design_name


HTML_PAGE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link rel="icon" href="data:,">
  <title>PIP Planner</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f5f7fa;
      --panel: #ffffff;
      --ink: #172033;
      --muted: #667085;
      --line: #d0d7e2;
      --blue: #225c8f;
      --blue-soft: #eaf2fb;
      --green: #25715f;
      --amber: #7a5a16;
      --amber-soft: #fbf3dd;
      --danger: #9c2f2f;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      background: var(--bg);
      color: var(--ink);
      font-family: Arial, Helvetica, sans-serif;
    }
    .app {
      display: grid;
      grid-template-columns: minmax(300px, 380px) minmax(0, 1fr);
      gap: 0;
      min-height: 100vh;
    }
    aside {
      background: var(--panel);
      border-right: 1px solid var(--line);
      padding: 24px;
    }
    main {
      padding: 24px;
      min-width: 0;
    }
    h1 {
      margin: 0 0 6px;
      font-size: 24px;
      line-height: 1.2;
      letter-spacing: 0;
    }
    .subtle {
      color: var(--muted);
      font-size: 13px;
      line-height: 1.45;
      margin: 0 0 22px;
    }
    label {
      display: block;
      font-size: 13px;
      font-weight: 700;
      margin: 18px 0 8px;
    }
    textarea, select {
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fff;
      color: var(--ink);
      font: inherit;
      min-height: 116px;
      padding: 12px;
    }
    select {
      min-height: 40px;
      padding: 8px 10px;
    }
    textarea:focus, select:focus, button:focus-visible, a:focus-visible {
      outline: 3px solid #9cc8ed;
      outline-offset: 2px;
    }
    .segmented {
      display: grid;
      grid-template-columns: 1fr 1fr;
      border: 1px solid var(--line);
      border-radius: 8px;
      overflow: hidden;
      background: #fff;
    }
    .segmented label {
      margin: 0;
      padding: 10px 12px;
      font-size: 14px;
      font-weight: 700;
      text-align: center;
      cursor: pointer;
      border-right: 1px solid var(--line);
    }
    .segmented label:last-child { border-right: 0; }
    .segmented input { position: absolute; opacity: 0; pointer-events: none; }
    .segmented label:has(input:checked) {
      color: #ffffff;
      background: var(--blue);
    }
    .row {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 12px;
    }
    .summary {
      display: grid;
      grid-template-columns: repeat(4, minmax(150px, 1fr));
      gap: 12px;
      margin-bottom: 18px;
    }
    .metric {
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      padding: 12px;
      min-width: 0;
    }
    .metric span {
      display: block;
      color: var(--muted);
      font-size: 12px;
      margin-bottom: 5px;
    }
    .metric strong {
      display: block;
      overflow-wrap: anywhere;
      font-family: Consolas, 'Liberation Mono', monospace;
      font-size: 14px;
      line-height: 1.35;
      white-space: pre-line;
    }
    .output-panel {
      max-width: 100%;
    }
    .output-heading {
      font-size: 18px;
      line-height: 1.25;
      margin: 0 0 10px;
    }
    .output-summary {
      color: var(--muted);
      font-size: 14px;
      line-height: 1.45;
      margin: 0 0 14px;
    }
    .output-titlebar {
      align-items: center;
      display: flex;
      gap: 10px;
      justify-content: space-between;
      margin: 0 0 10px;
    }
    .output-titlebar .output-heading {
      margin: 0;
    }
    .output-table {
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
      min-width: 680px;
    }
    .output-table th,
    .output-table td {
      border-bottom: 1px solid var(--line);
      padding: 9px 10px;
      text-align: left;
      vertical-align: top;
    }
    .output-table th {
      color: var(--muted);
      font-size: 12px;
      font-weight: 700;
      background: #f8fafc;
    }
    .output-table td.code {
      font-family: Consolas, 'Liberation Mono', monospace;
      white-space: nowrap;
    }
    .output-table td.status-ok {
      color: var(--green);
      font-weight: 700;
    }
    .output-table td.status-error {
      color: var(--danger);
      font-weight: 700;
    }
    .output-table td.status-muted {
      color: var(--muted);
    }
    .toolbar {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      align-items: center;
      margin: 0 0 12px;
    }
    .tab {
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fff;
      color: var(--ink);
      padding: 8px 12px;
      min-height: 36px;
      text-decoration: none;
      font: inherit;
      cursor: pointer;
    }
    .tab[aria-selected="true"] {
      background: var(--blue-soft);
      color: var(--blue);
      border-color: #9fc0ea;
      font-weight: 700;
    }
    .preview {
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      min-height: 520px;
      overflow: auto;
      padding: 18px;
      position: relative;
    }
    .preview svg {
      max-width: 100%;
      height: auto;
      display: block;
    }
    .preview-download {
      align-items: center;
      background: rgba(255, 255, 255, 0.94);
      border: 1px solid var(--line);
      border-radius: 8px;
      color: var(--blue);
      display: inline-flex;
      height: 36px;
      justify-content: center;
      position: absolute;
      right: 12px;
      top: 12px;
      text-decoration: none;
      width: 36px;
      z-index: 2;
    }
    .preview-download:hover {
      background: var(--blue-soft);
      border-color: #9fc0ea;
    }
    .preview-download span {
      font-size: 22px;
      line-height: 1;
      transform: translateY(-1px);
    }
    .model-frame {
      width: 100%;
      min-height: 620px;
      border: 0;
      display: block;
      background: #000000;
    }
    .message {
      border-radius: 8px;
      padding: 10px 12px;
      font-size: 13px;
      line-height: 1.45;
      margin: 12px 0 0;
      display: none;
    }
    .message.is-visible { display: block; }
    .message.warn {
      background: var(--amber-soft);
      color: var(--amber);
      border: 1px solid #e7cd87;
    }
    .message.error {
      background: #fce8e8;
      color: var(--danger);
      border: 1px solid #efb3b3;
    }
    .genome-actions {
      border: 1px solid var(--line);
      border-radius: 8px;
      margin-top: 8px;
      overflow: hidden;
    }
    .genome-item {
      align-items: center;
      background: #fff;
      border-bottom: 1px solid var(--line);
      display: grid;
      gap: 8px;
      grid-template-columns: minmax(0, 1fr) auto;
      min-height: 42px;
      padding: 8px 10px;
    }
    .genome-item:last-child { border-bottom: 0; }
    .genome-name {
      font-size: 13px;
      font-weight: 700;
      line-height: 1.25;
      overflow-wrap: anywhere;
    }
    .genome-meta {
      color: var(--muted);
      display: block;
      font-size: 11px;
      font-weight: 400;
      margin-top: 2px;
    }
    .genome-button {
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fff;
      color: var(--blue);
      cursor: pointer;
      font: inherit;
      font-size: 12px;
      font-weight: 700;
      min-height: 30px;
      padding: 5px 9px;
      white-space: nowrap;
    }
    .genome-button:hover { background: var(--blue-soft); border-color: #9fc0ea; }
    .genome-button:disabled {
      color: var(--muted);
      cursor: default;
      background: #f8fafc;
    }
    .genome-status {
      color: var(--muted);
      font-size: 12px;
      line-height: 1.35;
      margin-top: 8px;
      min-height: 16px;
    }
    .genome-settings {
      max-width: 760px;
    }
    .genome-settings select {
      margin-bottom: 12px;
    }
    .files {
      margin-top: 14px;
      color: var(--muted);
      font-size: 12px;
      overflow-wrap: anywhere;
    }
    .empty {
      color: var(--muted);
      font-size: 14px;
      padding: 28px;
      text-align: center;
    }
    .loading {
      align-items: center;
      display: flex;
      flex-direction: column;
      justify-content: center;
      min-height: var(--loading-min-height, 240px);
      gap: 12px;
      color: var(--muted);
      font-size: 13px;
    }
    .spinner {
      width: 24px;
      height: 24px;
      border: 3px solid #d7dee8;
      border-top-color: var(--blue);
      border-radius: 50%;
      animation: spin 0.8s linear infinite;
    }
    .metric-spinner {
      display: inline-block;
      width: 15px;
      height: 15px;
      border: 2px solid #d7dee8;
      border-top-color: var(--blue);
      border-radius: 50%;
      vertical-align: -2px;
      animation: spin 0.8s linear infinite;
    }
    @keyframes spin { to { transform: rotate(360deg); } }
    @media (max-width: 880px) {
      .app { grid-template-columns: 1fr; }
      aside { border-right: 0; border-bottom: 1px solid var(--line); }
      main { padding: 18px; }
      .summary { grid-template-columns: 1fr 1fr; }
    }
    @media (max-width: 540px) {
      aside { padding: 18px; }
      .row, .summary { grid-template-columns: 1fr; }
      .toolbar { align-items: stretch; }
      .tab { width: 100%; text-align: center; }
    }
  </style>
</head>
<body>
  <div class="app">
    <aside>
      <h1>PIP Planner</h1>
      <p class="subtle">Enter a 5' to 3' DNA target strand. The UI sends the request to the local CLI and displays the generated files.</p>

      <form id="design-form">
        <label for="sequence">DNA sequence</label>
        <textarea id="sequence" name="sequence" spellcheck="false" autocomplete="off" autocapitalize="characters" autocorrect="off">GTAC</textarea>

        <label>Architecture</label>
        <div class="segmented" role="radiogroup" aria-label="Polyamide architecture">
          <label><input type="radio" name="architecture" value="hairpin" checked>Hairpin</label>
          <label><input type="radio" name="architecture" value="linear">Linear</label>
        </div>

        <label for="at-mode">A/T recognition</label>
        <select id="at-mode" name="at_mode">
          <option value="distinguish">Distinguish A-T and T-A with Hp</option>
          <option value="py-py">Treat A/T as Py/Py</option>
        </select>

        <div class="row">
          <div>
            <label for="tail">Terminal group</label>
            <select id="tail" name="tail">
              <option value="dp">Dp</option>
              <option value="none">None</option>
            </select>
          </div>
          <div>
            <label for="turn">Hairpin turn</label>
            <select id="turn" name="turn">
              <option value="gamma">Gamma</option>
              <option value="beta">Beta</option>
              <option value="none">None</option>
            </select>
          </div>
        </div>

        <input id="genome" name="genome" type="hidden" value="sacCer3">
        <input id="genome-file" type="file" accept=".fa,.fasta,.fna,.gz" hidden>
      </form>

      <div class="message warn" id="warnings"></div>
      <div class="message error" id="errors"></div>
    </aside>

    <main>
      <section class="summary" aria-label="Design summary">
        <div class="metric"><span>Target</span><strong id="metric-target">-</strong></div>
        <div class="metric"><span>Complement</span><strong id="metric-complement">-</strong></div>
        <div class="metric"><span>Pairs</span><strong id="metric-pairs">-</strong></div>
        <div class="metric"><span>Chain</span><strong id="metric-chain">-</strong></div>
      </section>

      <div class="toolbar">
        <button class="tab" type="button" data-view="schematic" aria-selected="true">Schematic</button>
        <button class="tab" type="button" data-view="chemical" aria-selected="false">Chemical structure</button>
        <button class="tab" type="button" data-view="solubility" aria-selected="false">Solubility</button>
        <button class="tab" type="button" data-view="genome" aria-selected="false">Genome search</button>
        <button class="tab" type="button" data-view="model" aria-selected="false">3D model</button>
      </div>

      <section class="preview" id="preview" aria-live="polite">
        <div class="empty">No design has been generated yet.</div>
      </section>
      <div class="files" id="files"></div>
    </main>
  </div>

  <script>
    const form = document.querySelector('#design-form');
    const sequenceInput = document.querySelector('#sequence');
    const summary = document.querySelector('.summary');
    const preview = document.querySelector('#preview');
    const files = document.querySelector('#files');
    const warnings = document.querySelector('#warnings');
    const errors = document.querySelector('#errors');
    const tabs = [...document.querySelectorAll('.tab')];
    const genomeInput = document.querySelector('#genome');
    const genomeFileInput = document.querySelector('#genome-file');
    let currentResult = null;
    let currentView = 'schematic';
    let designTimer = null;
    let layoutLockFrame = null;
    let loadingRevealTimer = null;
    let pendingLoadingVisible = false;
    let previousResult = null;
    let activeDesignRequest = 0;
    let lastQueuedPayload = '';
    let genomeCatalog = [];
    let genomeBusy = false;
    let genomeSettingsVisible = false;
    let genomeStatusMessage = '';
    let genomeStatusIsError = false;
    const productOrder = ['schematic', 'chemical', 'solubility', 'genome', 'model'];
    const loadingRevealDelayMs = 250;

    function payloadFromForm() {
      const data = new FormData(form);
      return {
        sequence: data.get('sequence'),
        architecture: data.get('architecture'),
        at_mode: data.get('at_mode'),
        tail: data.get('tail'),
        turn: data.get('turn'),
        genome: data.get('genome')
      };
    }

    function sanitizeDnaSequence(rawValue) {
      return rawValue.toUpperCase().replace(/[^AGTC]/g, '');
    }

    function sanitizeSequenceInput() {
      const rawValue = sequenceInput.value;
      const selectionStart = sequenceInput.selectionStart ?? rawValue.length;
      const sanitizedValue = sanitizeDnaSequence(rawValue);
      if (sanitizedValue === rawValue) return;

      const sanitizedPrefix = sanitizeDnaSequence(rawValue.slice(0, selectionStart));
      sequenceInput.value = sanitizedValue;
      sequenceInput.setSelectionRange(sanitizedPrefix.length, sanitizedPrefix.length);
    }

    function showMessage(element, text) {
      element.textContent = text || '';
      element.classList.toggle('is-visible', Boolean(text));
    }

    function loadingMarkup(label = 'Loading') {
      return '<div class="loading"><div class="spinner"></div><div>' + escapeHtml(label) + '</div></div>';
    }

    function metricLoadingMarkup() {
      return '<span class="metric-spinner" aria-label="Loading"></span>';
    }

    function setMetric(selector, value) {
      document.querySelector(selector).textContent = value;
    }

    function setMetricLoading(selector) {
      document.querySelector(selector).innerHTML = metricLoadingMarkup();
    }

    function formatGenomeOccurrences(genomeResult) {
      if (!genomeResult || genomeResult.status === 'skipped') return 'Genome search unavailable';
      if (genomeResult.status === 'missing_reference') return 'Reference missing';
      if (genomeResult.status !== 'ok') return genomeResult.status || 'Unavailable';
      const count = Number(genomeResult.total_occurrences);
      const label = genomeResult.genome_label || genomeResult.genome_id || 'Genome';
      return Number.isFinite(count) ? count.toLocaleString() + ' in ' + label : label;
    }

    function productForView(view = currentView) {
      return productOrder.includes(view) ? view : 'schematic';
    }

    function isProductSettled(result, product) {
      const status = result?.productStatus?.[product];
      return status === 'done' || status === 'error';
    }

    function hasPendingProducts(result) {
      return productOrder.some(product => !isProductSettled(result, product));
    }

    function clearLoadingRevealTimer() {
      if (loadingRevealTimer) {
        window.clearTimeout(loadingRevealTimer);
        loadingRevealTimer = null;
      }
    }

    function scheduleLoadingReveal(requestId) {
      clearLoadingRevealTimer();
      pendingLoadingVisible = false;
      loadingRevealTimer = window.setTimeout(() => {
        loadingRevealTimer = null;
        if (requestId !== activeDesignRequest || !currentResult || !hasPendingProducts(currentResult)) return;
        pendingLoadingVisible = true;
        if (!isProductSettled(currentResult, productForView())) {
          preserveOutputLayoutForLoading();
        }
        renderState();
      }, loadingRevealDelayMs);
    }

    function settleLoadingRevealIfComplete() {
      if (!currentResult || hasPendingProducts(currentResult)) return;
      clearLoadingRevealTimer();
      pendingLoadingVisible = false;
      previousResult = null;
    }

    function lockElementHeight(element) {
      const height = Math.ceil(element.getBoundingClientRect().height);
      if (height <= 0) return;
      element.style.minHeight = height + 'px';
      element.dataset.layoutLocked = 'true';
    }

    function preserveOutputLayoutForLoading() {
      if (!currentResult || preview.querySelector('.loading')) return;
      clearOutputLayoutLock();
      lockElementHeight(summary);
      lockElementHeight(preview);
      lockElementHeight(files);

      const previewHeight = Math.ceil(preview.getBoundingClientRect().height);
      const previewStyles = window.getComputedStyle(preview);
      const previewFrameHeight =
        parseFloat(previewStyles.paddingTop) +
        parseFloat(previewStyles.paddingBottom) +
        parseFloat(previewStyles.borderTopWidth) +
        parseFloat(previewStyles.borderBottomWidth);
      const loadingHeight = Math.max(240, Math.ceil(previewHeight - previewFrameHeight));
      preview.style.setProperty('--loading-min-height', loadingHeight + 'px');
    }

    function clearOutputLayoutLock() {
      if (layoutLockFrame) {
        window.cancelAnimationFrame(layoutLockFrame);
        layoutLockFrame = null;
      }
      [summary, preview, files].forEach(element => {
        element.style.minHeight = '';
        delete element.dataset.layoutLocked;
      });
      preview.style.removeProperty('--loading-min-height');
    }

    function releaseOutputLayoutLockAfterPaint() {
      if (!summary.dataset.layoutLocked && !preview.dataset.layoutLocked && !files.dataset.layoutLocked) return;
      if (layoutLockFrame) window.cancelAnimationFrame(layoutLockFrame);
      layoutLockFrame = window.requestAnimationFrame(() => {
        layoutLockFrame = null;
        clearOutputLayoutLock();
      });
    }

    function resetProductState() {
      currentResult = {
        design: null,
        run_id: null,
        generated: {},
        productStatus: {
          schematic: 'loading',
          chemical: 'waiting',
          solubility: 'waiting',
          genome: 'waiting',
          model: 'waiting'
        },
        productErrors: {},
        schematic_svg: '',
        chemical_svg: ''
      };
      showMessage(errors, '');
      renderState();
    }

    function setProductLoading(product) {
      if (!currentResult) return;
      currentResult.productStatus[product] = 'loading';
      delete currentResult.productErrors[product];
      renderState();
    }

    function setProductError(product, error) {
      if (!currentResult) return;
      currentResult.productStatus[product] = 'error';
      currentResult.productErrors[product] = error.message || String(error);
      renderState();
    }

    function mergeProductResult(product, result) {
      if (!currentResult) return;
      const incomingDesign = result.design || {};
      const currentDesign = currentResult.design || {};
      currentResult.design = {
        ...currentDesign,
        ...incomingDesign,
        files: {
          ...(currentDesign.files || {}),
          ...(incomingDesign.files || {})
        }
      };
      currentResult.generated = {
        ...currentResult.generated,
        ...(result.generated || {})
      };
      currentResult.run_id = result.run_id || currentResult.run_id;
      if (result.schematic_svg) currentResult.schematic_svg = result.schematic_svg;
      if (result.chemical_svg) currentResult.chemical_svg = result.chemical_svg;
      currentResult.productStatus[product] = 'done';
      delete currentResult.productErrors[product];
      renderState();
    }

    function escapeHtml(value) {
      return String(value ?? '').replace(/[&<>"']/g, character => ({
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#39;'
      })[character]);
    }

    function genomeStatusLabel(genome) {
      if (genome.available) return genome.bundled ? 'Bundled' : 'Available';
      if (genome.downloadable) return 'Download ' + (genome.size_label || '');
      return 'Missing';
    }

    function setGenomeStatus(text, isError = false) {
      genomeStatusMessage = text || '';
      genomeStatusIsError = Boolean(isError);
      if (currentView === 'genome' && genomeSettingsVisible) renderPreview();
    }

    function renderGenomeActions() {
      return genomeCatalog.map(genome => {
        const button = genome.downloadable
          ? '<button class="genome-button" type="button" data-download-genome="' + escapeHtml(genome.id) + '"' +
            (genomeBusy ? ' disabled' : '') + '>Download</button>'
          : '<button class="genome-button" type="button" disabled>' + escapeHtml(genomeStatusLabel(genome)) + '</button>';
        const size = genome.size_label ? ' - ' + genome.size_label : '';
        return '<div class="genome-item">' +
          '<span class="genome-name">' + escapeHtml(genome.label) +
          '<span class="genome-meta">' + escapeHtml(genomeStatusLabel(genome) + size) + '</span></span>' +
          button +
          '</div>';
      }).join('');
    }

    function availableGenomeOptions() {
      return genomeCatalog.filter(genome => genome.available);
    }

    function defaultGenomeId() {
      const available = availableGenomeOptions();
      if (available.some(genome => genome.id === 'sacCer3')) return 'sacCer3';
      return available.length ? available[0].id : 'sacCer3';
    }

    async function loadGenomes(selectGenomeId = '') {
      try {
        const response = await fetch('/api/genomes');
        if (!response.ok) return;
        const payload = await response.json();
        if (!Array.isArray(payload.genomes)) return;
        genomeCatalog = payload.genomes;
        const selected = selectGenomeId || genomeInput.value || defaultGenomeId();
        const available = availableGenomeOptions();
        genomeInput.value = available.some(genome => genome.id === selected) ? selected : defaultGenomeId();
        if (currentView === 'genome') renderPreview();
      } catch (error) {
        return;
      }
    }

    async function downloadGenome(genomeId) {
      if (!genomeId || genomeBusy) return;
      genomeBusy = true;
      renderPreview();
      setGenomeStatus('Downloading ' + genomeId + '...');
      try {
        const response = await fetch('/api/genomes/download', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ genome: genomeId })
        });
        const result = await response.json();
        if (!response.ok) throw new Error(result.error || 'Genome download failed.');
        const downloadedId = result.genome && result.genome.id ? result.genome.id : genomeId;
        await loadGenomes(downloadedId);
        setGenomeStatus(result.message || 'Genome downloaded.');
        scheduleDesign(0);
      } catch (error) {
        setGenomeStatus(error.message || String(error), true);
      } finally {
        genomeBusy = false;
        renderPreview();
      }
    }

    async function importGenomeFile(file) {
      if (!file || genomeBusy) return;
      genomeBusy = true;
      renderPreview();
      setGenomeStatus('Importing ' + file.name + '...');
      try {
        const response = await fetch('/api/genomes/import', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/octet-stream',
            'X-Genome-Filename': encodeURIComponent(file.name)
          },
          body: file
        });
        const result = await response.json();
        if (!response.ok) throw new Error(result.error || 'Genome import failed.');
        const genomeId = result.genome && result.genome.id ? result.genome.id : '';
        await loadGenomes(genomeId);
        setGenomeStatus(result.message || 'Genome imported.');
        scheduleDesign(0);
      } catch (error) {
        setGenomeStatus(error.message || String(error), true);
      } finally {
        genomeBusy = false;
        genomeFileInput.value = '';
        renderPreview();
      }
    }

    function renderState() {
      if (!currentResult) return;
      const design = currentResult.design || (!pendingLoadingVisible && previousResult ? previousResult.design : {}) || {};
      if (design.sequence_label) {
        setMetric('#metric-target', design.sequence_label);
        setMetric('#metric-complement', design.complement_label);
        setMetric('#metric-pairs', Array.isArray(design.recognition_pairs) ? design.recognition_pairs.join(' ') : '-');
        setMetric('#metric-chain', design.chain_code || '-');
      } else {
        setMetricLoading('#metric-target');
        setMetricLoading('#metric-complement');
        setMetricLoading('#metric-pairs');
        setMetricLoading('#metric-chain');
      }

      showMessage(warnings, Array.isArray(design.warnings) ? design.warnings.join(' ') : '');
      renderFilesText(design);
      renderPreview();
      settleLoadingRevealIfComplete();
    }

    function renderFilesText(design) {
      const designFiles = design.files || {};
      const pieces = [];
      if (design.chemical_renderer) pieces.push('Generated with ' + design.chemical_renderer);
      if (design.chemical_smiles) pieces.push('SMILES: ' + design.chemical_smiles);
      ['chemical_svg', 'schematic_svg', 'complex_pdb'].forEach(key => {
        if (designFiles[key]) pieces.push(designFiles[key]);
      });
      files.textContent = pieces.join(' | ');
    }

    function renderPreview() {
      if (!currentResult) return;
      preview.innerHTML = renderView(currentResult);
      tabs.forEach(tab => {
        tab.setAttribute('aria-selected', String(tab.dataset.view === currentView));
      });
      if (!preview.querySelector('.loading')) {
        releaseOutputLayoutLockAfterPaint();
      }
    }

    function renderView(result, allowPendingFallback = true) {
      if (!result) return '<div class="empty">No design has been generated yet.</div>';
      const download = renderPreviewDownload(result);
      if (currentView === 'chemical') {
        return renderProductPreview(result, 'chemical', result.chemical_svg, 'Chemical structure', allowPendingFallback) + download;
      } else if (currentView === 'schematic') {
        return renderProductPreview(result, 'schematic', result.schematic_svg, 'Schematic', allowPendingFallback) + download;
      } else if (currentView === 'solubility') {
        return renderSolubilityPreview(result, allowPendingFallback);
      } else if (currentView === 'genome') {
        return renderGenomePreview(result, allowPendingFallback);
      } else if (currentView === 'model') {
        return renderModelPreview(result, allowPendingFallback) + download;
      }
      return '<div class="empty">Unknown output.</div>';
    }

    function renderPreviewDownload(result = currentResult) {
      const downloads = {
        chemical: {
          href: result.generated.chemical_svg_url,
          name: result.generated.chemical_svg_name,
          label: 'Download chemical SVG'
        },
        schematic: {
          href: result.generated.schematic_svg_url,
          name: result.generated.schematic_svg_name,
          label: 'Download schematic SVG'
        },
        model: {
          href: result.generated.complex_pdb_url,
          name: result.generated.complex_pdb_name,
          label: 'Download PDB'
        }
      };
      const download = downloads[currentView];
      if (!download || !download.href) return '';
      return '<a class="preview-download" href="' + escapeHtml(download.href) + '" download="' +
        escapeHtml(download.name || '') + '" aria-label="' + escapeHtml(download.label) +
        '" title="' + escapeHtml(download.label) + '"><span aria-hidden="true">&#8595;</span></a>';
    }

    function renderPendingPreview(label, allowPendingFallback) {
      if (allowPendingFallback && !pendingLoadingVisible) {
        return previousResult ? renderView(previousResult, false) : '<div class="empty">No design has been generated yet.</div>';
      }
      return loadingMarkup(label);
    }

    function renderProductPreview(result, product, markup, label, allowPendingFallback = true) {
      const status = result.productStatus[product];
      if (status === 'done' && markup) return markup;
      if (status === 'error') return '<div class="empty">' + escapeHtml(result.productErrors[product] || label + ' failed.') + '</div>';
      return renderPendingPreview(label, allowPendingFallback);
    }

    function renderStructuredProductPreview(result, product, label, renderer, allowPendingFallback = true) {
      const status = result.productStatus[product];
      if (status === 'done') return renderer(result);
      if (status === 'error') return '<div class="empty">' + escapeHtml(result.productErrors[product] || label + ' failed.') + '</div>';
      return renderPendingPreview(label, allowPendingFallback);
    }

    function renderSolubilityPreview(result = currentResult, allowPendingFallback = true) {
      return renderStructuredProductPreview(result, 'solubility', 'Solubility predictions', renderResult => {
        const predictions = (renderResult.design || {}).solubility_predictions;
        if (!Array.isArray(predictions) || predictions.length === 0) {
          return '<div class="empty">No solubility predictions are available.</div>';
        }

        const rows = predictions.map(prediction => {
          const method = prediction.method || 'Unknown predictor';
          const status = prediction.status || 'unknown';
          const numericValue = Number(prediction.value);
          const value = status === 'ok' && Number.isFinite(numericValue) ? numericValue.toPrecision(3) : '-';
          const detailParts = [];
          if (prediction.unit) detailParts.push(prediction.unit);
          if (prediction.property_name) detailParts.push(prediction.property_name);
          const detail = detailParts.length ? detailParts.join(' / ') : '-';
          const message = prediction.message || '-';
          return '<tr>' +
            '<td>' + escapeHtml(method) + '</td>' +
            '<td class="' + statusClass(status) + '">' + escapeHtml(status) + '</td>' +
            '<td class="code">' + escapeHtml(value) + '</td>' +
            '<td>' + escapeHtml(detail) + '</td>' +
            '<td>' + escapeHtml(message) + '</td>' +
            '</tr>';
        }).join('');

        return '<div class="output-panel">' +
          '<h2 class="output-heading">Solubility predictions</h2>' +
          '<table class="output-table solubility-table">' +
          '<thead><tr><th>Method</th><th>Status</th><th>Value</th><th>Unit / property</th><th>Message</th></tr></thead>' +
          '<tbody>' + rows + '</tbody>' +
          '</table>' +
          '</div>';
      }, allowPendingFallback);
    }

    function renderGenomeTitlebar(settingsVisible) {
      return '<div class="output-titlebar">' +
        '<h2 class="output-heading">Genome search</h2>' +
        '<button class="genome-button" type="button" data-genome-settings-toggle>' +
        (settingsVisible ? 'Results' : '&#9881; Settings') +
        '</button>' +
        '</div>';
    }

    function renderGenomeSettings() {
      const available = availableGenomeOptions();
      const selected = available.some(genome => genome.id === genomeInput.value) ? genomeInput.value : defaultGenomeId();
      const options = available.map(genome => {
        return '<option value="' + escapeHtml(genome.id) + '"' +
          (genome.id === selected ? ' selected' : '') + '>' +
          escapeHtml(genome.label) +
          '</option>';
      }).join('');
      const statusStyle = genomeStatusIsError ? ' style="color: var(--danger);"' : '';
      return '<div class="output-panel genome-settings">' +
        renderGenomeTitlebar(true) +
        '<label for="genome-select">Genome</label>' +
        '<select id="genome-select">' + options + '</select>' +
        '<div class="genome-actions">' + renderGenomeActions() + '</div>' +
        '<button class="genome-button" id="genome-import" type="button">Other...</button>' +
        '<div class="genome-status" aria-live="polite"' + statusStyle + '>' +
        escapeHtml(genomeStatusMessage) +
        '</div>' +
        '</div>';
    }

    function renderGenomeResult(genomeResult) {
      const heading = renderGenomeTitlebar(false);
      if (!genomeResult || genomeResult.status === 'skipped') {
        return '<div class="output-panel">' + heading + '<div class="empty">Genome search is waiting for a reference.</div></div>';
      }

      if (genomeResult.status !== 'ok') {
        return '<div class="output-panel">' + heading + '<div class="empty">' +
          escapeHtml(genomeResult.message || 'Genome search is unavailable.') +
          '</div></div>';
      }

      const summary = '<p class="output-summary">' + escapeHtml(formatGenomeOccurrences(genomeResult)) + '</p>';
      const locations = Array.isArray(genomeResult.locations) ? genomeResult.locations : [];
      if (!genomeResult.locations_listed || locations.length === 0) {
        return '<div class="output-panel">' + heading + summary + '<div class="empty">' +
          escapeHtml(genomeResult.message || 'No locations are listed.') +
          '</div></div>';
      }

      const rows = locations.map(location => {
        return '<tr>' +
          '<td class="code">' + escapeHtml(location.contig) + '</td>' +
          '<td class="code">' + escapeHtml(location.start) + '</td>' +
          '<td class="code">' + escapeHtml(location.end) + '</td>' +
          '<td class="code">' + escapeHtml(location.strand) + '</td>' +
          '<td>' + escapeHtml(location.feature_summary || 'No annotation') + '</td>' +
          '</tr>';
      }).join('');

      return '<div class="output-panel">' +
        heading +
        summary +
        '<table class="output-table genome-table">' +
        '<thead><tr><th>Contig</th><th>Start</th><th>End</th><th>Strand</th><th>Overlapping annotation</th></tr></thead>' +
        '<tbody>' + rows + '</tbody>' +
        '</table>' +
        '</div>';
    }

    function renderGenomePreview(result = currentResult, allowPendingFallback = true) {
      if (genomeSettingsVisible) return renderGenomeSettings();
      const status = result.productStatus.genome;
      if (status === 'done') return renderGenomeResult((result.design || {}).genome_occurrences);
      if (status === 'error') {
        return '<div class="output-panel">' + renderGenomeTitlebar(false) +
          '<div class="empty">' + escapeHtml(result.productErrors.genome || 'Genome search failed.') + '</div></div>';
      }
      return renderPendingPreview('Genome search', allowPendingFallback);
    }

    function renderModelPreview(result = currentResult, allowPendingFallback = true) {
      if (result.productStatus.model === 'done' && result.generated.model_html_url) {
        return '<iframe class="model-frame" title="3D DNA polyamide model" src="' +
          escapeHtml(result.generated.model_html_url) + '"></iframe>';
      }
      if (result.productStatus.model === 'error') {
        return '<div class="empty">' + escapeHtml(result.productErrors.model || 'The 3D model failed.') + '</div>';
      }
      return renderPendingPreview('Building 3D model', allowPendingFallback);
    }

    function statusClass(status) {
      if (status === 'ok') return 'status-ok';
      if (status === 'error' || status === 'failed') return 'status-error';
      return 'status-muted';
    }

    function scheduleDesign(delay = 250) {
      const payloadKey = JSON.stringify(payloadFromForm());
      if (payloadKey === lastQueuedPayload) return;
      lastQueuedPayload = payloadKey;
      const requestId = activeDesignRequest + 1;
      activeDesignRequest = requestId;
      window.clearTimeout(designTimer);
      designTimer = window.setTimeout(() => design(null, requestId), delay);
    }

    async function requestProduct(product, payload, runId) {
      const response = await fetch('/api/design/product', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...payload, product, run_id: runId || '' })
      });
      const result = await response.json();
      if (!response.ok) {
        throw new Error(result.error || product + ' generation failed.');
      }
      return result;
    }

    async function runProduct(product, payload, runId, requestId) {
      setProductLoading(product);
      try {
        const result = await requestProduct(product, payload, runId);
        if (requestId !== activeDesignRequest) return null;
        mergeProductResult(product, result);
        return result;
      } catch (error) {
        if (requestId === activeDesignRequest) setProductError(product, error);
        return null;
      }
    }

    async function design(event, queuedRequestId = null) {
      if (event) event.preventDefault();
      window.clearTimeout(designTimer);
      const requestId = queuedRequestId || activeDesignRequest + 1;
      activeDesignRequest = requestId;
      const payload = payloadFromForm();
      previousResult = currentResult;
      scheduleLoadingReveal(requestId);
      resetProductState();
      showMessage(errors, '');
      try {
        const schematic = await requestProduct('schematic', payload, null);
        if (requestId !== activeDesignRequest) return;
        mergeProductResult('schematic', schematic);
        const runId = schematic.run_id;

        await runProduct('chemical', payload, runId, requestId);
        if (requestId !== activeDesignRequest) return;

        await Promise.all(productOrder
          .filter(product => !['schematic', 'chemical'].includes(product))
          .map(product => runProduct(product, payload, runId, requestId)));
      } catch (error) {
        if (requestId !== activeDesignRequest) return;
        productOrder.forEach(product => {
          if (currentResult.productStatus[product] !== 'done') {
            currentResult.productStatus[product] = 'error';
            currentResult.productErrors[product] = error.message;
          }
        });
        renderState();
        showMessage(errors, error.message);
      }
    }

    tabs.forEach(tab => {
      tab.addEventListener('click', () => {
        clearOutputLayoutLock();
        currentView = tab.dataset.view;
        renderPreview();
      });
    });
    window.addEventListener('resize', clearOutputLayoutLock);
    sequenceInput.addEventListener('input', sanitizeSequenceInput);
    form.addEventListener('submit', design);
    form.addEventListener('input', () => scheduleDesign());
    form.addEventListener('change', () => scheduleDesign(0));
    preview.addEventListener('click', event => {
      const settingsToggle = event.target.closest('[data-genome-settings-toggle]');
      if (settingsToggle) {
        event.preventDefault();
        genomeSettingsVisible = !genomeSettingsVisible;
        renderPreview();
        return;
      }

      const button = event.target.closest('[data-download-genome]');
      if (button) {
        event.preventDefault();
        downloadGenome(button.dataset.downloadGenome);
        return;
      }

      const importButton = event.target.closest('#genome-import');
      if (importButton) {
        event.preventDefault();
        genomeFileInput.click();
      }
    });
    preview.addEventListener('change', event => {
      const select = event.target.closest('#genome-select');
      if (!select) return;
      genomeInput.value = select.value;
      genomeSettingsVisible = false;
      scheduleDesign(0);
      renderPreview();
    });
    genomeFileInput.addEventListener('change', event => {
      event.stopPropagation();
      const file = genomeFileInput.files && genomeFileInput.files[0];
      if (file) importGenomeFile(file);
    });
    loadGenomes();
    design();
  </script>
</body>
</html>
"""


class PlannerRequestHandler(BaseHTTPRequestHandler):
    output_root: Path
    project_root: Path

    server_version = "PIPPlannerHTTP/0.1"

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self._send_text(HTTPStatus.OK, HTML_PAGE, "text/html; charset=utf-8")
            return

        if parsed.path == "/favicon.ico":
            self._send_bytes(HTTPStatus.NO_CONTENT, b"", "image/x-icon")
            return

        if parsed.path == "/api/genomes":
            self._send_json(HTTPStatus.OK, {"genomes": list_genomes()})
            return

        if parsed.path.startswith("/generated/"):
            self._serve_generated(parsed.path)
            return

        self._send_json(HTTPStatus.NOT_FOUND, {"error": "Not found."})

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/genomes/download":
            try:
                payload = self._read_json()
                result = self._run_cli_genome_download(payload)
            except ValueError as exc:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return
            except RuntimeError as exc:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return
            self._send_json(HTTPStatus.OK, result)
            return

        if parsed.path == "/api/genomes/import":
            try:
                result = self._run_cli_genome_import()
            except ValueError as exc:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return
            except RuntimeError as exc:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return
            self._send_json(HTTPStatus.OK, result)
            return

        if parsed.path not in {"/api/design", "/api/design/product"}:
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "Not found."})
            return

        try:
            payload = self._read_json()
            result = self._run_cli_product(payload) if parsed.path == "/api/design/product" else self._run_cli_design(payload)
        except ValueError as exc:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return
        except RuntimeError as exc:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return

        self._send_json(HTTPStatus.OK, result)

    def log_message(self, format: str, *args: object) -> None:
        # Keep test and CLI output quiet unless a caller wraps the server logs.
        return

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            raise ValueError("Request body is required.")
        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON request: {exc.msg}.") from exc
        if not isinstance(payload, dict):
            raise ValueError("Request JSON must be an object.")
        return payload

    def _run_cli_design(self, payload: dict) -> dict:
        sequence = str(payload.get("sequence", "")).strip()
        if not sequence:
            raise ValueError("DNA sequence is required.")

        architecture = _choice(payload, "architecture", {"hairpin", "linear"}, "hairpin")
        at_mode = _choice(payload, "at_mode", {"distinguish", "py-py"}, "distinguish")
        tail = _choice(payload, "tail", {"dp", "none"}, "dp")
        turn = _choice(payload, "turn", {"gamma", "beta", "none"}, "gamma")
        genome_ids = {GENOME_NONE_ID, *(str(genome["id"]) for genome in list_genomes())}
        genome = _choice(payload, "genome", genome_ids, GENOME_NONE_ID)

        safe_name = safe_design_name(sequence, architecture)
        run_id = f"{int(time.time())}-{uuid.uuid4().hex[:8]}-{safe_name}"
        run_dir = (self.output_root / run_id).resolve()
        run_dir.mkdir(parents=True, exist_ok=True)

        command = [
            *_cli_command_prefix(),
            "design",
            sequence,
            "--architecture",
            architecture,
            "--at-mode",
            at_mode,
            "--tail",
            tail,
            "--turn",
            turn,
            "--genome",
            genome,
            "--out",
            str(run_dir),
            "--name",
            safe_name,
            "--format",
            "json",
        ]

        completed = subprocess.run(
            command,
            cwd=str(self.project_root),
            text=True,
            capture_output=True,
            timeout=180,
        )
        if completed.returncode != 0:
            error = completed.stderr.strip() or completed.stdout.strip() or "CLI command failed."
            raise RuntimeError(error)

        try:
            cli_payload = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"CLI returned invalid JSON: {exc.msg}.") from exc

        files = cli_payload.get("files", {})
        chemical_path = Path(files["chemical_svg"]).resolve()
        schematic_path = Path(files["schematic_svg"]).resolve()
        model_html_path = Path(files["model_html"]).resolve()
        complex_pdb_path = Path(files["complex_pdb"]).resolve()
        _assert_within(chemical_path, self.output_root)
        _assert_within(schematic_path, self.output_root)
        _assert_within(model_html_path, self.output_root)
        _assert_within(complex_pdb_path, self.output_root)

        return {
            "design": cli_payload,
            "chemical_svg": chemical_path.read_text(encoding="utf-8"),
            "schematic_svg": schematic_path.read_text(encoding="utf-8"),
            "generated": {
                "run_id": run_id,
                "chemical_svg_url": f"/generated/{run_id}/{chemical_path.name}",
                "schematic_svg_url": f"/generated/{run_id}/{schematic_path.name}",
                "model_html_url": f"/generated/{run_id}/{model_html_path.name}",
                "complex_pdb_url": f"/generated/{run_id}/{complex_pdb_path.name}",
                "chemical_svg_name": chemical_path.name,
                "schematic_svg_name": schematic_path.name,
                "complex_pdb_name": complex_pdb_path.name,
            },
            "invoked_command": command,
        }

    def _run_cli_product(self, payload: dict) -> dict:
        sequence = str(payload.get("sequence", "")).strip()
        if not sequence:
            raise ValueError("DNA sequence is required.")

        product = _choice(
            payload,
            "product",
            {"schematic", "chemical", "solubility", "genome", "model"},
            "schematic",
        )
        architecture = _choice(payload, "architecture", {"hairpin", "linear"}, "hairpin")
        at_mode = _choice(payload, "at_mode", {"distinguish", "py-py"}, "distinguish")
        tail = _choice(payload, "tail", {"dp", "none"}, "dp")
        turn = _choice(payload, "turn", {"gamma", "beta", "none"}, "gamma")
        genome_ids = {GENOME_NONE_ID, *(str(genome["id"]) for genome in list_genomes())}
        genome = _choice(payload, "genome", genome_ids, GENOME_NONE_ID)

        safe_name = safe_design_name(sequence, architecture)
        run_id = _run_id_from_payload(payload, safe_name)
        run_dir = (self.output_root / run_id).resolve()
        _assert_within(run_dir, self.output_root)
        run_dir.mkdir(parents=True, exist_ok=True)

        command = [
            *_cli_command_prefix(),
            "design",
            sequence,
            "--architecture",
            architecture,
            "--at-mode",
            at_mode,
            "--tail",
            tail,
            "--turn",
            turn,
            "--genome",
            genome,
            "--product",
            product,
            "--out",
            str(run_dir),
            "--name",
            safe_name,
            "--format",
            "json",
        ]

        completed = subprocess.run(
            command,
            cwd=str(self.project_root),
            text=True,
            capture_output=True,
            timeout=_product_timeout(product),
        )
        if completed.returncode != 0:
            error = completed.stderr.strip() or completed.stdout.strip() or "CLI command failed."
            raise RuntimeError(error)

        try:
            cli_payload = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"CLI returned invalid JSON: {exc.msg}.") from exc

        result = {
            "product": product,
            "run_id": run_id,
            "design": cli_payload,
            "generated": {"run_id": run_id},
            "invoked_command": command,
        }

        file_paths = _collect_generated_file_paths(cli_payload, self.output_root)
        for key, path in file_paths.items():
            result["generated"][f"{key}_url"] = f"/generated/{run_id}/{path.name}"
            result["generated"][f"{key}_name"] = path.name

        if "schematic_svg" in file_paths:
            result["schematic_svg"] = file_paths["schematic_svg"].read_text(encoding="utf-8")
        if "chemical_svg" in file_paths:
            result["chemical_svg"] = file_paths["chemical_svg"].read_text(encoding="utf-8")

        return result

    def _run_cli_genome_download(self, payload: dict) -> dict:
        genome = str(payload.get("genome", "")).strip()
        if not genome:
            raise ValueError("Genome id is required.")
        return self._run_cli_json(["genomes", "download", genome, "--format", "json"], timeout=7200)

    def _run_cli_genome_import(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            raise ValueError("Genome FASTA upload is required.")

        raw_filename = unquote(self.headers.get("X-Genome-Filename", "genome.fa"))
        filename = Path(raw_filename).name or "genome.fa"
        if not filename.lower().endswith((".fa", ".fasta", ".fna", ".fa.gz", ".fasta.gz", ".fna.gz")):
            raise ValueError("Genome file must be .fa, .fasta, .fna, or a gzipped version of one of those formats.")

        with tempfile.TemporaryDirectory() as tmp:
            upload_path = Path(tmp) / filename
            remaining = length
            with upload_path.open("wb") as target:
                while remaining > 0:
                    chunk = self.rfile.read(min(1024 * 1024, remaining))
                    if not chunk:
                        raise ValueError("Genome FASTA upload ended early.")
                    target.write(chunk)
                    remaining -= len(chunk)
            return self._run_cli_json(
                ["genomes", "import", str(upload_path), "--format", "json"],
                timeout=600,
            )

    def _run_cli_json(self, args: list[str], timeout: int) -> dict:
        command = [*_cli_command_prefix(), *args]
        completed = subprocess.run(
            command,
            cwd=str(self.project_root),
            text=True,
            capture_output=True,
            timeout=timeout,
        )
        if completed.returncode != 0:
            error = completed.stderr.strip() or completed.stdout.strip() or "CLI command failed."
            raise RuntimeError(error)
        try:
            payload = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"CLI returned invalid JSON: {exc.msg}.") from exc
        if not isinstance(payload, dict):
            raise RuntimeError("CLI returned an invalid JSON payload.")
        return payload

    def _serve_generated(self, path: str) -> None:
        relative = unquote(path.removeprefix("/generated/"))
        if "/" not in relative:
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "Generated file not found."})
            return

        candidate = (self.output_root / relative).resolve()
        try:
            _assert_within(candidate, self.output_root)
        except ValueError:
            self._send_json(HTTPStatus.FORBIDDEN, {"error": "Generated file path is not allowed."})
            return

        allowed_suffixes = {".svg", ".json", ".html", ".pdb", ".md"}
        if not candidate.exists() or candidate.suffix not in allowed_suffixes:
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "Generated file not found."})
            return

        content_types = {
            ".svg": "image/svg+xml; charset=utf-8",
            ".json": "application/json; charset=utf-8",
            ".html": "text/html; charset=utf-8",
            ".pdb": "chemical/x-pdb; charset=utf-8",
            ".md": "text/markdown; charset=utf-8",
        }
        content_type = content_types[candidate.suffix]
        self._send_bytes(HTTPStatus.OK, candidate.read_bytes(), content_type)

    def _send_json(self, status: HTTPStatus, payload: dict) -> None:
        body = json.dumps(payload, indent=2).encode("utf-8")
        self._send_bytes(status, body, "application/json; charset=utf-8")

    def _send_text(self, status: HTTPStatus, body: str, content_type: str) -> None:
        self._send_bytes(status, body.encode("utf-8"), content_type)

    def _send_bytes(self, status: HTTPStatus, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the PIP Planner local web UI.")
    parser.add_argument("--host", default="127.0.0.1", help="Host interface. Default: 127.0.0.1.")
    parser.add_argument("--port", type=int, default=8765, help="Port. Default: 8765.")
    parser.add_argument("--out", default="output/web", help="Directory for UI-generated CLI output files.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    output_root = Path(args.out).resolve()
    output_root.mkdir(parents=True, exist_ok=True)

    handler_class = type(
        "ConfiguredPlannerRequestHandler",
        (PlannerRequestHandler,),
        {
            "output_root": output_root,
            "project_root": Path.cwd().resolve(),
        },
    )

    server = ThreadingHTTPServer((args.host, args.port), handler_class)
    print(f"PIP Planner UI running at http://{args.host}:{args.port}/")
    print(f"Generated files will be written under {output_root}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping PIP Planner UI.")
    finally:
        server.server_close()
    return 0


def _choice(payload: dict, key: str, allowed: set[str], default: str) -> str:
    value = str(payload.get(key, default))
    if value not in allowed:
        raise ValueError(f"{key} must be one of: {', '.join(sorted(allowed))}.")
    return value


def _run_id_from_payload(payload: dict, safe_name: str) -> str:
    raw_run_id = str(payload.get("run_id") or "").strip()
    if raw_run_id:
        if any(not (char.isalnum() or char in "-_") for char in raw_run_id):
            raise ValueError("run_id contains unsupported characters.")
        return raw_run_id
    return f"{int(time.time())}-{uuid.uuid4().hex[:8]}-{safe_name}"


def _product_timeout(product: str) -> int:
    return {
        "schematic": 30,
        "chemical": 120,
        "solubility": 180,
        "genome": 240,
        "model": 180,
    }.get(product, 120)


def _collect_generated_file_paths(payload: dict, output_root: Path) -> dict[str, Path]:
    files = payload.get("files", {})
    if not isinstance(files, dict):
        return {}

    collected: dict[str, Path] = {}
    for key, raw_path in files.items():
        if not raw_path:
            continue
        path = Path(str(raw_path)).resolve()
        _assert_within(path, output_root)
        if path.exists():
            collected[key] = path
    return collected


def _assert_within(path: Path, root: Path) -> None:
    path.relative_to(root.resolve())


def _cli_command_prefix() -> list[str]:
    if getattr(sys, "frozen", False):
        return [sys.executable]
    return [sys.executable, "-m", "pip_planner"]


if __name__ == "__main__":
    raise SystemExit(main())
