import type { ReactNode } from 'react';
import { Button, Group, Modal, Stack, Text } from '@mantine/core';

/** Confirmation dialog (never window.confirm). */
export function ConfirmModal({
  opened,
  title,
  message,
  confirmLabel = 'Delete',
  color = 'red',
  loading,
  onConfirm,
  onClose,
}: {
  opened: boolean;
  title: string;
  message: ReactNode;
  confirmLabel?: string;
  color?: string;
  loading?: boolean;
  onConfirm: () => void;
  onClose: () => void;
}) {
  return (
    <Modal opened={opened} onClose={onClose} title={<Text fw={600}>{title}</Text>} centered size="md">
      <Stack>
        <Text size="sm">{message}</Text>
        <Group justify="flex-end">
          <Button variant="default" onClick={onClose}>
            Cancel
          </Button>
          <Button color={color} onClick={onConfirm} loading={loading} data-autofocus>
            {confirmLabel}
          </Button>
        </Group>
      </Stack>
    </Modal>
  );
}
