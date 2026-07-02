const childProcess = require('child_process');
const fs = require('fs');
const http = require('http');
const net = require('net');
const path = require('path');

function projectRoot() {
  return path.resolve(__dirname, '..');
}

function pythonExecutable() {
  return process.env.PIP_PLANNER_PYTHON || 'python';
}

function packagedBackendExecutable() {
  if (process.env.PIP_PLANNER_BACKEND_EXE && fs.existsSync(process.env.PIP_PLANNER_BACKEND_EXE)) {
    return process.env.PIP_PLANNER_BACKEND_EXE;
  }

  if (!process.resourcesPath) return null;
  const executableName = process.platform === 'win32' ? 'pip-planner-web.exe' : 'pip-planner-web';
  const candidate = path.join(
    process.resourcesPath,
    'backend',
    'pip-planner-web',
    executableName
  );
  return fs.existsSync(candidate) ? candidate : null;
}

function getFreePort(host = '127.0.0.1') {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.on('error', reject);
    server.listen(0, host, () => {
      const address = server.address();
      const port = typeof address === 'object' && address ? address.port : null;
      server.close(() => {
        if (port) resolve(port);
        else reject(new Error('Could not allocate a local port.'));
      });
    });
  });
}

function waitForUrl(url, timeoutMs = 15000) {
  const deadline = Date.now() + timeoutMs;

  return new Promise((resolve, reject) => {
    function attempt() {
      const request = http.get(url, response => {
        response.resume();
        if (response.statusCode >= 200 && response.statusCode < 500) {
          resolve();
          return;
        }
        retry();
      });

      request.on('error', retry);
      request.setTimeout(1000, () => {
        request.destroy();
        retry();
      });
    }

    function retry(error) {
      if (Date.now() > deadline) {
        reject(error || new Error(`Timed out waiting for ${url}`));
        return;
      }
      setTimeout(attempt, 150);
    }

    attempt();
  });
}

async function startPlannerServer(options = {}) {
  const host = options.host || '127.0.0.1';
  const port = options.port || await getFreePort(host);
  const root = options.cwd || projectRoot();
  const outDir = options.outDir || path.join('output', 'electron');
  const backend = options.backendExecutable || packagedBackendExecutable();
  const executable = backend || options.python || pythonExecutable();
  const args = backend
    ? [
        '--host',
        host,
        '--port',
        String(port),
        '--out',
        outDir
      ]
    : [
        '-m',
        'pip_planner.web',
        '--host',
        host,
        '--port',
        String(port),
        '--out',
        outDir
      ];

  const child = childProcess.spawn(executable, args, {
    cwd: backend ? path.dirname(backend) : root,
    windowsHide: true,
    stdio: ['ignore', 'pipe', 'pipe'],
    env: {
      ...process.env,
      PYTHONUNBUFFERED: '1'
    }
  });

  let output = '';
  child.stdout.on('data', chunk => {
    output += chunk.toString();
  });
  child.stderr.on('data', chunk => {
    output += chunk.toString();
  });

  const url = `http://${host}:${port}/`;

  try {
    await Promise.race([
      waitForUrl(url, options.timeoutMs || 15000),
      new Promise((_, reject) => {
        child.once('exit', code => {
          reject(new Error(`PIP Planner server exited before startup with code ${code}. ${output}`));
        });
      })
    ]);
  } catch (error) {
    stopPlannerServer(child);
    throw error;
  }

  return {
    child,
    url,
    host,
    port,
    output: () => output
  };
}

function stopPlannerServer(child) {
  if (!child || child.killed) return;
  child.kill();
}

module.exports = {
  getFreePort,
  packagedBackendExecutable,
  projectRoot,
  pythonExecutable,
  startPlannerServer,
  stopPlannerServer,
  waitForUrl
};
