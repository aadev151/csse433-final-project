import dayjs from 'dayjs';
import relativeTime from 'dayjs/plugin/relativeTime';
import utc from 'dayjs/plugin/utc';
import type { ActiveFault, ServedBy, StoreName } from '../api/types';
import { FAULT_LABEL } from './colors';

dayjs.extend(relativeTime);
dayjs.extend(utc);

export const STORE_LABEL: Record<StoreName, string> = { cassandra: 'Cassandra', mongodb: 'MongoDB', redis: 'Redis' };
export const SERVED_LABEL: Record<ServedBy, string> = { ...STORE_LABEL, snapshot: 'local snapshot' };

export function listStores(stores: StoreName[]): string {
  return stores.map((s) => STORE_LABEL[s]).join(', ');
}

export function fmtNum(x: number | null | undefined, digits = 2): string {
  if (x === null || x === undefined || Number.isNaN(x)) return '—';
  if (x !== 0 && Math.abs(x) < 10 ** -digits) return x.toExponential(1);
  return x.toLocaleString(undefined, { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

export function fmtInt(x: number | null | undefined): string {
  return x === null || x === undefined ? '—' : Math.round(x).toLocaleString();
}

export function fmtPct(fraction: number | null | undefined, digits = 1): string {
  return fraction === null || fraction === undefined ? '—' : `${(fraction * 100).toFixed(digits)}%`;
}

export function fmtMs(ms: number | null | undefined): string {
  if (ms === null || ms === undefined) return '—';
  if (ms >= 10_000) return `${(ms / 1000).toFixed(1)} s`;
  if (ms >= 100) return `${Math.round(ms)} ms`;
  return `${ms.toFixed(1)} ms`;
}

export function fmtBytes(b: number | null | undefined): string {
  if (b === null || b === undefined) return '—';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let i = 0;
  let v = b;
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024;
    i++;
  }
  return `${v.toFixed(i === 0 ? 0 : 1)} ${units[i]}`;
}

/** UTC timestamp, e.g. 2026-08-01 13:45:02 */
export function fmtTime(iso: string | null | undefined): string {
  return iso ? dayjs.utc(iso).format('YYYY-MM-DD HH:mm:ss') : '—';
}

export function fmtShortTime(iso: string | null | undefined): string {
  return iso ? dayjs.utc(iso).format('MMM D HH:mm') : '—';
}

export function fmtAgo(iso: string | null | undefined): string {
  return iso ? dayjs(iso).fromNow() : '—';
}

export function fmtDuration(ms: number): string {
  if (!Number.isFinite(ms) || ms <= 0) return '0 s';
  const s = Math.round(ms / 1000);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  if (h) return `${h} h ${m} min`;
  if (m) return `${m} min ${s % 60} s`;
  return `${s} s`;
}

export function fmtWindow(ms: number): string {
  if (!ms) return 'instant';
  if (ms % 60_000 === 0) return `${ms / 60_000} min`;
  if (ms % 1000 === 0) return `${ms / 1000} s`;
  return `${ms} ms`;
}

export function faultText(f: ActiveFault): string {
  const v = f.value === null ? '' : f.kind === 'packet_loss' ? ` ${f.value}%` : ` ${f.value} ms`;
  return `${FAULT_LABEL[f.kind]}${v} on ${f.target}`;
}

export function errorMessage(err: unknown): string {
  if (err instanceof Error) return err.message;
  return String(err);
}

export function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
