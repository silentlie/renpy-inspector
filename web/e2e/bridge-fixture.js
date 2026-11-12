import { spawn } from 'node:child_process';
import { createInterface } from 'node:readline';
import { resolve } from 'node:path';

// Only stdout JSON emitted by the fixture is part of this process contract.
// No debug console noise or Ren'Py SDK is needed for these browser/HTTP tests.
export async function startBridgeFixture() {
  const python = process.env.PYTHON || (process.platform === 'win32' ? 'python' : 'python3');
  const script = resolve(process.cwd(), '../scripts/e2e_bridge_fixture.py');
  const child = spawn(python, ['-u', script], {
    cwd: resolve(process.cwd(), '..'),
    stdio: ['pipe', 'pipe', 'pipe'],
  });
  let id = 0;
  let stderr = '';
  let closed = false;
  const pending = new Map();
  let readyDone = false;
  let resolveReady;
  let rejectReady;
  const ready = new Promise((resolve, reject) => {
    resolveReady = resolve;
    rejectReady = reject;
  });
  const deadline = setTimeout(() => {
    if (!readyDone) rejectReady(new Error('Synthetic bridge did not start: ' + stderr));
    child.kill();
  }, 15000);
  const lines = createInterface({ input: child.stdout });
  lines.on('line', (line) => {
    let data;
    try { data = JSON.parse(line); } catch { return; }
    if (data.ready && !readyDone) {
      readyDone = true;
      clearTimeout(deadline);
      resolveReady(data.ready);
    } else if (data.error && !readyDone) {
      readyDone = true;
      clearTimeout(deadline);
      rejectReady(new Error(data.error));
    }
    const command = pending.get(data.ack);
    if (command) {
      clearTimeout(command.timeout);
      pending.delete(data.ack);
      if (data.error) command.reject(new Error(data.error));
      else command.resolve(data);
    }
  });
  child.stderr.on('data', (buffer) => {
    stderr = (stderr + buffer.toString()).slice(-8000);
  });
  child.on('error', (reason) => {
    if (!readyDone) rejectReady(reason);
    for (const command of pending.values()) command.reject(reason);
    pending.clear();
  });
  child.on('exit', (code) => {
    closed = true;
    if (!readyDone) rejectReady(new Error('Bridge fixture exited ' + code + ': ' + stderr));
    for (const command of pending.values()) command.reject(new Error(
      'Bridge fixture exited ' + code + ': ' + stderr));
    pending.clear();
  });

  let url;
  try { url = await ready; }
  catch (reason) { child.kill(); throw reason; }

  const command = (action, fields = {}) => {
    if (closed) return Promise.reject(new Error('Fixture process already exited'));
    const number = ++id;
    return new Promise((resolve, reject) => {
      const timeout = setTimeout(() => {
        pending.delete(number);
        reject(new Error('Fixture command timed out: ' + action + ' ' + stderr));
      }, 10000);
      pending.set(number, { resolve, reject, timeout });
      child.stdin.write(JSON.stringify({ ...fields, id: number, action }) + '\n');
    });
  };
  const stop = async () => {
    if (closed) return;
    try { await command('exit'); } catch { /* force stop below */ }
    if (!closed) child.kill();
    lines.close();
  };
  return { url, origin: new URL(url).origin, token: new URLSearchParams(
    new URL(url).hash.substring(1)).get('token'), command, stop };
}
