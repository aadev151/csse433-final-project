import { useQuery } from '@tanstack/react-query';
import { api } from '../api';
import type { Health } from '../api/types';

export function useHealth() {
  return useQuery({
    queryKey: ['health'],
    queryFn: () => api.getHealth().then((r) => r.data),
    refetchInterval: 2000,
    retry: false,
    staleTime: 0,
  });
}

export interface StoreStatus {
  health: Health | undefined;
  /** true when /health itself cannot be reached */
  apiDown: boolean;
  cassandraUp: boolean;
  mongodbUp: boolean;
  redisUp: boolean;
  mode: Health['mode'] | 'unknown';
}

/** Convenience view of health. Stores are assumed up until health says otherwise. */
export function useStoreStatus(): StoreStatus {
  const q = useHealth();
  const h = q.data;
  return {
    health: h,
    apiDown: q.isError && !h,
    cassandraUp: h ? h.stores.cassandra.up : true,
    mongodbUp: h ? h.stores.mongodb.up : true,
    redisUp: h ? h.stores.redis.up : true,
    mode: h ? h.mode : 'unknown',
  };
}
