import { useEffect, useReducer, useState } from 'react';
import { Affix, Badge, Button, Divider, Group, Paper, Stack, Switch, Text, Tooltip } from '@mantine/core';
import { useQueryClient } from '@tanstack/react-query';
import { STORE_NAMES, type StoreName } from '../../api/types';
import { mockServer } from '../../api/mock/devControls';
import { STORE_LABEL } from '../../lib/format';
import { IconWrench, IconX } from '../icons';

/** Mock-mode only: floating panel to take simulated databases up or down (outage rehearsal). */
export function DevPanel() {
  const [open, setOpen] = useState(false);
  const [, rerender] = useReducer((x: number) => x + 1, 0);
  const qc = useQueryClient();

  useEffect(() => mockServer.subscribe(rerender), []);

  const dev = mockServer.dev;
  const pending = mockServer.pendingCounts;
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ['health'] });
  };
  const setStore = (s: StoreName, up: boolean) => {
    mockServer.setStore(s, up);
    refresh();
  };
  const setAll = (up: boolean) => {
    STORE_NAMES.forEach((s) => mockServer.setStore(s, up));
    refresh();
  };

  return (
    <Affix position={{ bottom: 16, right: 16 }} zIndex={300}>
      {open ? (
        <Paper withBorder shadow="lg" p="md" radius="md" w={300}>
          <Group justify="space-between" mb="xs">
            <Group gap={6}>
              <IconWrench size={16} />
              <Text fw={700} size="sm">
                Developer panel
              </Text>
              <Badge size="xs" variant="light" color="grape">
                mock
              </Badge>
            </Group>
            <Button variant="subtle" size="compact-xs" onClick={() => setOpen(false)} aria-label="Close developer panel">
              <IconX size={14} />
            </Button>
          </Group>
          <Text size="xs" c="dimmed" mb="sm">
            Simulate the professor turning databases off. Pending writes drain over ~5 s after a store comes back.
          </Text>
          <Stack gap="xs">
            {STORE_NAMES.map((s) => (
              <Group key={s} justify="space-between">
                <Switch
                  checked={dev.stores[s]}
                  onChange={(e) => setStore(s, e.currentTarget.checked)}
                  color="green"
                  label={`${STORE_LABEL[s]} ${dev.stores[s] ? 'up' : 'down'}`}
                />
                {pending[s] > 0 && (
                  <Badge size="xs" color="yellow" variant="filled" c="dark">
                    {pending[s]} pending
                  </Badge>
                )}
              </Group>
            ))}
            <Group gap="xs" grow>
              <Button size="compact-xs" variant="light" color="red" onClick={() => setAll(false)}>
                All down
              </Button>
              <Button size="compact-xs" variant="light" color="green" onClick={() => setAll(true)}>
                All up
              </Button>
            </Group>
            <Divider my={4} />
            <Tooltip label="Cassandra stays up with 2/3 nodes (cass3 DN)." position="left">
              <Switch size="xs" checked={dev.nodeDown} onChange={(e) => (mockServer.setNodeDown(e.currentTarget.checked), refresh())} label="Take node cass3 down" />
            </Tooltip>
            <Tooltip label="Every API call except /health returns 500 — use it to see error states." position="left">
              <Switch size="xs" color="red" checked={dev.failRequests} onChange={(e) => (mockServer.setFailRequests(e.currentTarget.checked), qc.invalidateQueries())} label="Fail API requests" />
            </Tooltip>
            <Divider my={4} />
            <Group gap="xs" grow>
              <Button size="compact-xs" variant="default" onClick={() => (mockServer.reset(false), qc.invalidateQueries())}>
                Reset seed data
              </Button>
              <Button size="compact-xs" variant="default" onClick={() => (mockServer.reset(true), qc.invalidateQueries())}>
                Clear all data
              </Button>
            </Group>
          </Stack>
        </Paper>
      ) : (
        <Tooltip label="Developer panel (mock mode)" position="left">
          <Button size="xs" radius="xl" variant="filled" color="grape" onClick={() => setOpen(true)} leftSection={<IconWrench size={14} />}>
            Dev
            {STORE_NAMES.some((s) => !dev.stores[s]) && (
              <Badge size="xs" color="red" variant="white" ml={6}>
                outage
              </Badge>
            )}
          </Button>
        </Tooltip>
      )}
    </Affix>
  );
}
