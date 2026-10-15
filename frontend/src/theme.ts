import { createTheme } from '@mantine/core';

export const theme = createTheme({
  primaryColor: 'blue',
  defaultRadius: 'sm',
  fontFamily: 'Inter, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif',
  fontFamilyMonospace: 'ui-monospace, SFMono-Regular, "JetBrains Mono", Menlo, Consolas, monospace',
  headings: { fontWeight: '650' },
  components: {
    Table: { defaultProps: { verticalSpacing: 6, horizontalSpacing: 'sm', fz: 'sm' } },
  },
});
