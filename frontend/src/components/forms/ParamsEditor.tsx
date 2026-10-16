import { ActionIcon, Button, Group, NumberInput, SegmentedControl, Stack, Text, TextInput } from '@mantine/core';
import { IconPlus, IconX } from '../icons';
import type { ParamRow } from '../../lib/params';


/** Key/value editor for signal params: add/remove rows, each a number or text. */
export function ParamsEditor({ value, onChange, readOnly }: { value: ParamRow[]; onChange: (rows: ParamRow[]) => void; readOnly?: boolean }) {
  const set = (i: number, patch: Partial<ParamRow>) => onChange(value.map((r, j) => (j === i ? { ...r, ...patch } : r)));
  const keys = value.map((r) => r.key.trim());
  return (
    <Stack gap={6}>
      <Text size="sm" fw={500}>
        Parameters
      </Text>
      {value.length === 0 && (
        <Text size="xs" c="dimmed">
          No parameters.
        </Text>
      )}
      {value.map((r, i) => (
        <Group key={i} gap={6} wrap="nowrap" align="flex-start">
          <TextInput
            placeholder="key"
            value={r.key}
            onChange={(e) => set(i, { key: e.currentTarget.value })}
            readOnly={readOnly}
            size="xs"
            w={140}
            error={r.key.trim() && keys.indexOf(r.key.trim()) !== i ? 'duplicate' : !r.key.trim() ? 'required' : undefined}
            classNames={{ input: 'mono' }}
          />
          <SegmentedControl
            size="xs"
            data={[
              { label: '123', value: 'number' },
              { label: 'abc', value: 'text' },
            ]}
            value={r.kind}
            onChange={(k) => set(i, { kind: k as ParamRow['kind'], value: k === 'number' ? Number(r.value) || 0 : String(r.value) })}
            disabled={readOnly}
          />
          {r.kind === 'number' ? (
            <NumberInput size="xs" value={r.value as number} onChange={(v) => set(i, { value: typeof v === 'number' ? v : Number(v) || 0 })} readOnly={readOnly} style={{ flex: 1 }} />
          ) : (
            <TextInput size="xs" value={String(r.value)} onChange={(e) => set(i, { value: e.currentTarget.value })} readOnly={readOnly} style={{ flex: 1 }} />
          )}
          {!readOnly && (
            <ActionIcon variant="subtle" color="gray" onClick={() => onChange(value.filter((_, j) => j !== i))} aria-label="Remove parameter" mt={2}>
              <IconX size={14} />
            </ActionIcon>
          )}
        </Group>
      ))}
      {!readOnly && (
        <Button size="compact-xs" variant="subtle" leftSection={<IconPlus size={14} />} w="fit-content" onClick={() => onChange([...value, { key: '', kind: 'number', value: 0 }])}>
          Add parameter
        </Button>
      )}
    </Stack>
  );
}
