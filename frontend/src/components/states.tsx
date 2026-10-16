import type { ReactNode } from 'react';
import { Alert, Badge, Button, Group, Paper, Skeleton, Stack, Text, Title, Tooltip } from '@mantine/core';
import { ApiError } from '../api/client';
import type { ServedBy } from '../api/types';
import { SERVED_LABEL } from '../lib/format';
import { IconAlert } from './icons';

export function LoadingState({ rows = 6, height = 28 }: { rows?: number; height?: number }) {
  return (
    <Stack gap={8} aria-busy="true" aria-label="Loading">
      {Array.from({ length: rows }, (_, i) => (
        <Skeleton key={i} height={height} radius="sm" />
      ))}
    </Stack>
  );
}

export function ErrorState({ error, onRetry, title }: { error: unknown; onRetry?: () => void; title?: string }) {
  const msg =
    error instanceof ApiError && error.status === 0
      ? 'The API server cannot be reached. Check that the backend is running, then retry.'
      : error instanceof Error
        ? error.message
        : 'Something went wrong.';
  return (
    <Alert color="red" variant="light" title={title ?? "Couldn't load this data"} icon={<IconAlert />}>
      <Group justify="space-between" align="center">
        <Text size="sm">{msg}</Text>
        {onRetry && (
          <Button size="xs" color="red" variant="white" onClick={onRetry}>
            Retry
          </Button>
        )}
      </Group>
    </Alert>
  );
}

export function EmptyState({ title, message, action }: { title: string; message?: ReactNode; action?: ReactNode }) {
  return (
    <Paper withBorder p="xl" radius="md">
      <Stack align="center" gap="xs">
        <Text fw={600}>{title}</Text>
        {message && (
          <Text size="sm" c="dimmed" ta="center" maw={480}>
            {message}
          </Text>
        )}
        {action && <div style={{ marginTop: 8 }}>{action}</div>}
      </Stack>
    </Paper>
  );
}

export function ServedByBadge({ servedBy }: { servedBy?: ServedBy }) {
  if (!servedBy) return null;
  const fallback = servedBy !== 'mongodb';
  return (
    <Tooltip
      label={
        fallback
          ? `MongoDB (the source of truth) is unavailable, so this page was read from ${SERVED_LABEL[servedBy]}.`
          : 'Read from MongoDB, the source of truth.'
      }
      multiline
      w={260}
    >
      <Badge variant={fallback ? 'light' : 'outline'} color={fallback ? 'yellow' : 'gray'} size="sm" radius="sm" tt="none">
        served from {SERVED_LABEL[servedBy]}
      </Badge>
    </Tooltip>
  );
}

export function PageHeader({
  title,
  subtitle,
  servedBy,
  badges,
  actions,
}: {
  title: ReactNode;
  subtitle?: ReactNode;
  servedBy?: ServedBy;
  badges?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <Group justify="space-between" align="flex-start" mb="md" wrap="wrap" gap="sm">
      <Stack gap={4}>
        <Group gap="xs" align="center">
          <Title order={2} fz={22}>
            {title}
          </Title>
          {badges}
          <ServedByBadge servedBy={servedBy} />
        </Group>
        {subtitle && (
          <Text size="sm" c="dimmed">
            {subtitle}
          </Text>
        )}
      </Stack>
      {actions && <Group gap="xs">{actions}</Group>}
    </Group>
  );
}

export function SectionTitle({ children, right }: { children: ReactNode; right?: ReactNode }) {
  return (
    <Group justify="space-between" mb="xs" mt="lg">
      <Title order={4} fz={16}>
        {children}
      </Title>
      {right}
    </Group>
  );
}
