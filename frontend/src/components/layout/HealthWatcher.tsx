import { useEffect, useRef } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { notifications } from '@mantine/notifications';
import type { StoreName } from '../../api/types';
import { STORE_NAMES } from '../../api/types';
import { useHealth } from '../../hooks/useHealth';
import { STORE_LABEL } from '../../lib/format';

/**
 * Watches health transitions: refetches every query when a store goes down or
 * comes back (so "served from" badges and outage fallbacks update), and shows
 * "X is back and fully synced." once a recovered store's backlog drains to 0.
 */
export function HealthWatcher() {
  const { data } = useHealth();
  const qc = useQueryClient();
  const prev = useRef<Record<StoreName, boolean> | null>(null);
  const recovering = useRef(new Set<StoreName>());

  useEffect(() => {
    if (!data) return;
    const now: Record<StoreName, boolean> = {
      cassandra: data.stores.cassandra.up,
      mongodb: data.stores.mongodb.up,
      redis: data.stores.redis.up,
    };
    const before = prev.current;
    prev.current = now;
    if (before) {
      let changed = false;
      for (const s of STORE_NAMES) {
        if (before[s] === now[s]) continue;
        changed = true;
        if (now[s]) {
          recovering.current.add(s);
        } else {
          recovering.current.delete(s);
          notifications.show({ id: `down-${s}`, color: 'red', title: `${STORE_LABEL[s]} is down`, message: 'The app keeps working; see the banner for what is affected.', autoClose: 5000 });
        }
      }
      if (changed) qc.invalidateQueries({ predicate: (q) => q.queryKey[0] !== 'health' });
    }
    for (const s of [...recovering.current]) {
      if (now[s] && data.pending_writes[s] === 0) {
        recovering.current.delete(s);
        notifications.show({ id: `synced-${s}`, color: 'green', title: `${STORE_LABEL[s]} is back and fully synced.`, message: 'All pending writes have been applied.', autoClose: 5000 });
      }
    }
  }, [data, qc]);

  return null;
}
