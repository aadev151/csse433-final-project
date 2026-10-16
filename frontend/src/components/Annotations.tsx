import { useState } from 'react';
import { Badge, Button, Group, Paper, Stack, TagsInput, Text, TextInput, Textarea, Title, Tooltip } from '@mantine/core';
import { useLocalStorage } from '@mantine/hooks';
import { api } from '../api';
import type { Annotation, AnnotationTarget } from '../api/types';
import { qk, useAnnotations } from '../hooks/queries';
import { useWriteMutation } from '../hooks/useWriteMutation';
import { fmtAgo, fmtTime } from '../lib/format';
import { ConfirmModal } from './ConfirmModal';
import { EmptyState, ErrorState, LoadingState } from './states';

function AnnotationItem({ a, onDelete }: { a: Annotation; onDelete: () => void }) {
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState(a.text);
  const [tags, setTags] = useState(a.tags);
  const update = useWriteMutation({
    mutationFn: () => api.updateAnnotation(a.id, { text, tags, version: a.version }),
    action: 'Annotation updated',
    invalidate: [qk.annotations(a.target_type, a.target_id)],
    onSuccess: () => setEditing(false),
  });

  return (
    <Paper withBorder p="sm" radius="sm">
      {editing ? (
        <Stack gap="xs">
          <Textarea value={text} onChange={(e) => setText(e.currentTarget.value)} autosize minRows={2} aria-label="Annotation text" />
          <TagsInput value={tags} onChange={setTags} placeholder="Tags" size="xs" aria-label="Tags" />
          <Group gap="xs" justify="flex-end">
            <Button size="compact-sm" variant="default" onClick={() => (setEditing(false), setText(a.text), setTags(a.tags))}>
              Cancel
            </Button>
            <Button size="compact-sm" disabled={!text.trim()} loading={update.isPending} onClick={() => update.mutate(undefined)}>
              Save
            </Button>
          </Group>
        </Stack>
      ) : (
        <Stack gap={6}>
          <Text size="sm" style={{ whiteSpace: 'pre-wrap' }}>
            {a.text}
          </Text>
          <Group justify="space-between" gap="xs">
            <Group gap={6}>
              <Text size="xs" fw={600}>
                {a.author}
              </Text>
              <Tooltip label={`created ${fmtTime(a.created_at)} UTC${a.updated_at !== a.created_at ? ` · edited ${fmtTime(a.updated_at)} UTC` : ''}`}>
                <Text size="xs" c="dimmed" className="mono">
                  {fmtAgo(a.created_at)}
                  {a.updated_at !== a.created_at ? ' · edited' : ''}
                </Text>
              </Tooltip>
              {a.tags.map((t) => (
                <Badge key={t} size="xs" variant="default" tt="none">
                  {t}
                </Badge>
              ))}
            </Group>
            <Group gap={2}>
              <Button size="compact-xs" variant="subtle" onClick={() => setEditing(true)}>
                Edit
              </Button>
              <Button size="compact-xs" variant="subtle" color="red" onClick={onDelete}>
                Delete
              </Button>
            </Group>
          </Group>
        </Stack>
      )}
    </Paper>
  );
}

/** Notes attached to an experiment or run: list (newest first), add, inline edit, delete. */
export function Annotations({ targetType, targetId }: { targetType: AnnotationTarget; targetId: string }) {
  const q = useAnnotations(targetType, targetId);
  const [author, setAuthor] = useLocalStorage({ key: 'cuf-author', defaultValue: '' });
  const [text, setText] = useState('');
  const [tags, setTags] = useState<string[]>([]);
  const [toDelete, setToDelete] = useState<Annotation | null>(null);
  const key = qk.annotations(targetType, targetId);

  const create = useWriteMutation({
    mutationFn: () => api.createAnnotation({ target_type: targetType, target_id: targetId, text: text.trim(), tags, author: author.trim() || 'anonymous' }),
    action: 'Annotation added',
    invalidate: [key],
    onSuccess: () => {
      setText('');
      setTags([]);
    },
  });
  const remove = useWriteMutation({
    mutationFn: (a: Annotation) => api.deleteAnnotation(a.id),
    action: 'Annotation deleted',
    invalidate: [key],
    onSuccess: () => setToDelete(null),
  });

  return (
    <Stack gap="sm">
      <Title order={4} fz={16}>
        Annotations
      </Title>
      <Paper withBorder p="sm" radius="sm">
        <Stack gap="xs">
          <Textarea placeholder={`Add a note about this ${targetType}…`} value={text} onChange={(e) => setText(e.currentTarget.value)} autosize minRows={2} aria-label="New annotation" />
          <Group gap="xs" align="flex-end" wrap="wrap">
            <TagsInput placeholder="Tags (Enter to add)" value={tags} onChange={setTags} size="xs" style={{ flex: 1, minWidth: 200 }} aria-label="Tags" />
            <TextInput placeholder="Your name" value={author} onChange={(e) => setAuthor(e.currentTarget.value)} size="xs" w={140} aria-label="Author" />
            <Button size="xs" disabled={!text.trim()} loading={create.isPending} onClick={() => create.mutate(undefined)}>
              Add note
            </Button>
          </Group>
        </Stack>
      </Paper>
      {q.isPending ? (
        <LoadingState rows={2} height={60} />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} title="Couldn't load annotations" />
      ) : q.data.data.length === 0 ? (
        <EmptyState title="No annotations yet" message="Notes you add here are shared with your team and kept in all three databases." />
      ) : (
        q.data.data.map((a) => <AnnotationItem key={`${a.id}-${a.version}`} a={a} onDelete={() => setToDelete(a)} />)
      )}
      <ConfirmModal
        opened={!!toDelete}
        title="Delete annotation?"
        message="This note will be removed for everyone."
        loading={remove.isPending}
        onConfirm={() => toDelete && remove.mutate(toDelete)}
        onClose={() => setToDelete(null)}
      />
    </Stack>
  );
}
