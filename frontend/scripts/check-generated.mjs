import { readFile } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath, pathToFileURL } from 'node:url';
import openapiTS, { astToString, COMMENT_HEADER } from 'openapi-typescript';

const frontendRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const contractPath = resolve(frontendRoot, '../contracts/openapi.json');
const generatedPath = resolve(frontendRoot, 'src/api/generated.ts');

const tracked = spawnSync(
  'git',
  ['ls-files', '--error-unmatch', '--', 'src/api/generated.ts'],
  { cwd: frontendRoot, stdio: 'ignore' },
);
if (tracked.status !== 0) {
  console.error('Generated API types are not tracked by git. Generate and commit the reviewed output.');
  process.exitCode = 1;
}

let committed;
try {
  committed = await readFile(generatedPath, 'utf8');
} catch {
  console.error('Generated API types are missing. Run npm run generate:types.');
  process.exitCode = 1;
}

if (committed !== undefined) {
  const ast = await openapiTS(pathToFileURL(contractPath));
  const expected = COMMENT_HEADER + astToString(ast);
  if (committed !== expected) {
    console.error('Generated API types are stale. Run npm run generate:types and review the diff.');
    process.exitCode = 1;
  }
}
