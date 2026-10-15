// Runs every lib/*.check.ts self-check, the way each file's header says: compile with tsc to a temporary folder,
// then run the result with node. Exits non-zero at the first failure. No dependency beyond typescript.
import { spawnSync } from 'node:child_process';
import { mkdtempSync, readdirSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const files = readdirSync('lib').filter((f) => f.endsWith('.check.ts')).sort();
const out = mkdtempSync(join(tmpdir(), 'dgchk-'));
let failed = false;
for (const f of files) {
  const tsc = spawnSync('npx', ['tsc', join('lib', f), '--outDir', out, '--module', 'commonjs', '--target', 'es2022',
    '--skipLibCheck', '--esModuleInterop', '--resolveJsonModule'], { stdio: 'inherit' });
  const js = join(out, f.replace(/\.ts$/, '.js'));
  const run = tsc.status === 0 ? spawnSync('node', [js], { stdio: 'inherit' }) : tsc;
  console.log(`${run.status === 0 ? 'ok  ' : 'FAIL'} ${f}`);
  if (run.status !== 0) failed = true;
}
rmSync(out, { recursive: true, force: true });
process.exit(failed ? 1 : 0);
