import { ApiError, type ApiClient, type LiveHandlers, type Served } from './client';
import { connectLiveSocket } from './ws';
import type { ApiErrorBody, ServedBy } from './types';

const SERVED_BY: ServedBy[] = ['mongodb', 'cassandra', 'redis', 'snapshot'];

function qs(params: Record<string, string | number | undefined | null>): string {
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== '') sp.set(k, String(v));
  }
  const s = sp.toString();
  return s ? `?${s}` : '';
}

export function createHttpClient(baseUrl: string): ApiClient {
  const root = `${baseUrl}/api`;

  async function request(method: string, path: string, body?: unknown): Promise<Response> {
    let res: Response;
    try {
      res = await fetch(root + path, {
        method,
        headers: body !== undefined ? { 'Content-Type': 'application/json' } : undefined,
        body: body !== undefined ? JSON.stringify(body) : undefined,
      });
    } catch {
      throw new ApiError(0, `Cannot reach the API at ${baseUrl}.`);
    }
    if (!res.ok) {
      let errBody: ApiErrorBody | null = null;
      try {
        const raw = await res.json();
        // Accept both the contract shape and FastAPI's default {"detail": ...}.
        if (raw && typeof raw === 'object') {
          const detail = (raw as { detail?: unknown }).detail;
          const src = detail && typeof detail === 'object' ? detail : raw;
          errBody = {
            reason: String((src as ApiErrorBody).reason ?? 'error'),
            message: String((src as ApiErrorBody).message ?? (typeof detail === 'string' ? detail : res.statusText)),
            used_by: (src as ApiErrorBody).used_by,
          };
        }
      } catch {
        /* non-JSON error body */
      }
      throw new ApiError(res.status, errBody?.message || `${method} ${path} failed (${res.status})`, errBody);
    }
    return res;
  }

  async function get<T>(path: string): Promise<Served<T>> {
    const res = await request('GET', path);
    const header = (res.headers.get('X-Served-By') || 'mongodb').toLowerCase() as ServedBy;
    return { data: (await res.json()) as T, servedBy: SERVED_BY.includes(header) ? header : 'mongodb' };
  }

  async function send<T>(method: string, path: string, body?: unknown): Promise<T> {
    const res = await request(method, path, body);
    return (await res.json()) as T;
  }

  async function blob(path: string): Promise<Blob> {
    const res = await request('GET', path);
    return res.blob();
  }

  return {
    mode: 'http',
    getHealth: () => get('/health'),

    listDatasets: () => get('/datasets'),
    importDatasets: (body) => send('POST', '/datasets/import', body),
    deleteDataset: (id) => send('DELETE', `/datasets/${id}`),

    listSignals: () => get('/signals'),
    getSignal: (id) => get(`/signals/${id}`),
    createSignal: (body) => send('POST', '/signals', body),
    updateSignal: (id, body) => send('PUT', `/signals/${id}`, body),
    deleteSignal: (id) => send('DELETE', `/signals/${id}`),

    listExperiments: (f = {}) => get(`/experiments${qs({ status: f.status, tag: f.tag, q: f.q })}`),
    getExperiment: (id) => get(`/experiments/${id}`),
    createExperiment: (body) => send('POST', '/experiments', body),
    updateExperiment: (id, body) => send('PUT', `/experiments/${id}`, body),
    deleteExperiment: (id) => send('DELETE', `/experiments/${id}`),
    cloneExperiment: (id) => send('POST', `/experiments/${id}/clone`),
    launchExperiment: (id) => send('POST', `/experiments/${id}/launch`),
    listRuns: (id) => get(`/experiments/${id}/runs`),
    exportExperimentCsv: (id) => blob(`/experiments/${id}/export.csv`),

    getRun: (id) => get(`/runs/${id}`),
    cancelRun: (id) => send('POST', `/runs/${id}/cancel`),
    getReadings: (runId, q) =>
      get(`/runs/${runId}/readings${qs({ signal_id: q.signal_id, symbol: q.symbol, from: q.from, to: q.to, max_points: q.max_points ?? 2000 })}`),
    getFaults: (runId) => get(`/runs/${runId}/faults`),
    exportRunCsv: (id) => blob(`/runs/${id}/export.csv`),
    openRunLive: (runId, handlers: LiveHandlers) => {
      const wsBase = baseUrl.replace(/^http/, 'ws');
      return connectLiveSocket(`${wsBase}/ws/runs/${runId}/live`, handlers);
    },

    getQueue: () => get('/queue'),

    listAnnotations: (targetType, targetId) => get(`/annotations${qs({ target_type: targetType, target_id: targetId })}`),
    createAnnotation: (body) => send('POST', '/annotations', body),
    updateAnnotation: (id, body) => send('PUT', `/annotations/${id}`, body),
    deleteAnnotation: (id) => send('DELETE', `/annotations/${id}`),

    getAudit: () => get('/audit'),
    repairAudit: (body) => send('POST', '/audit/repair', body),
  };
}
