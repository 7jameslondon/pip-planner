const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');

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
  page.on('console', message => {
    if (message.type() === 'error') consoleErrors.push(message.text());
  });

  try {
    await page.goto(baseUrl, { waitUntil: 'domcontentloaded' });
    await page.waitForSelector('#preview svg', { timeout: 10000 });

    await page.fill('#sequence', 'ATGC');
    await page.locator('label').filter({ hasText: 'Linear' }).click();
    await page.selectOption('#at-mode', 'py-py');
    await page.selectOption('#tail', 'none');
    await page.waitForFunction(() => {
      const chain = document.querySelector('#metric-chain');
      return chain && chain.textContent.includes('Py-Py-Im-Py');
    }, null, { timeout: 10000 });

    const chemicalRenderer = await page.locator('#preview svg').getAttribute('data-renderer');
    if (chemicalRenderer !== 'RDKit') {
      throw new Error(`Expected RDKit chemical SVG, saw renderer: ${chemicalRenderer}`);
    }

    await page.click('[data-view="schematic"]');
    await page.waitForFunction(() => {
      const title = document.querySelector('#preview svg title');
      return title && title.textContent.includes('schematic');
    }, null, { timeout: 10000 });

    const filesText = await page.locator('#files').textContent();
    if (!filesText.includes('Generated with RDKit') || !filesText.includes('SMILES:')) {
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
    await browser.close();
  }
}

main().catch(error => {
  console.error(error);
  process.exit(1);
});
