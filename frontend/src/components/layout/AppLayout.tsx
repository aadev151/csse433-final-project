import { ActionIcon, AppShell, Burger, Group, NavLink, ScrollArea, Text, Tooltip, useComputedColorScheme, useMantineColorScheme } from '@mantine/core';
import { useDisclosure } from '@mantine/hooks';
import { Link, Outlet, useLocation } from 'react-router-dom';
import { USE_MOCK } from '../../api';
import { IconDashboard, IconDatabase, IconFlask, IconMoon, IconQueue, IconShield, IconSignal, IconSun } from '../icons';
import { DevPanel } from './DevPanel';
import { HealthWatcher } from './HealthWatcher';
import { OutageBanner } from './OutageBanner';
import { StatusBar } from './StatusBar';

const NAV = [
  { to: '/', label: 'Dashboard', icon: IconDashboard, exact: true },
  { to: '/datasets', label: 'Datasets', icon: IconDatabase },
  { to: '/signals', label: 'Signals', icon: IconSignal },
  { to: '/experiments', label: 'Experiments', icon: IconFlask },
  { to: '/queue', label: 'Queue', icon: IconQueue },
  { to: '/audit', label: 'Audit', icon: IconShield },
];

function ColorSchemeToggle() {
  const { setColorScheme } = useMantineColorScheme();
  const scheme = useComputedColorScheme('light');
  return (
    <Tooltip label={scheme === 'dark' ? 'Light mode' : 'Dark mode'}>
      <ActionIcon variant="default" size="lg" onClick={() => setColorScheme(scheme === 'dark' ? 'light' : 'dark')} aria-label="Toggle color scheme">
        {scheme === 'dark' ? <IconSun /> : <IconMoon />}
      </ActionIcon>
    </Tooltip>
  );
}

export function AppLayout() {
  const [opened, { toggle, close }] = useDisclosure();
  const { pathname } = useLocation();
  const isActive = (to: string, exact?: boolean) =>
    exact ? pathname === to : pathname === to || pathname.startsWith(`${to}/`) || (to === '/experiments' && pathname.startsWith('/runs/'));

  return (
    <AppShell header={{ height: 56 }} navbar={{ width: 210, breakpoint: 'sm', collapsed: { mobile: !opened } }} padding={0}>
      <HealthWatcher />
      <AppShell.Header>
        <Group h="100%" px="md" justify="space-between" wrap="nowrap">
          <Group gap="sm" wrap="nowrap">
            <Burger opened={opened} onClick={toggle} hiddenFrom="sm" size="sm" />
            <Text fw={700} size="sm" visibleFrom="xs" style={{ whiteSpace: 'nowrap' }}>
              Consistency Under Fire
            </Text>
          </Group>
          <Group gap="sm" wrap="nowrap" style={{ overflowX: 'auto' }}>
            <StatusBar />
            <ColorSchemeToggle />
          </Group>
        </Group>
      </AppShell.Header>
      <AppShell.Navbar p="xs">
        <AppShell.Section grow component={ScrollArea}>
          {NAV.map((n) => (
            <NavLink
              key={n.to}
              component={Link}
              to={n.to}
              label={n.label}
              leftSection={<n.icon size={18} />}
              active={isActive(n.to, n.exact)}
              onClick={close}
              style={{ borderRadius: 6 }}
            />
          ))}
        </AppShell.Section>
        <AppShell.Section>
          <Text size="xs" c="dimmed" px="sm" py={6}>
            CSSE433 · {USE_MOCK ? 'mock API' : 'live API'}
          </Text>
        </AppShell.Section>
      </AppShell.Navbar>
      <AppShell.Main>
        <OutageBanner />
        <div className="page">
          <Outlet />
        </div>
      </AppShell.Main>
      {USE_MOCK && <DevPanel />}
    </AppShell>
  );
}
