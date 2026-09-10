import { readFile, writeFile } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import openapiTS, { astToString, COMMENT_HEADER } from 'openapi-typescript';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const contract = resolve(root, '../contracts/v2-app/openapi.json');
const target = resolve(root, 'src/v2/api.generated.ts');
const expected = COMMENT_HEADER + astToString(await openapiTS(pathToFileURL(contract)));
if (process.argv.includes('--check')) {
  const actual = await readFile(target, 'utf8').catch(() => '');
  if (actual !== expected) {
    console.error('V2 API types are missing or stale. Run npm run generate:v2.');
    process.exitCode = 1;
  }
} else {
  await writeFile(target, expected);
}
