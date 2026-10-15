export interface ParamRow {
  key: string;
  kind: 'number' | 'text';
  value: string | number;
}

export function paramsToRows(params: Record<string, number | string>): ParamRow[] {
  return Object.entries(params).map(([key, value]) => ({ key, kind: typeof value === 'number' ? 'number' : 'text', value }));
}

export function rowsToParams(rows: ParamRow[]): Record<string, number | string> {
  const out: Record<string, number | string> = {};
  for (const r of rows) {
    if (!r.key.trim()) continue;
    out[r.key.trim()] = r.kind === 'number' ? Number(r.value) || 0 : String(r.value);
  }
  return out;
}

