import { useRef } from 'react';
import { useMutation, useQueryClient, type QueryKey } from '@tanstack/react-query';
import type { WriteInfo } from '../api/types';
import { ApiError } from '../api/client';
import { notifyError, notifyWrite } from '../lib/notify';

interface Options<V, R> {
  mutationFn: (vars: V) => Promise<R>;
  /** Short description of what happened, shown in the toast (e.g. "Signal created"). */
  action: string | ((vars: V, res?: R) => string);
  invalidate?: QueryKey[];
  onSuccess?: (res: R, vars: V) => void;
  /** Return true to suppress the default error toast (e.g. to show it inline instead). */
  onError?: (err: unknown, vars: V) => boolean | void;
}

/** useMutation + the app-wide write-result toasts (green / amber pending / red with Retry). */
export function useWriteMutation<V, R extends { write: WriteInfo }>(opts: Options<V, R>) {
  const qc = useQueryClient();
  const retryRef = useRef<(v: V) => void>(() => undefined);
  const label = (v: V, res?: R) => (typeof opts.action === 'function' ? opts.action(v, res) : opts.action);
  const m = useMutation<R, unknown, V>({
    mutationFn: opts.mutationFn,
    onSuccess: (res, vars) => {
      notifyWrite(res.write, label(vars, res));
      for (const key of opts.invalidate ?? []) qc.invalidateQueries({ queryKey: key });
      qc.invalidateQueries({ queryKey: ['health'] });
      opts.onSuccess?.(res, vars);
    },
    onError: (err, vars) => {
      if (opts.onError?.(err, vars)) return;
      // 4xx means retrying the same request cannot succeed, so only offer Retry for network/5xx failures
      const retryable = !(err instanceof ApiError && err.status >= 400 && err.status < 500);
      notifyError(err, retryable ? () => retryRef.current(vars) : undefined, label(vars));
    },
  });
  retryRef.current = m.mutate;
  return m;
}
