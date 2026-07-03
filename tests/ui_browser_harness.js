const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

async function previewMetrics(page) {
  return await page.locator('#preview').evaluate(preview => {
    const previewRect = preview.getBoundingClientRect();
    const files = document.querySelector('#files');
    const filesRect = files ? files.getBoundingClientRect() : null;
    return {
      height: previewRect.height,
      top: previewRect.top,
      bottom: previewRect.bottom,
      filesTop: filesRect ? filesRect.top : null
    };
  });
}

function assertStableLoadingLayout(before, during, label) {
  const tolerance = 1;
  if (during.height + tolerance < before.height) {
    throw new Error(
      `${label}: preview height shrank from ${before.height.toFixed(1)}px to ${during.height.toFixed(1)}px.`
    );
  }
  if (during.bottom + tolerance < before.bottom) {
    throw new Error(
      `${label}: preview bottom moved up from ${before.bottom.toFixed(1)}px to ${during.bottom.toFixed(1)}px.`
    );
  }
  if (before.filesTop !== null && during.filesTop !== null && during.filesTop + tolerance < before.filesTop) {
    throw new Error(
      `${label}: file details moved up from ${before.filesTop.toFixed(1)}px to ${during.filesTop.toFixed(1)}px.`
    );
  }
}

async function startPreviewLoadingWatch(page) {
  await page.evaluate(() => {
    if (window.__pipPlannerLoadingObserver) {
      window.__pipPlannerLoadingObserver.disconnect();
    }
    window.__pipPlannerLoadingSeen = false;
    const preview = document.querySelector('#preview');
    const markIfLoading = () => {
      if (preview && preview.querySelector('.loading')) {
        window.__pipPlannerLoadingSeen = true;
      }
    };
    markIfLoading();
    window.__pipPlannerLoadingObserver = new MutationObserver(markIfLoading);
    window.__pipPlannerLoadingObserver.observe(preview, { childList: true, subtree: true });
  });
}

async function stopPreviewLoadingWatch(page) {
  return await page.evaluate(() => {
    const seen = Boolean(window.__pipPlannerLoadingSeen);
    if (window.__pipPlannerLoadingObserver) {
      window.__pipPlannerLoadingObserver.disconnect();
      delete window.__pipPlannerLoadingObserver;
    }
    delete window.__pipPlannerLoadingSeen;
    return seen;
  });
}

async function main() {
  const baseUrl = process.argv[2];
  const artifactDir = process.argv[3] || path.join('output', 'playwright');
  if (!baseUrl) {
    throw new Error('Usage: node tests/ui_browser_harness.js <base-url> [artifact-dir]');
  }

  fs.mkdirSync(artifactDir, { recursive: true });
  const launchOptions = { headless: true, args: ['--no-sandbox'] };
  const requestedExecutable = process.env.PIP_PLANNER_BROWSER_EXECUTABLE;
  if (requestedExecutable && fs.existsSync(requestedExecutable)) {
    launchOptions.executablePath = requestedExecutable;
  } else {
    const executablePath = chromium.executablePath();
    if (fs.existsSync(executablePath)) {
      launchOptions.executablePath = executablePath;
    }
  }
  const browser = await chromium.launch(launchOptions);
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  const consoleErrors = [];
  let delayNextSchematic = false;
  let serveCachedProducts = false;
  let cachedFulfillCount = 0;
  const cachedProductResponses = new Map();
  page.on('console', message => {
    if (message.type() === 'error') consoleErrors.push(message.text());
  });
  await page.route('**/api/design/product', async route => {
    const request = route.request();
    let product = '';
    if (request.method() === 'POST') {
      try {
        product = JSON.parse(request.postData() || '{}').product || '';
      } catch (_error) {
        product = '';
      }
    }
    if (serveCachedProducts && cachedProductResponses.has(product)) {
      cachedFulfillCount += 1;
      await route.fulfill(cachedProductResponses.get(product));
      return;
    }
    if (delayNextSchematic && product === 'schematic') {
      delayNextSchematic = false;
      await sleep(700);
    }
    const response = await route.fetch();
    const body = await response.text();
    const cachedResponse = {
      status: response.status(),
      headers: response.headers(),
      body
    };
    if (product && response.ok()) {
      cachedProductResponses.set(product, cachedResponse);
    }
    await route.fulfill(cachedResponse);
  });

  try {
    await page.goto(baseUrl, { waitUntil: 'domcontentloaded' });
    await page.waitForSelector('#preview svg', { timeout: 10000 });
    await page.click('[data-view="genome"]');
    await page.click('[data-genome-settings-toggle]');
    await page.waitForFunction(() => {
      const options = [...document.querySelectorAll('#genome-select option')].map(option => option.value);
      return options.includes('human-grch38') && options.includes('sacCer3');
    }, null, { timeout: 10000 });
    const defaultGenome = await page.locator('#genome-select').inputValue();
    if (defaultGenome !== 'sacCer3') {
      throw new Error(`Expected sacCer3 to be the default genome, saw: ${defaultGenome}.`);
    }
    const genomeOptionsText = await page.locator('#genome-select').textContent();
    if (genomeOptionsText.includes('HeLa') || genomeOptionsText.includes('hela') || genomeOptionsText.includes('Not searched')) {
      throw new Error('HeLa should not be listed as a built-in genome option.');
    }
    await page.click('[data-genome-settings-toggle]');
    await page.click('[data-view="schematic"]');
    const toolbarDownloads = await page.locator('.toolbar .download').count();
    if (toolbarDownloads !== 0) {
      throw new Error(`Expected no toolbar download links, saw ${toolbarDownloads}.`);
    }
    await page.waitForFunction(() => {
      const title = document.querySelector('#preview svg title');
      return title && title.textContent.includes('schematic');
    }, null, { timeout: 10000 });
    await page.waitForSelector('#preview .preview-download[aria-label="Download schematic SVG"]', { timeout: 10000 });

    await page.fill('#sequence', 'axt gc123');
    const sanitizedSequence = await page.locator('#sequence').inputValue();
    if (sanitizedSequence !== 'ATGC') {
      throw new Error(`Expected DNA input to sanitize to ATGC, saw: ${sanitizedSequence}`);
    }
    await page.locator('label').filter({ hasText: 'Linear' }).click();
    await page.selectOption('#at-mode', 'py-py');
    await page.selectOption('#tail', 'none');
    await page.click('[data-view="genome"]');
    await page.click('[data-genome-settings-toggle]');
    await page.selectOption('#genome-select', 'human-grch38');
    await page.waitForFunction(() => {
      const chain = document.querySelector('#metric-chain');
      return chain && chain.textContent.includes('Py-Py-Im-Py');
    }, null, { timeout: 10000 });

    await page.click('[data-view="solubility"]');
    await page.waitForSelector('#preview table.solubility-table', { timeout: 20000 });
    const solubilityText = await page.locator('#preview').textContent();
    if (!solubilityText.includes('ADMET-AI v2') || !solubilityText.includes('SolTranNet')) {
      throw new Error('Solubility predictions were not shown in the preview tab.');
    }

    await page.click('[data-view="genome"]');
    await page.waitForSelector('#preview table.genome-table', { timeout: 10000 });
    const genomeText = await page.locator('#preview').textContent();
    if (!genomeText.includes('Human GRCh38') || !genomeText.includes('GENE1')) {
      throw new Error('Genome occurrences were not shown in the preview tab.');
    }

    await page.click('[data-view="chemical"]');
    await page.waitForSelector('#preview .preview-download[aria-label="Download chemical SVG"]', { timeout: 10000 });
    const chemicalRenderer = await page.locator('#preview svg').getAttribute('data-renderer');
    if (chemicalRenderer !== 'RDKit') {
      throw new Error(`Expected RDKit chemical SVG, saw renderer: ${chemicalRenderer}`);
    }

    await page.click('[data-view="schematic"]');
    await page.waitForFunction(() => {
      const title = document.querySelector('#preview svg title');
      return title && title.textContent.includes('schematic');
    }, null, { timeout: 10000 });
    await page.waitForSelector('#preview .preview-download[aria-label="Download schematic SVG"]', { timeout: 10000 });

    await page.click('[data-view="model"]');
    await page.waitForSelector('#preview iframe.model-frame', { timeout: 10000 });
    await page.waitForSelector('#preview .preview-download[aria-label="Download PDB"]', { timeout: 10000 });
    const modelFrame = page.frameLocator('#preview iframe.model-frame');
    await modelFrame.locator('canvas#scene').waitFor({ timeout: 10000 });

    for (const product of ['schematic', 'chemical', 'solubility', 'genome', 'model']) {
      if (!cachedProductResponses.has(product)) {
        throw new Error(`Expected cached ${product} response for fast loading test.`);
      }
    }
    serveCachedProducts = true;
    const cachedFulfillStart = cachedFulfillCount;
    await startPreviewLoadingWatch(page);
    await page.selectOption('#turn', 'beta');
    const cachedDeadline = Date.now() + 5000;
    while (cachedFulfillCount - cachedFulfillStart < 5 && Date.now() < cachedDeadline) {
      await sleep(25);
    }
    if (cachedFulfillCount - cachedFulfillStart < 5) {
      throw new Error('Timed out waiting for cached automatic update responses.');
    }
    await sleep(350);
    const fastUpdateShowedLoading = await stopPreviewLoadingWatch(page);
    serveCachedProducts = false;
    if (fastUpdateShowedLoading) {
      throw new Error('Fast cached update showed a loading spinner before replacing the output.');
    }

    const beforeUpdate = await previewMetrics(page);
    delayNextSchematic = true;
    await page.fill('#sequence', 'ATGCA');
    await page.waitForSelector('#preview .loading', { timeout: 5000 });
    const duringUpdate = await previewMetrics(page);
    assertStableLoadingLayout(beforeUpdate, duringUpdate, 'Model tab loading state');
    await page.screenshot({
      path: path.join(artifactDir, 'pip-planner-loading-state.png'),
      fullPage: true
    });
    await page.waitForSelector('#preview iframe.model-frame', { timeout: 15000 });
    await page.waitForFunction(() => !document.querySelector('[data-layout-locked]'), null, { timeout: 10000 });
    const updatedModelFrame = page.frameLocator('#preview iframe.model-frame');
    await updatedModelFrame.locator('canvas#scene').waitFor({ timeout: 10000 });

    const filesText = await page.locator('#files').textContent();
    if (!filesText.includes('Generated with RDKit') || !filesText.includes('SMILES:') || !filesText.includes('complex-model.pdb')) {
      throw new Error('RDKit renderer details were not shown in the UI.');
    }

    await page.screenshot({
      path: path.join(artifactDir, 'pip-planner-ui.png'),
      fullPage: true
    });

    if (consoleErrors.length) {
      throw new Error(`Browser console errors:\n${consoleErrors.join('\n')}`);
    }
  } finally {
    try {
      await page.unrouteAll({ behavior: 'ignoreErrors' });
    } catch (_error) {
      await page.unroute('**/api/design/product').catch(() => {});
    }
    await browser.close();
  }
}

main().catch(error => {
  console.error(error);
  process.exit(1);
});
