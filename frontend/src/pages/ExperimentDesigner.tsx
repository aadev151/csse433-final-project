import { useMemo, type ReactNode } from 'react';
import {
  Alert,
  Anchor,
  Badge,
  Button,
  Checkbox,
  Divider,
  Grid,
  Group,
  MultiSelect,
  Paper,
  Select,
  SimpleGrid,
  Stack,
  TagsInput,
  Text,
  TextInput,
  Textarea,
  Title,
} from '@mantine/core';
import { DatePickerInput } from '@mantine/dates';
import { useForm } from '@mantine/form';
import dayjs from 'dayjs';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { api } from '../api';
import {
  CONSISTENCY_LEVELS,
  SYMBOLS,
  type Consistency,
  type Dataset,
  type Experiment,
  type ExperimentInput,
  type MarketSymbol,
  type NodeOutage,
  type Signal,
  type SignalInputKind,
  type SignalType,
} from '../api/types';
import { SignalTypeBadge } from '../components/badges';
import { ErrorState, LoadingState, PageHeader } from '../components/states';
import { qk, useDatasets, useExperiment, useSignals } from '../hooks/queries';
import { useWriteMutation } from '../hooks/useWriteMutation';
import { useExperimentActions } from '../hooks/useExperimentActions';
import { fmtDuration } from '../lib/format';
import { dayCount, daysBetween } from '../lib/grid';

interface FormValues {
  name: string;
  tags: string[];
  notes: string;
  symbols: string[];
  range: [Date | null, Date | null];
  signal_ids: string[];
  consistency: string[];
  delay_ms: string[];
  packet_loss_pct: string[];
  clock_skew_ms: string[];
  node_outage: string[];
  replay_speed: string;
}

const PRESETS = {
  delay_ms: ['0', '1', '5', '25', '100', '500'],
  packet_loss_pct: ['0', '1', '5', '10'],
  clock_skew_ms: ['0', '10', '50', '200'],
};

const toDate = (d: string) => dayjs(d).toDate();
const fmtDay = (d: Date | null) => (d ? dayjs(d).format('YYYY-MM-DD') : null);

function numberListError(values: string[], unit: string): string | null {
  if (values.length === 0) return 'Add at least one value';
  for (const v of values) {
    const n = Number(v);
    if (v.trim() === '' || Number.isNaN(n)) return `“${v}” is not a number`;
    if (n < 0) return `Values must be 0 or more (${unit})`;
  }
  if (new Set(values.map(Number)).size !== values.length) return 'Remove duplicate values';
  return null;
}

/** For each selected symbol, the days that have every needed data kind ready. */
function availability(datasets: Dataset[], symbols: string[], kinds: SignalInputKind[]) {
  const ready = new Set(datasets.filter((d) => d.status === 'ready').map((d) => `${d.symbol}|${d.kind}|${d.day}`));
  const allDays = [...new Set(datasets.map((d) => d.day))].sort();
  const available = new Set(allDays.filter((day) => symbols.length > 0 && symbols.every((s) => kinds.every((k) => ready.has(`${s}|${k}|${day}`)))));
  const missingFor = (day: string) => symbols.flatMap((s) => kinds.filter((k) => !ready.has(`${s}|${k}|${day}`)).map((k) => `${s} ${k}`));
  return { available, missingFor };
}

function SignalGroup({ type, signals, selected, onChange }: { type: SignalType; signals: Signal[]; selected: string[]; onChange: (ids: string[]) => void }) {
  const ids = signals.map((s) => s.id);
  const nSel = ids.filter((id) => selected.includes(id)).length;
  return (
    <Paper withBorder p="sm" radius="sm">
      <Group justify="space-between" mb={6}>
        <SignalTypeBadge type={type} />
        <Checkbox
          size="xs"
          label="Select all"
          checked={nSel === ids.length && ids.length > 0}
          indeterminate={nSel > 0 && nSel < ids.length}
          disabled={ids.length === 0}
          onChange={(e) => onChange(e.currentTarget.checked ? [...new Set([...selected, ...ids])] : selected.filter((x) => !ids.includes(x)))}
        />
      </Group>
      <Stack gap={6}>
        {signals.length === 0 && (
          <Text size="xs" c="dimmed">
            No {type} signals.
          </Text>
        )}
        {signals.map((s) => (
          <Checkbox
            key={s.id}
            size="sm"
            label={s.name}
            description={s.description}
            checked={selected.includes(s.id)}
            onChange={(e) => onChange(e.currentTarget.checked ? [...selected, s.id] : selected.filter((x) => x !== s.id))}
          />
        ))}
      </Stack>
    </Paper>
  );
}

function Section({ n, title, children }: { n: number; title: string; children: ReactNode }) {
  return (
    <Paper withBorder p="md" radius="md">
      <Title order={4} fz={15} mb="sm">
        {n}. {title}
      </Title>
      {children}
    </Paper>
  );
}

function DesignerForm({ experiment, signals, datasets }: { experiment?: Experiment; signals: Signal[]; datasets: Dataset[] }) {
  const navigate = useNavigate();
  const { launch } = useExperimentActions();
  const form = useForm<FormValues>({
    initialValues: {
      name: experiment?.name ?? '',
      tags: experiment?.tags ?? [],
      notes: experiment?.notes ?? '',
      symbols: experiment?.symbols ?? ['BTCUSDT'],
      range: experiment ? [toDate(experiment.dates.start), toDate(experiment.dates.end)] : [null, null],
      signal_ids: experiment?.signal_ids ?? [],
      consistency: experiment?.params.consistency ?? ['ONE', 'QUORUM', 'ALL'],
      delay_ms: (experiment?.params.delay_ms ?? [0, 25, 100]).map(String),
      packet_loss_pct: (experiment?.params.packet_loss_pct ?? [0]).map(String),
      clock_skew_ms: (experiment?.params.clock_skew_ms ?? [0]).map(String),
      node_outage: experiment?.params.node_outage ?? ['none'],
      replay_speed: String(experiment?.replay_speed ?? 10),
    },
    validate: {
      name: (v) => (v.trim() ? null : 'Give the experiment a name'),
      symbols: (v) => (v.length ? null : 'Pick at least one symbol'),
      range: (v) => (v[0] ? null : 'Pick a date range'),
      signal_ids: (v) => (v.length ? null : 'Pick at least one signal'),
      consistency: (v) => (v.length ? null : 'Pick at least one consistency level'),
      delay_ms: (v) => numberListError(v, 'ms'),
      packet_loss_pct: (v) => numberListError(v, '%') ?? (v.some((x) => Number(x) > 100) ? 'Packet loss cannot exceed 100%' : null),
      clock_skew_ms: (v) => numberListError(v, 'ms'),
      node_outage: (v) => (v.length ? null : 'Pick at least one option'),
    },
  });
  const v = form.values;

  const signalsByType = (t: SignalType) => signals.filter((s) => s.type === t).sort((a, b) => a.name.localeCompare(b.name));
  const kinds = useMemo<SignalInputKind[]>(() => {
    const k = new Set(signals.filter((s) => v.signal_ids.includes(s.id)).flatMap((s) => s.inputs));
    return k.size ? [...k] : ['trades', 'quotes'];
  }, [signals, v.signal_ids]);
  const { available, missingFor } = useMemo(() => availability(datasets, v.symbols, kinds), [datasets, v.symbols, kinds]);

  const start = fmtDay(v.range[0]);
  const end = fmtDay(v.range[1]) ?? start;
  const selectedDays = start && end ? daysBetween(start, end) : [];
  const missingDays = selectedDays.filter((d) => !available.has(d));

  // live preview
  const lens = {
    consistency: v.consistency.length,
    delay: v.delay_ms.length,
    loss: v.packet_loss_pct.length,
    skew: v.clock_skew_ms.length,
    outage: v.node_outage.length,
  };
  const runs = lens.consistency * lens.delay * lens.loss * lens.skew * lens.outage;
  const days = start && end ? dayCount(start, end) : 0;
  const speed = Number(v.replay_speed) || 1;
  const perRunMs = (days * 86_400_000) / speed;

  const buildBody = (): ExperimentInput => ({
    name: v.name.trim(),
    tags: v.tags,
    notes: v.notes,
    symbols: v.symbols as MarketSymbol[],
    dates: { start: start!, end: end! },
    signal_ids: v.signal_ids,
    params: {
      consistency: CONSISTENCY_LEVELS.filter((c) => v.consistency.includes(c)) as Consistency[],
      delay_ms: v.delay_ms.map(Number).sort((a, b) => a - b),
      packet_loss_pct: v.packet_loss_pct.map(Number).sort((a, b) => a - b),
      clock_skew_ms: v.clock_skew_ms.map(Number).sort((a, b) => a - b),
      node_outage: (['none', 'one_node_down'] as NodeOutage[]).filter((o) => v.node_outage.includes(o)),
    },
    replay_speed: speed,
    ...(experiment ? { version: experiment.version } : {}),
  });

  const save = useWriteMutation({
    mutationFn: ({ body }: { body: ExperimentInput; launchAfter: boolean }) => (experiment ? api.updateExperiment(experiment.id, body) : api.createExperiment(body)),
    action: experiment ? 'Experiment updated' : 'Experiment saved as draft',
    invalidate: [['experiments'], ...(experiment ? [qk.experiment(experiment.id)] : [])],
    onSuccess: (res, { launchAfter }) => {
      const id = res.record?.id ?? experiment?.id;
      if (!id) return;
      if (launchAfter) launch.mutate(id);
      else navigate(`/experiments/${id}`);
    },
  });

  const submit = (launchAfter: boolean) =>
    form.onSubmit(() => {
      if (missingDays.length) {
        form.setFieldError('range', 'Some selected days are missing data');
        return;
      }
      save.mutate({ body: buildBody(), launchAfter });
    })();

  const busy = save.isPending || launch.isPending;

  return (
    <form onSubmit={(e) => (e.preventDefault(), submit(false))}>
      <Grid gutter="md">
        <Grid.Col span={{ base: 12, md: 8 }}>
          <Stack gap="md">
            <Section n={1} title="Basics">
              <Stack gap="sm">
                <TextInput label="Name" placeholder="e.g. Delay sweep — BTC, Aug 1" required {...form.getInputProps('name')} />
                <TagsInput label="Tags" placeholder="Type a tag and press Enter" {...form.getInputProps('tags')} clearable />
                <Textarea label="Notes" autosize minRows={2} placeholder="What are you testing and why?" {...form.getInputProps('notes')} />
              </Stack>
            </Section>

            <Section n={2} title="Data">
              <Stack gap="sm">
                <MultiSelect label="Symbols" data={SYMBOLS} required {...form.getInputProps('symbols')} />
                <DatePickerInput
                  type="range"
                  label="Date range (UTC)"
                  placeholder={v.symbols.length ? 'Pick days with data' : 'Pick symbols first'}
                  allowSingleDateInRange
                  disabled={!v.symbols.length}
                  excludeDate={(d) => !available.has(dayjs(d).format('YYYY-MM-DD'))}
                  defaultDate={available.size ? toDate([...available][0]) : undefined}
                  required
                  {...form.getInputProps('range')}
                />
                <Group gap={6}>
                  <Text size="xs" c="dimmed">
                    Days with {kinds.join(' + ')} ready for {v.symbols.join(', ') || '—'}:
                  </Text>
                  {available.size === 0 ? (
                    <Text size="xs" c="dimmed">
                      none
                    </Text>
                  ) : (
                    [...available].map((d) => (
                      <Badge key={d} size="xs" variant="light" color="green" tt="none" className="mono">
                        {d}
                      </Badge>
                    ))
                  )}
                </Group>
                {(missingDays.length > 0 || (v.symbols.length > 0 && available.size === 0)) && (
                  <Alert color="yellow" variant="light" title="Missing market data">
                    {missingDays.length > 0 ? (
                      <Stack gap={2}>
                        {missingDays.slice(0, 6).map((d) => (
                          <Text key={d} size="sm">
                            <span className="mono">{d}</span>: missing {missingFor(d).join(', ')}
                          </Text>
                        ))}
                        {missingDays.length > 6 && <Text size="sm">…and {missingDays.length - 6} more days.</Text>}
                      </Stack>
                    ) : (
                      <Text size="sm">No day has every needed file for these symbols.</Text>
                    )}
                    <Anchor component={Link} to="/datasets" size="sm">
                      Import the missing days on the Datasets page →
                    </Anchor>
                  </Alert>
                )}
              </Stack>
            </Section>

            <Section n={3} title="Signals">
              <SimpleGrid cols={{ base: 1, sm: 2 }}>
                <SignalGroup type="latest-value" signals={signalsByType('latest-value')} selected={v.signal_ids} onChange={(ids) => form.setFieldValue('signal_ids', ids)} />
                <SignalGroup type="running-total" signals={signalsByType('running-total')} selected={v.signal_ids} onChange={(ids) => form.setFieldValue('signal_ids', ids)} />
              </SimpleGrid>
              {form.errors.signal_ids && (
                <Text size="xs" c="red" mt={6}>
                  {form.errors.signal_ids}
                </Text>
              )}
            </Section>

            <Section n={4} title="Test settings grid">
              <Text size="xs" c="dimmed" mb="sm">
                Every combination of the values below becomes one run. Replication factor is fixed at 3.
              </Text>
              <Stack gap="md">
                <Checkbox.Group label="Read consistency level" {...form.getInputProps('consistency')}>
                  <Group mt={6}>
                    {CONSISTENCY_LEVELS.map((c) => (
                      <Checkbox key={c} value={c} label={c} />
                    ))}
                  </Group>
                </Checkbox.Group>
                <TagsInput
                  label="Network delay (ms)"
                  description="Added to one replica's network link. Pick presets or type a value and press Enter."
                  data={PRESETS.delay_ms}
                  {...form.getInputProps('delay_ms')}
                />
                <SimpleGrid cols={{ base: 1, sm: 2 }}>
                  <TagsInput label="Packet loss (%)" data={PRESETS.packet_loss_pct} {...form.getInputProps('packet_loss_pct')} />
                  <TagsInput label="Clock skew (ms)" data={PRESETS.clock_skew_ms} {...form.getInputProps('clock_skew_ms')} />
                </SimpleGrid>
                <Group align="flex-start" gap="xl">
                  <Checkbox.Group label="Node outage" {...form.getInputProps('node_outage')}>
                    <Group mt={6}>
                      <Checkbox value="none" label="none" />
                      <Checkbox value="one_node_down" label="one node down" />
                    </Group>
                  </Checkbox.Group>
                  <Select
                    label="Replay speed"
                    w={140}
                    allowDeselect={false}
                    data={[
                      { value: '1', label: '1×' },
                      { value: '5', label: '5×' },
                      { value: '10', label: '10×' },
                      { value: '50', label: '50×' },
                    ]}
                    {...form.getInputProps('replay_speed')}
                  />
                </Group>
              </Stack>
            </Section>
          </Stack>
        </Grid.Col>

        <Grid.Col span={{ base: 12, md: 4 }}>
          <Paper withBorder p="md" radius="md" className="sticky-panel">
            <Text size="sm" c="dimmed">
              Live preview
            </Text>
            <Text size="sm" mt={4}>
              This experiment will create{' '}
              <Text span fw={700} fz={18} c={runs > 30 ? 'yellow.8' : undefined}>
                {runs} run{runs === 1 ? '' : 's'}
              </Text>
            </Text>
            <Text size="xs" c="dimmed" mt={4} className="mono">
              {lens.consistency} consistency × {lens.delay} delay × {lens.loss} loss × {lens.skew} skew × {lens.outage} outage
            </Text>
            <Divider my="sm" />
            <Stack gap={4}>
              <Group justify="space-between">
                <Text size="sm">Replay window</Text>
                <Text size="sm">{days ? `${days} day${days === 1 ? '' : 's'}` : '—'}</Text>
              </Group>
              <Group justify="space-between">
                <Text size="sm">Per run at {speed}×</Text>
                <Text size="sm">{days ? fmtDuration(perRunMs) : '—'}</Text>
              </Group>
              <Group justify="space-between">
                <Text size="sm" fw={600}>
                  Estimated total
                </Text>
                <Text size="sm" fw={600}>
                  {days ? fmtDuration(perRunMs * runs) : '—'}
                </Text>
              </Group>
              <Text size="xs" c="dimmed">
                = date range ÷ replay speed × runs. Runs execute one at a time.
              </Text>
            </Stack>
            {runs > 30 && (
              <Alert color="yellow" variant="light" mt="sm" p="xs">
                <Text size="xs">That is a lot of runs. Consider fewer values per setting, or split this into several experiments.</Text>
              </Alert>
            )}
            <Divider my="sm" />
            <Stack gap={4}>
              <Text size="xs" c="dimmed">
                {v.signal_ids.length} signal{v.signal_ids.length === 1 ? '' : 's'} · {v.symbols.length} symbol{v.symbols.length === 1 ? '' : 's'}
              </Text>
            </Stack>
            <Stack gap="xs" mt="md">
              <Button onClick={() => submit(true)} loading={busy && save.variables?.launchAfter !== false}>
                Save and launch
              </Button>
              <Button variant="default" type="submit" loading={busy && save.variables?.launchAfter === false}>
                {experiment ? 'Save changes' : 'Save draft'}
              </Button>
              <Button variant="subtle" color="gray" onClick={() => navigate(experiment ? `/experiments/${experiment.id}` : '/experiments')}>
                Cancel
              </Button>
            </Stack>
          </Paper>
        </Grid.Col>
      </Grid>
    </form>
  );
}

export function ExperimentDesignerPage() {
  const { id } = useParams();
  const exp = useExperiment(id);
  const signals = useSignals();
  const datasets = useDatasets();
  const queries = [signals, datasets, ...(id ? [exp] : [])];
  const err = queries.find((q) => q.isError);

  return (
    <>
      <PageHeader
        title={id ? `Edit: ${exp.data?.data.name ?? '…'}` : 'New experiment'}
        subtitle="Choose data and signals, then the grid of fault settings to test."
        servedBy={id ? exp.data?.servedBy : signals.data?.servedBy}
      />
      {err ? (
        <ErrorState error={err.error} onRetry={() => queries.forEach((q) => q.refetch())} />
      ) : queries.some((q) => q.isPending) ? (
        <LoadingState rows={10} height={40} />
      ) : (
        <DesignerForm key={exp.data?.data.id ?? 'new'} experiment={id ? exp.data?.data : undefined} signals={signals.data!.data} datasets={datasets.data!.data} />
      )}
    </>
  );
}
