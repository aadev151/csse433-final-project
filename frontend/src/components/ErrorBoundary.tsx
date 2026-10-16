import { Component, type ReactNode } from 'react';
import { Alert, Button, Code, Stack, Text } from '@mantine/core';

/** Last line of defence: a render error shows a message instead of a blank page. */
export class ErrorBoundary extends Component<{ children: ReactNode; resetKey?: string }, { error: Error | null }> {
  state = { error: null as Error | null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  componentDidUpdate(prev: { resetKey?: string }) {
    if (prev.resetKey !== this.props.resetKey && this.state.error) this.setState({ error: null });
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <Alert color="red" title="This page hit an unexpected error" variant="light">
        <Stack gap="xs">
          <Text size="sm">The rest of the app still works. You can try again or go to another page.</Text>
          <Code block>{this.state.error.message}</Code>
          <Button size="xs" variant="white" color="red" w="fit-content" onClick={() => this.setState({ error: null })}>
            Try again
          </Button>
        </Stack>
      </Alert>
    );
  }
}
