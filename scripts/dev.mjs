/** Start the existing local services together; no credentials or data are stored. */
import { spawn } from 'node:child_process';
import { existsSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const args = process.argv.slice(2);
const mock = args.includes('--mock');
const agents = args.includes('--agents');
const v2 = args.includes('--v2');
if (v2 && (mock || agents)) {
  console.error('--v2 runs the standalone fixture API; use it without --mock or --agents.');
  process.exit(1);
}
const viteArgs = args.filter(value => !['--mock', '--agents', '--v2'].includes(value));
const python = folder => join(root, folder, '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');
const vite = join(root, 'frontend/node_modules/vite/bin/vite.js');
const required = [vite, ...(!mock ? [python('backend')] : []), ...(agents ? [python('engine')] : [])];
if (required.some(path => !existsSync(path))) {
  console.error('Install the frontend and backend dependencies from README.md first. --agents also requires the engine environment.');
  process.exit(1);
}

const children = [];
let stopping = false;
function stop(code = 0) {
  if (stopping) return;
  stopping = true;
  process.exitCode = code;
  for (const child of children) if (child.exitCode === null) child.kill('SIGTERM');
  const timer = setTimeout(() => {
    for (const child of children) if (child.exitCode === null) child.kill('SIGKILL');
  }, 3000);
  timer.unref();
}
function start(label, command, commandArgs, folder, extra = {}) {
  const child = spawn(command, commandArgs, {
    cwd: join(root, folder),
    stdio: 'inherit',
    env: { ...process.env, ...extra },
  });
  children.push(child);
  child.on('error', () => {
    console.error(`${label} could not start. Check its installed dependencies.`);
    stop(1);
  });
  child.on('exit', code => {
    if (!stopping) {
      console.error(`${label} stopped; shutting down the other local services.`);
      stop(code ?? 1);
    }
  });
}
process.on('SIGINT', () => stop());
process.on('SIGTERM', () => stop());

if (!mock) start('Backend', python('backend'), ['-m', 'uvicorn', v2 ? 'app.v2.main:app' : 'app.main:app', '--host', '127.0.0.1', '--port', v2 ? '8002' : '8000'], 'backend', { APP_MODE: process.env.APP_MODE || 'cached' });
if (agents) start('Exploratory engine', python('engine'), ['-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', '8001'], 'engine');
start('Frontend', process.execPath, [vite, ...viteArgs], 'frontend', { VITE_DATA_MODE: mock ? 'mock' : 'http' });
if (v2) console.log('PolicyFuzz v2 fixture: open the frontend URL at /v2 (normally http://127.0.0.1:5173/v2).');
