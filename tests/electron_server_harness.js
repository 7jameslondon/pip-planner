const assert = require('assert');
const { startPlannerServer, stopPlannerServer } = require('../electron/server');

async function main() {
  const server = await startPlannerServer({
    outDir: 'output/electron-harness',
    timeoutMs: 20000
  });

  try {
    const pageResponse = await fetch(server.url);
    assert.strictEqual(pageResponse.status, 200);
    const html = await pageResponse.text();
    assert.ok(html.includes('PIP Planner'));

    const apiResponse = await fetch(`${server.url}api/design`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        sequence: 'GTAC',
        architecture: 'hairpin',
        at_mode: 'distinguish',
        tail: 'dp',
        turn: 'gamma'
      })
    });
    assert.strictEqual(apiResponse.status, 200);
    const payload = await apiResponse.json();
    assert.ok(payload.design.chemical_renderer.startsWith('RDKit '));
    assert.ok(payload.chemical_svg.includes('data-renderer="RDKit"'));
    assert.ok(payload.generated.chemical_svg_url.endsWith('.svg'));

    console.log(`electron-server-harness-ok ${server.url}`);
  } finally {
    stopPlannerServer(server.child);
  }
}

main().catch(error => {
  console.error(error);
  process.exit(1);
});
