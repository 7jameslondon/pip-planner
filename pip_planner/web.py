from __future__ import annotations

import argparse
import json
from http import HTTPStatus
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
import subprocess
import sys
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
    .primary {
      width: 100%;
      margin-top: 20px;
      border: 0;
      border-radius: 8px;
      background: var(--green);
      color: #fff;
      min-height: 44px;
      font-weight: 700;
      cursor: pointer;
    }
    .primary:disabled {
      cursor: wait;
      opacity: 0.72;
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
    .metric.solubility, .metric.genome { grid-column: 1 / -1; }
    .genome-panel {
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      margin: 0 0 18px;
      overflow: auto;
      display: none;
    }
    .genome-panel.is-visible { display: block; }
    .genome-panel .empty {
      text-align: left;
      padding: 14px;
    }
    .location-table {
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
      min-width: 680px;
    }
    .location-table th,
    .location-table td {
      border-bottom: 1px solid var(--line);
      padding: 9px 10px;
      text-align: left;
      vertical-align: top;
    }
    .location-table th {
      color: var(--muted);
      font-size: 12px;
      font-weight: 700;
      background: #f8fafc;
    }
    .location-table td.code {
      font-family: Consolas, 'Liberation Mono', monospace;
      white-space: nowrap;
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
      display: grid;
      place-items: center;
      min-height: 240px;
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

        <label for="genome">Genome</label>
        <select id="genome" name="genome">
          <option value="none">Not searched</option>
          <option value="human-grch38">Human GRCh38</option>
          <option value="hela">HeLa</option>
        </select>

        <button class="primary" type="submit" id="submit">Update now</button>
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
        <div class="metric solubility"><span>Solubility</span><strong id="metric-solubility">-</strong></div>
        <div class="metric genome"><span>Genome occurrences</span><strong id="metric-genome">-</strong></div>
        <div class="metric genome"><span>3D/MD model</span><strong id="metric-model">-</strong></div>
      </section>

      <section class="genome-panel" id="genome-panel" aria-label="Genome occurrence locations"></section>

      <div class="toolbar">
        <button class="tab" type="button" data-view="schematic" aria-selected="true">Schematic</button>
        <button class="tab" type="button" data-view="chemical" aria-selected="false">Chemical structure</button>
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
    const submit = document.querySelector('#submit');
    const preview = document.querySelector('#preview');
    const genomePanel = document.querySelector('#genome-panel');
    const warnings = document.querySelector('#warnings');
    const errors = document.querySelector('#errors');
    const tabs = [...document.querySelectorAll('.tab')];
    let currentResult = null;
    let currentView = 'schematic';
    let designTimer = null;
    let activeDesignRequest = 0;
    let lastQueuedPayload = '';
    const productOrder = ['schematic', 'chemical', 'solubility', 'genome', 'model'];

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

    function formatSolubility(predictions) {
      if (!Array.isArray(predictions) || predictions.length === 0) return '-';
      return predictions.map(prediction => {
        const method = prediction.method || 'Unknown predictor';
        if (prediction.status === 'ok' && Number.isFinite(Number(prediction.value))) {
          const value = Number(prediction.value).toPrecision(3);
          const unit = prediction.unit || 'predicted logS';
          const propertyName = prediction.property_name ? ' (' + prediction.property_name + ')' : '';
          return method + ': ' + value + ' ' + unit + propertyName;
        }
        const status = prediction.status || 'unknown';
        const message = prediction.message ? ' - ' + prediction.message : '';
        return method + ': ' + status + message;
      }).join('\\n');
    }

    function formatGenomeOccurrences(genomeResult) {
      if (!genomeResult || genomeResult.status === 'skipped') return 'Not searched';
      if (genomeResult.status === 'missing_reference') return 'Reference missing';
      if (genomeResult.status !== 'ok') return genomeResult.status || 'Unavailable';
      const count = Number(genomeResult.total_occurrences);
      const label = genomeResult.genome_label || genomeResult.genome_id || 'Genome';
      return Number.isFinite(count) ? count.toLocaleString() + ' in ' + label : label;
    }

    function formatModelStatus(modelResult) {
      if (!modelResult) return 'Not generated';
      const simulation = modelResult.md_simulation || {};
      const status = simulation.status || modelResult.status || 'unknown';
      const atoms = Number(modelResult.atom_count);
      const countText = Number.isFinite(atoms) ? atoms.toLocaleString() + ' atoms' : 'model generated';
      return status + ' | ' + countText;
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
      setMetricLoading('#metric-target');
      setMetricLoading('#metric-complement');
      setMetricLoading('#metric-pairs');
      setMetricLoading('#metric-chain');
      setMetricLoading('#metric-solubility');
      setMetricLoading('#metric-genome');
      setMetricLoading('#metric-model');
      renderGenomePanel(null);
      showMessage(warnings, '');
      showMessage(errors, '');
      document.querySelector('#files').textContent = '';
      renderPreview();
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

    function renderGenomePanel(genomeResult) {
      if (!genomeResult || genomeResult.status === 'skipped') {
        genomePanel.classList.remove('is-visible');
        genomePanel.innerHTML = '';
        return;
      }

      genomePanel.classList.add('is-visible');
      if (genomeResult.status !== 'ok') {
        genomePanel.innerHTML = '<div class="empty">' + escapeHtml(genomeResult.message || 'Genome search is unavailable.') + '</div>';
        return;
      }

      const locations = Array.isArray(genomeResult.locations) ? genomeResult.locations : [];
      if (!genomeResult.locations_listed || locations.length === 0) {
        genomePanel.innerHTML = '<div class="empty">' + escapeHtml(genomeResult.message || 'No locations are listed.') + '</div>';
        return;
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

      genomePanel.innerHTML =
        '<table class="location-table">' +
        '<thead><tr><th>Contig</th><th>Start</th><th>End</th><th>Strand</th><th>Overlapping annotation</th></tr></thead>' +
        '<tbody>' + rows + '</tbody>' +
        '</table>';
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

    async function loadGenomes() {
      const genomeSelect = document.querySelector('#genome');
      try {
        const response = await fetch('/api/genomes');
        if (!response.ok) return;
        const payload = await response.json();
        if (!Array.isArray(payload.genomes)) return;
        const selected = genomeSelect.value;
        const options = [{ id: 'none', label: 'Not searched', available: true }].concat(payload.genomes);
        genomeSelect.innerHTML = options.map(genome => {
          const label = genome.label + (genome.available === false ? ' (missing data)' : '');
          return '<option value="' + escapeHtml(genome.id) + '">' + escapeHtml(label) + '</option>';
        }).join('');
        genomeSelect.value = options.some(genome => genome.id === selected) ? selected : 'none';
      } catch (error) {
        return;
      }
    }

    function renderState() {
      if (!currentResult) return;
      const design = currentResult.design || {};
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

      renderProductMetric('#metric-solubility', 'solubility', () => formatSolubility(design.solubility_predictions));
      renderProductMetric('#metric-genome', 'genome', () => formatGenomeOccurrences(design.genome_occurrences));
      renderProductMetric('#metric-model', 'model', () => formatModelStatus(design.model_3d));
      renderGenomePanel(currentResult.productStatus.genome === 'done' ? design.genome_occurrences : null);
      showMessage(warnings, Array.isArray(design.warnings) ? design.warnings.join(' ') : '');
      renderFilesText(design);
      renderPreview();
    }

    function renderProductMetric(selector, product, formatter) {
      const status = currentResult.productStatus[product];
      if (status === 'done') {
        setMetric(selector, formatter());
      } else if (status === 'error') {
        setMetric(selector, 'Error');
      } else {
        setMetricLoading(selector);
      }
    }

    function renderFilesText(design) {
      const files = design.files || {};
      const pieces = [];
      if (design.chemical_renderer) pieces.push('Generated with ' + design.chemical_renderer);
      if (design.chemical_smiles) pieces.push('SMILES: ' + design.chemical_smiles);
      ['chemical_svg', 'schematic_svg', 'complex_pdb'].forEach(key => {
        if (files[key]) pieces.push(files[key]);
      });
      document.querySelector('#files').textContent = pieces.join(' | ');
    }

    function renderPreview() {
      if (!currentResult) return;
      const download = renderPreviewDownload();
      if (currentView === 'chemical') {
        preview.innerHTML = renderProductPreview('chemical', currentResult.chemical_svg, 'Chemical structure') + download;
      } else if (currentView === 'schematic') {
        preview.innerHTML = renderProductPreview('schematic', currentResult.schematic_svg, 'Schematic') + download;
      } else {
        if (currentResult.productStatus.model === 'done' && currentResult.generated.model_html_url) {
          preview.innerHTML = '<iframe class="model-frame" title="3D DNA polyamide model" src="' +
            escapeHtml(currentResult.generated.model_html_url) + '"></iframe>' + download;
        } else if (currentResult.productStatus.model === 'error') {
          preview.innerHTML = '<div class="empty">' + escapeHtml(currentResult.productErrors.model || 'The 3D model failed.') + '</div>';
        } else {
          preview.innerHTML = loadingMarkup('Building 3D model');
        }
      }
      tabs.forEach(tab => {
        tab.setAttribute('aria-selected', String(tab.dataset.view === currentView));
      });
    }

    function renderPreviewDownload() {
      const downloads = {
        chemical: {
          href: currentResult.generated.chemical_svg_url,
          name: currentResult.generated.chemical_svg_name,
          label: 'Download chemical SVG'
        },
        schematic: {
          href: currentResult.generated.schematic_svg_url,
          name: currentResult.generated.schematic_svg_name,
          label: 'Download schematic SVG'
        },
        model: {
          href: currentResult.generated.complex_pdb_url,
          name: currentResult.generated.complex_pdb_name,
          label: 'Download PDB'
        }
      };
      const download = downloads[currentView];
      if (!download || !download.href) return '';
      return '<a class="preview-download" href="' + escapeHtml(download.href) + '" download="' +
        escapeHtml(download.name || '') + '" aria-label="' + escapeHtml(download.label) +
        '" title="' + escapeHtml(download.label) + '"><span aria-hidden="true">↓</span></a>';
    }

    function renderProductPreview(product, markup, label) {
      const status = currentResult.productStatus[product];
      if (status === 'done' && markup) return markup;
      if (status === 'error') return '<div class="empty">' + escapeHtml(currentResult.productErrors[product] || label + ' failed.') + '</div>';
      return loadingMarkup(label);
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
      resetProductState();
      submit.disabled = true;
      submit.textContent = 'Updating...';
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
      } finally {
        if (requestId === activeDesignRequest) {
          submit.disabled = false;
          submit.textContent = 'Update now';
        }
      }
    }

    tabs.forEach(tab => {
      tab.addEventListener('click', () => {
        currentView = tab.dataset.view;
        renderPreview();
      });
    });
    sequenceInput.addEventListener('input', sanitizeSequenceInput);
    form.addEventListener('submit', design);
    form.addEventListener('input', () => scheduleDesign());
    form.addEventListener('change', () => scheduleDesign(0));
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
