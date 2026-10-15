import { Alert, List, Text } from '@mantine/core';
import type { StoreName } from '../../api/types';
import { useStoreStatus } from '../../hooks/useHealth';
import { STORE_LABEL } from '../../lib/format';
import { IconAlert } from '../icons';

const IMPACT: Record<StoreName, string> = {
  cassandra:
    'Step-by-step run readings are unavailable (summaries still load). New and queued runs wait for Cassandra and start automatically when it returns.',
  mongodb: 'Everything still works. Pages are served from a replica copy and your changes will sync to MongoDB when it returns.',
  redis: 'Live run monitoring is off; run pages refresh every 5 seconds instead. Results appear when runs finish.',
};

/** Full-width banner shown under the top bar whenever health mode is not "normal". */
export function OutageBanner() {
  const { health, apiDown, mode } = useStoreStatus();

  if (apiDown) {
    return (
      <Alert color="red" radius={0} variant="filled" icon={<IconAlert />} title="Cannot reach the API server">
        The backend is not responding. Data on screen may be out of date; pages will recover automatically once it is back.
      </Alert>
    );
  }
  if (!health || mode === 'normal') return null;

  if (mode === 'offline') {
    return (
      <Alert color="red" radius={0} variant="filled" icon={<IconAlert />} title="All databases are down">
        All databases are down. Showing the last known data from the local snapshot. Changes you make are saved and will sync when databases come back.
      </Alert>
    );
  }

  const down = (Object.keys(STORE_LABEL) as StoreName[]).filter((s) => !health.stores[s].up);
  return (
    <Alert color="yellow" radius={0} variant="light" icon={<IconAlert />} title={`Degraded: ${down.map((s) => STORE_LABEL[s]).join(' and ')} ${down.length === 1 ? 'is' : 'are'} down`}>
      <List size="sm" spacing={2}>
        {down.map((s) => (
          <List.Item key={s}>
            <Text span fw={600} size="sm">
              {STORE_LABEL[s]}:
            </Text>{' '}
            {IMPACT[s]}
          </List.Item>
        ))}
      </List>
    </Alert>
  );
}
