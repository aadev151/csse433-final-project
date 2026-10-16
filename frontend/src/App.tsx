import type { ReactNode } from 'react';
import { Route, Routes, useLocation, Link } from 'react-router-dom';
import { Button } from '@mantine/core';
import { AppLayout } from './components/layout/AppLayout';
import { ErrorBoundary } from './components/ErrorBoundary';
import { EmptyState } from './components/states';
import { DashboardPage } from './pages/Dashboard';
import { DatasetsPage } from './pages/Datasets';
import { SignalsPage } from './pages/Signals';
import { ExperimentsPage } from './pages/Experiments';
import { ExperimentDesignerPage } from './pages/ExperimentDesigner';
import { ExperimentDetailPage } from './pages/ExperimentDetail';
import { RunDetailPage } from './pages/RunDetail';
import { QueuePage } from './pages/Queue';
import { AuditPage } from './pages/Audit';

function NotFound() {
  return (
    <EmptyState
      title="Page not found"
      message="That address doesn't match any page."
      action={
        <Button component={Link} to="/">
          Go to dashboard
        </Button>
      }
    />
  );
}

export function App() {
  const { pathname } = useLocation();
  const guard = (el: ReactNode) => <ErrorBoundary resetKey={pathname}>{el}</ErrorBoundary>;
  return (
    <Routes>
      <Route element={<AppLayout />}>
        <Route index element={guard(<DashboardPage />)} />
        <Route path="datasets" element={guard(<DatasetsPage />)} />
        <Route path="signals" element={guard(<SignalsPage />)} />
        <Route path="experiments" element={guard(<ExperimentsPage />)} />
        <Route path="experiments/new" element={guard(<ExperimentDesignerPage />)} />
        <Route path="experiments/:id/edit" element={guard(<ExperimentDesignerPage />)} />
        <Route path="experiments/:id" element={guard(<ExperimentDetailPage />)} />
        <Route path="runs/:id" element={guard(<RunDetailPage />)} />
        <Route path="queue" element={guard(<QueuePage />)} />
        <Route path="audit" element={guard(<AuditPage />)} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  );
}
