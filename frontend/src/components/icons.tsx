import type { SVGProps } from 'react';

/** Minimal inline stroke icons (no icon library). */
function Icon({ d, size = 18, ...rest }: { d: string; size?: number } & SVGProps<SVGSVGElement>) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" aria-hidden {...rest}>
      <path d={d} />
    </svg>
  );
}

type P = { size?: number };
export const IconDashboard = (p: P) => <Icon {...p} d="M4 13h6V4H4zM14 20h6v-9h-6zM4 20h6v-3H4zM14 7h6V4h-6z" />;
export const IconDatabase = (p: P) => <Icon {...p} d="M4 6c0-1.7 3.6-3 8-3s8 1.3 8 3-3.6 3-8 3-8-1.3-8-3zM4 6v12c0 1.7 3.6 3 8 3s8-1.3 8-3V6M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3" />;
export const IconSignal = (p: P) => <Icon {...p} d="M3 17l5-6 4 3 5-8 4 4" />;
export const IconFlask = (p: P) => <Icon {...p} d="M9 3h6M10 3v6l-5 9a2 2 0 0 0 1.7 3h10.6a2 2 0 0 0 1.7-3l-5-9V3M7.5 15h9" />;
export const IconQueue = (p: P) => <Icon {...p} d="M4 6h16M4 12h16M4 18h10" />;
export const IconShield = (p: P) => <Icon {...p} d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6zM9 12l2 2 4-4" />;
export const IconSun = (p: P) => <Icon {...p} d="M12 4V2M12 22v-2M4 12H2M22 12h-2M5.6 5.6 4.2 4.2M19.8 19.8l-1.4-1.4M5.6 18.4l-1.4 1.4M19.8 4.2l-1.4 1.4M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8z" />;
export const IconMoon = (p: P) => <Icon {...p} d="M20 14.5A8 8 0 0 1 9.5 4 8 8 0 1 0 20 14.5z" />;
export const IconPlus = (p: P) => <Icon {...p} d="M12 5v14M5 12h14" />;
export const IconRefresh = (p: P) => <Icon {...p} d="M20 11a8 8 0 0 0-14.9-3M4 4v4h4M4 13a8 8 0 0 0 14.9 3M20 20v-4h-4" />;
export const IconWrench = (p: P) => <Icon {...p} d="M14.7 6.3a4 4 0 0 0-5.4 5.4L3 18l3 3 6.3-6.3a4 4 0 0 0 5.4-5.4l-2.6 2.6-2.4-.6-.6-2.4z" />;
export const IconDownload = (p: P) => <Icon {...p} d="M12 4v11M7 10l5 5 5-5M5 20h14" />;
export const IconAlert = (p: P) => <Icon {...p} d="M12 3l10 18H2zM12 10v4M12 17.5v.5" />;
export const IconCheck = (p: P) => <Icon {...p} d="M5 12l5 5L20 7" />;
export const IconX = (p: P) => <Icon {...p} d="M6 6l12 12M18 6L6 18" />;
