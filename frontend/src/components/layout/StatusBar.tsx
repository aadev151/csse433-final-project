import { Badge, Group, HoverCard, Popover, Stack, Table, Text, Tooltip, UnstyledButton } from '@mantine/core';
import type { StoreName } from '../../api/types';
import { useHealth } from '../../hooks/useHealth';
import { STORE_LABEL, fmtMs } from '../../lib/format';

function Dot({ up }: { up: boolean | null }) {
  const color = up === null ? 'var(--mantine-color-gray-5)' : up ? 'var(--mantine-color-green-6)' : 'var(--mantine-color-red-6)';
  return <span style={{ display: 'inline-block', width: 8, height: 8, borderRadius: 8, background: color, flexShrink: 0 }} />;
}

function Pill({ store, up, extra, pending }: { store: StoreName; up: boolean | null; extra?: string; pending: number }) {
  return (
    <Group gap={6} wrap="nowrap">
      <Badge
        variant="light"
        radius="sm"
        size="lg"
        color={up === null ? 'gray' : up ? 'green' : 'red'}
        tt="none"
        fw={500}
        leftSection={<Dot up={up} />}
        style={{ cursor: 'default' }}
      >
        {STORE_LABEL[store]}
        {extra ? ` · ${extra}` : ''}
        {up === false ? ' · down' : ''}
      </Badge>
      {pending > 0 && (
        <Tooltip label={`${pending} write${pending === 1 ? '' : 's'} saved elsewhere, waiting to sync to ${STORE_LABEL[store]}`}>
          <Badge variant="filled" color="yellow" radius="sm" size="sm" tt="none" c="dark">
            {pending} pending
          </Badge>
        </Tooltip>
      )}
    </Group>
  );
}

/** The three store pills in the top bar. */
export function StatusBar() {
  const q = useHealth();
  const h = q.data;

  if (!h) {
    return (
      <Group gap="xs">
        <Badge variant="light" color={q.isError ? 'red' : 'gray'} radius="sm" size="lg" tt="none" fw={500} leftSection={<Dot up={q.isError ? false : null} />}>
          {q.isError ? 'API unreachable' : 'Checking databases…'}
        </Badge>
      </Group>
    );
  }

  const c = h.stores.cassandra;
  const nodesUp = c.nodes.filter((n) => n.status === 'UN').length;
  const latencyLabel = (up: boolean, ms: number | null) => (up ? `Up · ping ${fmtMs(ms)}` : 'Down — not responding');

  return (
    <Group gap="sm" wrap="nowrap">
      <Popover position="bottom" withArrow shadow="md">
        <Popover.Target>
          <UnstyledButton aria-label="Cassandra nodes">
            <Tooltip label={`${latencyLabel(c.up, c.latency_ms)} · click for nodes`}>
              <div>
                <Pill store="cassandra" up={c.up} extra={`${nodesUp}/${c.nodes.length} nodes`} pending={h.pending_writes.cassandra} />
              </div>
            </Tooltip>
          </UnstyledButton>
        </Popover.Target>
        <Popover.Dropdown>
          <Stack gap={4}>
            <Text size="xs" fw={600}>
              Cassandra cluster (replication factor 3)
            </Text>
            <Table withRowBorders={false} verticalSpacing={2} horizontalSpacing="xs" fz="xs">
              <Table.Tbody>
                {c.nodes.map((n) => (
                  <Table.Tr key={n.name}>
                    <Table.Td className="mono">{n.name}</Table.Td>
                    <Table.Td>
                      <Badge size="xs" radius="sm" color={n.status === 'UN' ? 'green' : 'red'} variant="light">
                        {n.status}
                      </Badge>
                    </Table.Td>
                    <Table.Td c="dimmed">{n.status === 'UN' ? 'up, normal' : 'down'}</Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
            <Text size="xs" c="dimmed">
              Ping {fmtMs(c.latency_ms)}
            </Text>
          </Stack>
        </Popover.Dropdown>
      </Popover>
      {(['mongodb', 'redis'] as const).map((s) => (
        <HoverCard key={s} openDelay={150} position="bottom" withArrow>
          <HoverCard.Target>
            <div>
              <Pill store={s} up={h.stores[s].up} pending={h.pending_writes[s]} />
            </div>
          </HoverCard.Target>
          <HoverCard.Dropdown>
            <Text size="xs">{latencyLabel(h.stores[s].up, h.stores[s].latency_ms)}</Text>
          </HoverCard.Dropdown>
        </HoverCard>
      ))}
    </Group>
  );
}
