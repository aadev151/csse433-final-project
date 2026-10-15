import { useMemo, useState } from 'react';
import { Badge, Button, Group, Menu, Select, Table, Text, TextInput, Tooltip } from '@mantine/core';
import { useDebouncedValue } from '@mantine/hooks';
import { Link, useNavigate } from 'react-router-dom';
import type { Experiment, ExperimentStatus } from '../api/types';
import { ConfirmModal } from '../components/ConfirmModal';
import { ExperimentStatusBadge, Mono } from '../components/badges';
import { IconPlus } from '../components/icons';
import { EmptyState, ErrorState, LoadingState, PageHeader } from '../components/states';
import { useExperiments } from '../hooks/queries';
import { useExperimentActions } from '../hooks/useExperimentActions';
import { fmtAgo } from '../lib/format';

export function ExperimentsPage() {
  const navigate = useNavigate();
  const [status, setStatus] = useState<string | null>(null);
  const [tag, setTag] = useState<string | null>(null);
  const [text, setText] = useState('');
  const [q] = useDebouncedValue(text.trim(), 250);
  const filters = { status: (status ?? undefined) as ExperimentStatus | undefined, tag: tag ?? undefined, q: q || undefined };
  const list = useExperiments(filters);
  const all = useExperiments();
  const allTags = useMemo(() => [...new Set((all.data?.data ?? []).flatMap((e) => e.tags))].sort(), [all.data]);
  const [toDelete, setToDelete] = useState<Experiment | null>(null);
  const { clone, remove } = useExperimentActions({ afterDelete: () => setToDelete(null) });
  const filtered = !!(status || tag || q);

  return (
    <>
      <PageHeader
        title="Experiments"
        subtitle="Saved plans: symbols, dates, signals and a grid of fault settings. Each grid cell becomes one run."
        servedBy={list.data?.servedBy}
        actions={
          <Button component={Link} to="/experiments/new" leftSection={<IconPlus size={16} />}>
            New experiment
          </Button>
        }
      />
      <Group mb="sm" gap="xs">
        <TextInput placeholder="Search by name" value={text} onChange={(e) => setText(e.currentTarget.value)} w={240} size="sm" />
        <Select placeholder="Any status" clearable data={['draft', 'queued', 'running', 'done', 'failed']} value={status} onChange={setStatus} w={150} size="sm" />
        <Select placeholder="Any tag" clearable searchable data={allTags} value={tag} onChange={setTag} w={170} size="sm" />
      </Group>

      {list.isPending ? (
        <LoadingState />
      ) : list.isError ? (
        <ErrorState error={list.error} onRetry={() => list.refetch()} />
      ) : list.data.data.length === 0 ? (
        filtered ? (
          <EmptyState title="No experiments match these filters" action={<Button variant="default" onClick={() => (setText(''), setStatus(null), setTag(null))}>Clear filters</Button>} />
        ) : (
          <EmptyState
            title="No experiments yet"
            message="Design an experiment to replay market data through a faulty Cassandra cluster and measure how signals degrade."
            action={
              <Button component={Link} to="/experiments/new">
                New experiment
              </Button>
            }
          />
        )
      ) : (
        <Table.ScrollContainer minWidth={900}>
          <Table highlightOnHover>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Name</Table.Th>
                <Table.Th>Symbols</Table.Th>
                <Table.Th>Dates</Table.Th>
                <Table.Th className="num">Signals</Table.Th>
                <Table.Th className="num">Runs</Table.Th>
                <Table.Th>Status</Table.Th>
                <Table.Th>Tags</Table.Th>
                <Table.Th>Updated</Table.Th>
                <Table.Th />
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {list.data.data.map((e) => (
                <Table.Tr key={e.id} className="clickable-row" onClick={() => navigate(`/experiments/${e.id}`)}>
                  <Table.Td fw={500}>{e.name}</Table.Td>
                  <Table.Td>{e.symbols.join(', ')}</Table.Td>
                  <Table.Td>
                    <Mono>{e.dates.start === e.dates.end ? e.dates.start : `${e.dates.start} → ${e.dates.end}`}</Mono>
                  </Table.Td>
                  <Table.Td className="num">{e.signal_ids.length}</Table.Td>
                  <Table.Td className="num">{e.run_count}</Table.Td>
                  <Table.Td>
                    <ExperimentStatusBadge status={e.status} />
                  </Table.Td>
                  <Table.Td>
                    <Group gap={4}>
                      {e.tags.map((t) => (
                        <Badge key={t} size="xs" variant="default" tt="none">
                          {t}
                        </Badge>
                      ))}
                    </Group>
                  </Table.Td>
                  <Table.Td>
                    <Tooltip label={e.updated_at}>
                      <Text size="xs">{fmtAgo(e.updated_at)}</Text>
                    </Tooltip>
                  </Table.Td>
                  <Table.Td onClick={(ev) => ev.stopPropagation()}>
                    <Group justify="flex-end" gap={4} wrap="nowrap">
                      <Button size="compact-xs" variant="subtle" component={Link} to={`/experiments/${e.id}`}>
                        Open
                      </Button>
                      <Menu position="bottom-end" withinPortal>
                        <Menu.Target>
                          <Button size="compact-xs" variant="subtle" color="gray" aria-label="More actions">
                            •••
                          </Button>
                        </Menu.Target>
                        <Menu.Dropdown>
                          <Menu.Item onClick={() => navigate(`/experiments/${e.id}/edit`)}>Edit</Menu.Item>
                          <Menu.Item onClick={() => clone.mutate(e)}>Clone</Menu.Item>
                          <Menu.Divider />
                          <Menu.Item color="red" onClick={() => setToDelete(e)}>
                            Delete
                          </Menu.Item>
                        </Menu.Dropdown>
                      </Menu>
                    </Group>
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
      )}
      <ConfirmModal
        opened={!!toDelete}
        title="Delete experiment?"
        message={
          <>
            Delete <b>{toDelete?.name}</b> and all {toDelete?.run_count ?? 0} of its runs and their results? This cannot be undone.
          </>
        }
        loading={remove.isPending}
        onConfirm={() => toDelete && remove.mutate(toDelete)}
        onClose={() => setToDelete(null)}
      />
    </>
  );
}
