import { useMemo, useState } from 'react';
import { Alert, Button, Group, Modal, Select, Stack, Table, Text, Tooltip } from '@mantine/core';
import { DatePickerInput } from '@mantine/dates';
import dayjs from 'dayjs';
import { api } from '../api';
import { SYMBOLS, type Dataset, type DatasetImportInput, type MarketSymbol, type SignalInputKind } from '../api/types';
import { ConfirmModal } from '../components/ConfirmModal';
import { DatasetStatusBadge, Mono } from '../components/badges';
import { IconCheck, IconPlus, IconX } from '../components/icons';
import { EmptyState, ErrorState, LoadingState, PageHeader } from '../components/states';
import { qk, useDatasets } from '../hooks/queries';
import { useWriteMutation } from '../hooks/useWriteMutation';
import { fmtAgo, fmtBytes, fmtInt } from '../lib/format';
import { dayCount } from '../lib/grid';

function ImportModal({ opened, onClose }: { opened: boolean; onClose: () => void }) {
  const [symbol, setSymbol] = useState<MarketSymbol>('BTCUSDT');
  const [kind, setKind] = useState<SignalInputKind>('trades');
  const [range, setRange] = useState<[Date | null, Date | null]>([null, null]);
  const start = range[0] ? dayjs(range[0]).format('YYYY-MM-DD') : null;
  const end = range[1] ? dayjs(range[1]).format('YYYY-MM-DD') : start;
  const n = start && end ? dayCount(start, end) : 0;

  const imp = useWriteMutation({
    mutationFn: (body: DatasetImportInput) => api.importDatasets(body),
    action: (b) => `Import of ${b.symbol} ${b.kind} started`,
    invalidate: [qk.datasets],
    onSuccess: () => {
      setRange([null, null]);
      onClose();
    },
  });

  return (
    <Modal opened={opened} onClose={onClose} title={<Text fw={600}>Import market data</Text>} centered>
      <Stack>
        <Text size="sm" c="dimmed">
          Downloads daily Binance files, verifies their checksums, and loads them for replay. One dataset is created per day.
        </Text>
        <Group grow>
          <Select label="Symbol" data={SYMBOLS} value={symbol} onChange={(v) => v && setSymbol(v as MarketSymbol)} allowDeselect={false} />
          <Select
            label="Kind"
            data={[
              { value: 'trades', label: 'trades' },
              { value: 'quotes', label: 'quotes (best bid/ask)' },
            ]}
            value={kind}
            onChange={(v) => v && setKind(v as SignalInputKind)}
            allowDeselect={false}
          />
        </Group>
        <DatePickerInput type="range" label="Days (UTC)" placeholder="Pick a start and end day" value={range} onChange={setRange} allowSingleDateInRange maxDate={new Date()} />
        {n > 0 && (
          <Alert color={n > 31 ? 'red' : 'blue'} variant="light">
            {n > 31 ? `That is ${n} days; import at most 31 at a time.` : `This will download ${n} file${n === 1 ? '' : 's'}.`}
          </Alert>
        )}
        <Group justify="flex-end">
          <Button variant="default" onClick={onClose}>
            Cancel
          </Button>
          <Button disabled={!start || !end || n > 31} loading={imp.isPending} onClick={() => start && end && imp.mutate({ symbol, kind, start, end })}>
            Import
          </Button>
        </Group>
      </Stack>
    </Modal>
  );
}

export function DatasetsPage() {
  const q = useDatasets();
  const [symbol, setSymbol] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [importOpen, setImportOpen] = useState(false);
  const [toDelete, setToDelete] = useState<Dataset | null>(null);

  const del = useWriteMutation({
    mutationFn: (d: Dataset) => api.deleteDataset(d.id),
    action: (d) => `Dataset ${d.symbol} ${d.kind} ${d.day} deleted`,
    invalidate: [qk.datasets],
    onSuccess: () => setToDelete(null),
  });

  const rows = useMemo(
    () => (q.data?.data ?? []).filter((d) => (!symbol || d.symbol === symbol) && (!status || d.status === status)),
    [q.data, symbol, status],
  );
  const inProgress = (q.data?.data ?? []).filter((d) => d.status === 'downloading' || d.status === 'verifying').length;

  return (
    <>
      <PageHeader
        title="Datasets"
        subtitle="Daily Binance trade and best bid/ask files available for replay."
        servedBy={q.data?.servedBy}
        actions={
          <Button leftSection={<IconPlus size={16} />} onClick={() => setImportOpen(true)}>
            Import data
          </Button>
        }
      />
      <Group mb="sm" gap="xs">
        <Select placeholder="All symbols" clearable data={SYMBOLS} value={symbol} onChange={setSymbol} w={160} size="sm" />
        <Select placeholder="Any status" clearable data={['downloading', 'verifying', 'ready', 'failed']} value={status} onChange={setStatus} w={160} size="sm" />
        {inProgress > 0 && (
          <Text size="xs" c="dimmed">
            {inProgress} import{inProgress === 1 ? '' : 's'} in progress · refreshing every 3 s
          </Text>
        )}
      </Group>

      {q.isPending ? (
        <LoadingState />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : q.data.data.length === 0 ? (
        <EmptyState
          title="No market data imported yet"
          message="Import at least one day of trades and quotes before designing an experiment."
          action={<Button onClick={() => setImportOpen(true)}>Import data</Button>}
        />
      ) : rows.length === 0 ? (
        <EmptyState title="No datasets match these filters" action={<Button variant="default" onClick={() => (setSymbol(null), setStatus(null))}>Clear filters</Button>} />
      ) : (
        <Table.ScrollContainer minWidth={760}>
          <Table highlightOnHover>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Symbol</Table.Th>
                <Table.Th>Kind</Table.Th>
                <Table.Th>Day</Table.Th>
                <Table.Th>Status</Table.Th>
                <Table.Th className="num">Rows</Table.Th>
                <Table.Th className="num">Size</Table.Th>
                <Table.Th>Checksum</Table.Th>
                <Table.Th>Created</Table.Th>
                <Table.Th />
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {rows.map((d) => (
                <Table.Tr key={d.id}>
                  <Table.Td fw={500}>{d.symbol}</Table.Td>
                  <Table.Td>{d.kind}</Table.Td>
                  <Table.Td>
                    <Mono>{d.day}</Mono>
                  </Table.Td>
                  <Table.Td>
                    {d.error ? (
                      <Tooltip label={d.error} multiline w={300}>
                        <span>
                          <DatasetStatusBadge status={d.status} />
                        </span>
                      </Tooltip>
                    ) : (
                      <DatasetStatusBadge status={d.status} />
                    )}
                  </Table.Td>
                  <Table.Td className="num">{fmtInt(d.row_count)}</Table.Td>
                  <Table.Td className="num">{fmtBytes(d.size_bytes)}</Table.Td>
                  <Table.Td>
                    {d.checksum_ok === null ? (
                      <Text size="xs" c="dimmed">
                        —
                      </Text>
                    ) : d.checksum_ok ? (
                      <Text c="green.7" component="span" aria-label="checksum ok">
                        <IconCheck size={16} />
                      </Text>
                    ) : (
                      <Text c="red.7" component="span" aria-label="checksum mismatch">
                        <IconX size={16} />
                      </Text>
                    )}
                  </Table.Td>
                  <Table.Td>
                    <Tooltip label={d.created_at}>
                      <Text size="xs">{fmtAgo(d.created_at)}</Text>
                    </Tooltip>
                  </Table.Td>
                  <Table.Td>
                    <Group justify="flex-end">
                      <Button size="compact-xs" variant="subtle" color="red" onClick={() => setToDelete(d)}>
                        Delete
                      </Button>
                    </Group>
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
      )}

      <ImportModal opened={importOpen} onClose={() => setImportOpen(false)} />
      <ConfirmModal
        opened={!!toDelete}
        title="Delete dataset?"
        message={
          <>
            Delete <b>{toDelete && `${toDelete.symbol} ${toDelete.kind} ${toDelete.day}`}</b>? Experiments covering this day can no longer be launched until it is imported again.
          </>
        }
        loading={del.isPending}
        onConfirm={() => toDelete && del.mutate(toDelete)}
        onClose={() => setToDelete(null)}
      />
    </>
  );
}
