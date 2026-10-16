import { useNavigate } from 'react-router-dom';
import { api } from '../api';
import type { Experiment } from '../api/types';
import { useWriteMutation } from './useWriteMutation';

/** Clone / delete / launch mutations shared by the experiments list and detail pages. */
export function useExperimentActions(opts: { afterDelete?: () => void } = {}) {
  const navigate = useNavigate();
  const clone = useWriteMutation({
    mutationFn: (e: Experiment) => api.cloneExperiment(e.id),
    action: (e) => `Cloned “${e.name}” as a new draft`,
    invalidate: [['experiments']],
    onSuccess: (res) => res.record && navigate(`/experiments/${res.record.id}/edit`),
  });
  const remove = useWriteMutation({
    mutationFn: (e: Experiment) => api.deleteExperiment(e.id),
    action: (e) => `Experiment “${e.name}” deleted`,
    invalidate: [['experiments'], ['queue']],
    onSuccess: () => opts.afterDelete?.(),
  });
  const launch = useWriteMutation({
    mutationFn: (id: string) => api.launchExperiment(id),
    action: (_id, res) => `Launched: ${res?.run_ids.length ?? 0} runs queued`,
    invalidate: [['experiments'], ['experiment'], ['runs'], ['queue']],
    onSuccess: (_res, id) => navigate(`/experiments/${id}`),
  });
  return { clone, remove, launch };
}
