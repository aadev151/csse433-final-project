import { Button, Group, Text } from '@mantine/core';
import { notifications } from '@mantine/notifications';
import type { WriteInfo } from '../api/types';
import { ApiError } from '../api/client';
import { listStores } from './format';

/** Toast for a successful write: green when fully committed, amber when some stores are pending. */
export function notifyWrite(write: WriteInfo, what?: string) {
  if (write.stores_pending.length === 0) {
    notifications.show({ color: 'green', title: 'Saved.', message: what ?? 'Written to every database.', autoClose: 3000 });
  } else {
    notifications.show({
      color: 'yellow',
      title: `Saved. Waiting to sync to ${listStores(write.stores_pending)}.`,
      message: what ? `${what} — it will sync automatically when the database is back.` : 'It will sync automatically when the database is back.',
      autoClose: 6000,
    });
  }
}

/** Toast for a failed write, with a Retry action. */
export function notifyError(err: unknown, retry?: () => void, _what?: string) {
  const message = err instanceof ApiError || err instanceof Error ? err.message : String(err);
  const id = `err-${Date.now()}-${Math.random()}`;
  notifications.show({
    id,
    color: 'red',
    title: "Couldn't save — the request failed",
    autoClose: 10_000,
    message: (
      <Group justify="space-between" wrap="nowrap" gap="sm">
        <Text size="sm">{message}</Text>
        {retry && (
          <Button
            size="compact-xs"
            variant="light"
            color="red"
            onClick={() => {
              notifications.hide(id);
              retry();
            }}
          >
            Retry
          </Button>
        )}
      </Group>
    ),
  });
}
