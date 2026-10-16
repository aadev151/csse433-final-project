import { useState } from 'react';
import { Badge, Button, Group, Paper, SimpleGrid, Switch, Table, Text, Tooltip } from '@mantine/core';
import { notifications } from '@mantine/notifications';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '../api';
import { STORE_NAMES, type AuditRecord, type AuditRepairInput, type StoreName } from '../api/types';
import { ConfirmModal } from '../components/ConfirmModal';
import { Mono } from '../components/badges';
import { IconRefresh, IconShield } from '../components/icons';
import { EmptyState, ErrorState, LoadingState, PageHeader } from '../components/states';
import { useStoreStatus } from '../hooks/useHealth';
import { STORE_LABEL, fmtTime } from '../lib/format';
import { notifyError } from '../lib/notify';

const STATUS_COLOR = { match: 'green', mismatch: 'red', missing: 'yellow' } as const;

function Tile({ label, value, color }: { label: string; value: number; color?: string }) {
  return (
    <Paper withBorder p="md" radius="md">
      <Text size="xs" c="dimmed" tt="uppercase" fw={600}>
        {label}
      </Text>
      <Text fz={28} fw={650} c={value > 0 ? color : undefined}>
        {value.toLocaleString()}
      </Text>
    </Paper>
  );
}

function VersionCell({ rec, store, up }: { rec: AuditRecord; store: StoreName; up: boolean }) {
  const v = rec.versions[store];
  if (!up)
    return (
      <Tooltip label={`${STORE_LABEL[store]} is down, so its copy could not be checked.`}>
        <Text size="xs" c="dimmed">
          unreachable
        </Text>
      </Tooltip>
    );
  const others = STORE_NAMES.map((s) => rec.versions[s]).filter((x): x is number => x !== null);
  const newest = others.length ? Math.max(...others) : null;
  if (v === null)
    return (
      <Badge size="sm" color="yellow" variant="light" tt="none">
        missing
      </Badge>
    );
  const stale = newest !== null && v < newest;
  return (
    <Text size="sm" fw={stale ? 700 : 400} c={stale ? 'red.7' : undefined} className="mono">
      v{v}
      {stale ? ' (behind)' : ''}
    </Text>
  );
}

export function AuditPage() {
  const qc = useQueryClient();
  const [started, setStarted] = useState(false);
  const [showAll, setShowAll] = useState(false);
  const [confirmAll, setConfirmAll] = useState(false);
  const stores = useStoreStatus();
  const up: Record<StoreName, boolean> = { cassandra: stores.cassandraUp, mongodb: stores.mongodbUp, redis: stores.redisUp };

  const audit = useQuery({ queryKey: ['audit'], queryFn: () => api.getAudit(), enabled: started, staleTime: Infinity });

  const repair = useMutation({
    mutationFn: (body: AuditRepairInput) => api.repairAudit(body),
    onSuccess: (result, body) => {
      qc.setQueryData(['audit'], { data: result, servedBy: audit.data?.servedBy ?? 'mongodb' });
      qc.invalidateQueries({ queryKey: ['audit'] });
      qc.invalidateQueries({ queryKey: ['health'] });
      setConfirmAll(false);
      const left = result.summary.mismatched + result.summary.missing;
      notifications.show({
        color: left ? 'yellow' : 'green',
        title: 'all' in body ? 'Repair finished.' : 'Record repaired.',
        message: left ? `${left} record${left === 1 ? '' : 's'} still differ — some stores may be down.` : 'Every store now holds the same version.',
      });
    },
    onError: (err, body) => notifyError(err, () => repair.mutate(body)),
  });

  const records = audit.data?.data.records ?? [];
  const shown = showAll ? records : records.filter((r) => r.status !== 'match');
  const s = audit.data?.data.summary;

  return (
    <>
      <PageHeader
        title="Consistency audit"
        subtitle="Compares the version of every user record held by MongoDB (source of truth), Cassandra and Redis."
        servedBy={audit.data?.servedBy}
        actions={
          <>
            <Button leftSection={started ? <IconRefresh size={16} /> : <IconShield size={16} />} loading={audit.isFetching} onClick={() => (started ? audit.refetch() : setStarted(true))}>
              {started ? 'Run audit again' : 'Run audit'}
            </Button>
            <Button variant="light" color="red" disabled={!s || s.mismatched + s.missing === 0} onClick={() => setConfirmAll(true)}>
              Repair all
            </Button>
          </>
        }
      />
      {!started ? (
        <EmptyState
          title="No audit run yet"
          message="Run an audit to check that MongoDB, Cassandra and Redis all hold the same version of every signal, experiment, run, annotation and dataset."
          action={<Button onClick={() => setStarted(true)}>Run audit</Button>}
        />
      ) : audit.isPending ? (
        <LoadingState rows={6} />
      ) : audit.isError ? (
        <ErrorState error={audit.error} onRetry={() => audit.refetch()} />
      ) : (
        <>
          <SimpleGrid cols={{ base: 2, md: 4 }} mb="md">
            <Tile label="Total records" value={s!.total} />
            <Tile label="Matching" value={s!.matching} color="green.7" />
            <Tile label="Mismatched" value={s!.mismatched} color="red.7" />
            <Tile label="Missing" value={s!.missing} color="yellow.8" />
          </SimpleGrid>
          <Group justify="space-between" mb="sm">
            <Switch checked={showAll} onChange={(e) => setShowAll(e.currentTarget.checked)} label="Show matching records too" />
            <Text size="xs" c="dimmed">
              Checked <span className="mono">{fmtTime(audit.data.data.checked_at)}</span> UTC
            </Text>
          </Group>
          {shown.length === 0 ? (
            <EmptyState title="Everything matches" message={showAll ? 'There are no records yet.' : 'All three databases hold the same version of every record.'} />
          ) : (
            <Table.ScrollContainer minWidth={800}>
              <Table highlightOnHover>
                <Table.Thead>
                  <Table.Tr>
                    <Table.Th>Type</Table.Th>
                    <Table.Th>Name</Table.Th>
                    <Table.Th>MongoDB</Table.Th>
                    <Table.Th>Cassandra</Table.Th>
                    <Table.Th>Redis</Table.Th>
                    <Table.Th>Status</Table.Th>
                    <Table.Th />
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {shown.map((r) => (
                    <Table.Tr key={`${r.type}:${r.id}`}>
                      <Table.Td>{r.type}</Table.Td>
                      <Table.Td>
                        <Text size="sm">{r.name}</Text>
                        <Mono>{r.id}</Mono>
                      </Table.Td>
                      {(['mongodb', 'cassandra', 'redis'] as const).map((st) => (
                        <Table.Td key={st}>
                          <VersionCell rec={r} store={st} up={up[st]} />
                        </Table.Td>
                      ))}
                      <Table.Td>
                        <Badge size="sm" variant="light" color={STATUS_COLOR[r.status]} tt="none">
                          {r.status}
                        </Badge>
                      </Table.Td>
                      <Table.Td>
                        <Group justify="flex-end">
                          {r.status !== 'match' && (
                            <Button
                              size="compact-xs"
                              variant="subtle"
                              loading={repair.isPending && 'id' in (repair.variables ?? {}) && (repair.variables as { id: string }).id === r.id}
                              onClick={() => repair.mutate({ type: r.type, id: r.id })}
                            >
                              Repair
                            </Button>
                          )}
                        </Group>
                      </Table.Td>
                    </Table.Tr>
                  ))}
                </Table.Tbody>
              </Table>
            </Table.ScrollContainer>
          )}
        </>
      )}
      <ConfirmModal
        opened={confirmAll}
        title="Repair all records?"
        message={`Copy the MongoDB version of ${s ? s.mismatched + s.missing : 0} differing record(s) to every reachable store. Stores that are down are skipped.`}
        confirmLabel="Repair all"
        color="blue"
        loading={repair.isPending}
        onConfirm={() => repair.mutate({ all: true })}
        onClose={() => setConfirmAll(false)}
      />
    </>
  );
}
