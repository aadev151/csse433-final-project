import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: { port: 5173 },
  build: {
    chunkSizeWarningLimit: 5000,
    rollupOptions: {
      output: {
        manualChunks: {
          plotly: ['plotly.js-dist-min'],
          mantine: ['@mantine/core', '@mantine/hooks', '@mantine/notifications', '@mantine/dates', '@mantine/form'],
        },
      },
    },
  },
});
