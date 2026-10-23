import { spawn } from 'node:child_process';
import { createHash } from 'node:crypto';
import { existsSync } from 'node:fs';
import { mkdtemp, writeFile, rm } from 'node:fs/promises';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { TEST_ROOT, TEST_SOCKET_ROOT, managedPython } from './test-environment.mjs';

// Real Qrun queue and handler; only the systemd runtime is replaced inside the
// runner's private process namespace. Each caller owns and closes its daemon.
export async function startQrunFixture(config, workRoot) {
  const root = await mkdtemp(join(TEST_ROOT, 'qrun-'));
  const source = fileURLToPath(new URL('../../../', import.meta.url));
  const python = managedPython();
  const program = `import sys; sys.path.insert(0, ${JSON.stringify(source)}); from pathlib import Path; from tests.support.qrun_runtime import serve; serve(Path(sys.argv[1]), Path(sys.argv[2]))`;
  const child = spawn(python, ['-B', '-c', program, root, workRoot], {
    env: { ...process.env, XDG_RUNTIME_DIR: TEST_SOCKET_ROOT }, stdio: 'ignore',
  });
  let spawnError;
  child.on('error', error => { spawnError = error; });
  const exited = new Promise(resolve => child.once('close', resolve));
  const socket = join(TEST_SOCKET_ROOT, 'qrun-' + createHash('sha256').update(root).digest('hex').slice(0, 20) + '.sock');
  const close = async () => {
    if (child.exitCode === null) child.kill('SIGTERM');
    await exited;
    if (existsSync(socket)) throw new Error('Qrun fixture socket survived shutdown');
    await rm(root, { recursive: true, force: true });
  };
  try {
    const deadline = Date.now() + 5000;
    while (!existsSync(socket)) {
      if (spawnError) throw spawnError;
      if (child.exitCode !== null || Date.now() > deadline) throw new Error('Qrun fixture failed to start');
      await new Promise(resolve => setTimeout(resolve, 10));
    }
    await writeFile(config, `[execution]\nschema_version=2\ndefault_platform="local"\n[execution.platforms.local]\ndefault_scheduler="main"\nschedulers.main.executor="qrun"\ntransport="local"\nstorage.file_mode="shared"\nstorage.work_root=${JSON.stringify(workRoot)}\nschedulers.main.handler=${JSON.stringify([python, '-B', '-m', 'research_agent.jobs.qrun', '--state-dir', root, 'handler'])}\nsubmission={resources={cpus=1,memory_mb=512}}\n[execution.platforms.local.schedulers.main.handler_environment]\nXDG_RUNTIME_DIR=${JSON.stringify(TEST_SOCKET_ROOT)}\n`);
    return close;
  } catch (error) {
    await close();
    throw error;
  }
}
