import { useMemo, useState } from 'react';
import { Alert, Badge, Button, Drawer, Group, MultiSelect, NumberInput, SegmentedControl, Select, Stack, Table, Text, TextInput, Textarea, Tooltip } from '@mantine/core';
import { useForm } from '@mantine/form';
import { api } from '../api';
import type { Signal, SignalInput, SignalType } from '../api/types';
import { ConfirmModal } from '../components/ConfirmModal';
import { ParamsEditor } from '../components/forms/ParamsEditor';
import { paramsToRows, rowsToParams, type ParamRow } from '../lib/params';
import { IconPlus } from '../components/icons';
import { SignalTypeBadge } from '../components/badges';
import { EmptyState, ErrorState, LoadingState, PageHeader } from '../components/states';
import { qk, useSignals } from '../hooks/queries';
import { useWriteMutation } from '../hooks/useWriteMutation';
import { fmtAgo, fmtWindow } from '../lib/format';

type DrawerState = { mode: 'create' | 'edit' | 'view'; signal?: Signal; prefill?: Partial<Signal> } | null;

interface FormValues {
  name: string;
  type: SignalType;
  inputs: string[];
  window_ms: number;
  description: string;
  params: ParamRow[];
}

function SignalDrawer({ state, onClose, onDuplicate }: { state: NonNullable<DrawerState>; onClose: () => void; onDuplicate: (s: Signal) => void }) {
  const src = state.signal ?? state.prefill;
  const readOnly = state.mode === 'view';
  const form = useForm<FormValues>({
    initialValues: {
      name: src?.name ?? '',
      type: src?.type ?? 'latest-value',
      inputs: src?.inputs ?? ['quotes'],
      window_ms: src?.window_ms ?? 0,
      description: src?.description ?? '',
      params: paramsToRows(src?.params ?? {}),
    },
    validate: {
      name: (v) => (v.trim() ? null : 'Name is required'),
      inputs: (v) => (v.length ? null : 'Pick at least one input'),
      window_ms: (v, values) =>
        v < 0 ? 'Must be 0 or more' : values.type === 'running-total' && v <= 0 ? 'Running-total signals need a window > 0' : null,
      params: (rows) => {
        const keys = rows.map((r) => r.key.trim());
        if (keys.some((k) => !k)) return 'Every parameter needs a key';
        if (new Set(keys).size !== keys.length) return 'Parameter keys must be unique';
        return null;
      },
    },
  });

  const save = useWriteMutation({
    mutationFn: (body: SignalInput) => (state.mode === 'edit' && state.signal ? api.updateSignal(state.signal.id, body) : api.createSignal(body)),
    action: state.mode === 'edit' ? 'Signal updated' : 'Signal created',
    invalidate: [qk.signals],
    onSuccess: onClose,
  });

  const submit = form.onSubmit((v) =>
    save.mutate({
      name: v.name.trim(),
      type: v.type,
      inputs: v.inputs as SignalInput['inputs'],
      window_ms: v.window_ms,
      description: v.description,
      params: rowsToParams(v.params),
      ...(state.signal ? { version: state.signal.version } : {}),
    }),
  );

  return (
    <form onSubmit={submit}>
      <Stack>
        {readOnly && (
          <Alert color="gray" variant="light">
            Built-in signals are read-only. Duplicate it to make an editable copy.
          </Alert>
        )}
        <TextInput label="Name" required readOnly={readOnly} {...form.getInputProps('name')} />
        <Stack gap={4}>
          <Text size="sm" fw={500}>
            Type
          </Text>
          <SegmentedControl
            disabled={readOnly}
            data={[
              { value: 'latest-value', label: 'latest-value' },
              { value: 'running-total', label: 'running-total' },
            ]}
            {...form.getInputProps('type')}
          />
          <Text size="xs" c="dimmed">
            {form.values.type === 'latest-value'
              ? 'Needs only the most recent quote (e.g. micro-price, spread).'
              : 'Adds up a sequence of trades over a time window (e.g. order flow imbalance, VWAP).'}
          </Text>
        </Stack>
        <MultiSelect
          label="Inputs"
          data={[
            { value: 'trades', label: 'trades' },
            { value: 'quotes', label: 'quotes (best bid/ask)' },
          ]}
          readOnly={readOnly}
          {...form.getInputProps('inputs')}
        />
        <NumberInput label="Window (ms)" description="0 = instantaneous" min={0} step={100} thousandSeparator="," readOnly={readOnly} {...form.getInputProps('window_ms')} />
        <Textarea label="Description" autosize minRows={2} readOnly={readOnly} {...form.getInputProps('description')} />
        <ParamsEditor value={form.values.params} onChange={(rows) => form.setFieldValue('params', rows)} readOnly={readOnly} />
        {form.errors.params && (
          <Text size="xs" c="red">
            {form.errors.params}
          </Text>
        )}
        <Group justify="flex-end" mt="md">
          <Button variant="default" onClick={onClose}>
            {readOnly ? 'Close' : 'Cancel'}
          </Button>
          {readOnly && state.signal ? (
            <Button onClick={() => onDuplicate(state.signal!)}>Duplicate to edit</Button>
          ) : (
            <Button type="submit" loading={save.isPending}>
              {state.mode === 'edit' ? 'Save changes' : 'Create signal'}
            </Button>
          )}
        </Group>
      </Stack>
    </form>
  );
}

export function SignalsPage() {
  const q = useSignals();
  const [typeFilter, setTypeFilter] = useState<string | null>(null);
  const [builtinFilter, setBuiltinFilter] = useState<string | null>(null);
  const [text, setText] = useState('');
  const [drawer, setDrawer] = useState<DrawerState>(null);
  const [toDelete, setToDelete] = useState<Signal | null>(null);

  const del = useWriteMutation({
    mutationFn: (s: Signal) => api.deleteSignal(s.id),
    action: (s) => `Signal “${s.name}” deleted`,
    invalidate: [qk.signals],
    onSuccess: () => setToDelete(null),
    onError: () => {
      setToDelete(null);
    },
  });

  const rows = useMemo(() => {
    const list = q.data?.data ?? [];
    return list
      .filter((s) => !typeFilter || s.type === typeFilter)
      .filter((s) => !builtinFilter || (builtinFilter === 'builtin' ? s.builtin : !s.builtin))
      .filter((s) => !text || s.name.toLowerCase().includes(text.toLowerCase()))
      .sort((a, b) => a.type.localeCompare(b.type) || a.name.localeCompare(b.name));
  }, [q.data, typeFilter, builtinFilter, text]);

  const duplicate = (s: Signal) => setDrawer({ mode: 'create', prefill: { ...s, name: `${s.name} (custom)` } });

  return (
    <>
      <PageHeader
        title="Signals"
        subtitle="Market signals computed from what is read back from Cassandra and compared with ground truth."
        servedBy={q.data?.servedBy}
        actions={
          <Button leftSection={<IconPlus size={16} />} onClick={() => setDrawer({ mode: 'create' })}>
            New signal
          </Button>
        }
      />
      <Group mb="sm" gap="xs">
        <TextInput placeholder="Filter by name" value={text} onChange={(e) => setText(e.currentTarget.value)} w={220} size="sm" />
        <Select placeholder="Any type" clearable data={['latest-value', 'running-total']} value={typeFilter} onChange={setTypeFilter} w={170} size="sm" />
        <Select
          placeholder="Built-in & custom"
          clearable
          data={[
            { value: 'builtin', label: 'Built-in only' },
            { value: 'custom', label: 'Custom only' },
          ]}
          value={builtinFilter}
          onChange={setBuiltinFilter}
          w={170}
          size="sm"
        />
      </Group>

      {q.isPending ? (
        <LoadingState />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : q.data.data.length === 0 ? (
        <EmptyState
          title="No signals yet"
          message="Signals are the numbers each run computes from market data, e.g. micro-price or VWAP."
          action={<Button onClick={() => setDrawer({ mode: 'create' })}>Create a signal</Button>}
        />
      ) : rows.length === 0 ? (
        <EmptyState title="No signals match these filters" action={<Button variant="default" onClick={() => (setText(''), setTypeFilter(null), setBuiltinFilter(null))}>Clear filters</Button>} />
      ) : (
        <Table.ScrollContainer minWidth={800}>
          <Table highlightOnHover>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Name</Table.Th>
                <Table.Th>Type</Table.Th>
                <Table.Th>Inputs</Table.Th>
                <Table.Th className="num">Window</Table.Th>
                <Table.Th>Built-in</Table.Th>
                <Table.Th>Updated</Table.Th>
                <Table.Th />
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {rows.map((s) => (
                <Table.Tr key={s.id} className="clickable-row" onClick={() => setDrawer({ mode: s.builtin ? 'view' : 'edit', signal: s })}>
                  <Table.Td>
                    <Text size="sm" fw={500}>
                      {s.name}
                    </Text>
                    <Text size="xs" c="dimmed" lineClamp={1} maw={360}>
                      {s.description}
                    </Text>
                  </Table.Td>
                  <Table.Td>
                    <SignalTypeBadge type={s.type} />
                  </Table.Td>
                  <Table.Td>
                    <Group gap={4}>
                      {s.inputs.map((i) => (
                        <Badge key={i} size="xs" variant="default" tt="none">
                          {i}
                        </Badge>
                      ))}
                    </Group>
                  </Table.Td>
                  <Table.Td className="num">{fmtWindow(s.window_ms)}</Table.Td>
                  <Table.Td>{s.builtin ? <Badge size="xs" variant="outline" color="gray">built-in</Badge> : <Text size="xs" c="dimmed">custom</Text>}</Table.Td>
                  <Table.Td>
                    <Tooltip label={s.updated_at}>
                      <Text size="xs">{fmtAgo(s.updated_at)}</Text>
                    </Tooltip>
                  </Table.Td>
                  <Table.Td onClick={(e) => e.stopPropagation()}>
                    <Group gap={4} justify="flex-end" wrap="nowrap">
                      {s.builtin ? (
                        <Button size="compact-xs" variant="subtle" onClick={() => duplicate(s)}>
                          Duplicate to edit
                        </Button>
                      ) : (
                        <>
                          <Button size="compact-xs" variant="subtle" onClick={() => setDrawer({ mode: 'edit', signal: s })}>
                            Edit
                          </Button>
                          <Button size="compact-xs" variant="subtle" color="red" onClick={() => setToDelete(s)}>
                            Delete
                          </Button>
                        </>
                      )}
                    </Group>
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
      )}

      <Drawer
        opened={!!drawer}
        onClose={() => setDrawer(null)}
        position="right"
        size="md"
        title={<Text fw={600}>{drawer?.mode === 'create' ? 'New signal' : drawer?.mode === 'edit' ? `Edit ${drawer.signal?.name}` : drawer?.signal?.name}</Text>}
      >
        {drawer && <SignalDrawer key={`${drawer.mode}-${drawer.signal?.id ?? drawer.prefill?.name ?? 'new'}`} state={drawer} onClose={() => setDrawer(null)} onDuplicate={duplicate} />}
      </Drawer>

      <ConfirmModal
        opened={!!toDelete}
        title="Delete signal?"
        message={
          <>
            Delete <b>{toDelete?.name}</b>? This cannot be undone. Signals used by an experiment cannot be deleted.
          </>
        }
        loading={del.isPending}
        onConfirm={() => toDelete && del.mutate(toDelete)}
        onClose={() => setToDelete(null)}
      />
    </>
  );
}
