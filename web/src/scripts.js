/** Browser-only script metadata helpers. Never build file:// or editor URLs. */
export function normaliseGameScriptFile(filename) {
  if (typeof filename !== 'string' || filename.length > 360) return '';
  const input = filename.replace(/\\/g, '/');
  const gameAt = input.lastIndexOf('/game/');
  const relative = gameAt >= 0 ? input.slice(gameAt + 6) :
    input.startsWith('game/') ? input.slice(5) : input;
  if (relative.startsWith('/') || !relative.endsWith('.rpy') ||
      relative.includes('\0') || relative.split('/').some((p) =>
        !p || p === '.' || p === '..')) return '';
  return relative;
}

export function safeScriptLine(line) {
  const value = Number(line);
  return Number.isSafeInteger(value) && value >= 1 && value <= 100000 ? value : null;
}

export function appendScriptLabels(existing, incoming) {
  const list = [...(existing ?? [])];
  const seen = new Set(list.map((entry) => entry.name + '\0' + entry.file + '\0' + entry.line));
  for (const item of incoming ?? []) {
    if (!item || typeof item.name !== 'string' || typeof item.file !== 'string' ||
        safeScriptLine(item.line) === null) continue;
    const id = item.name + '\0' + item.file + '\0' + item.line;
    if (!seen.has(id)) {
      seen.add(id);
      list.push(item);
    }
  }
  return list;
}

/** Keep source navigation scoped to the existing read-only .rpy endpoint. */
export function sourceTargetForContext(info) {
  const file = normaliseGameScriptFile(info?.file ?? info?.filename);
  const line = safeScriptLine(info?.line);
  return file && line ? { file, line } : null;
}
