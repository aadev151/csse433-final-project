import type { LiveConnection, LiveHandlers } from './client';
import type { LiveMessage } from './types';

/**
 * Opens the real run live-stream WebSocket. Reconnection is handled one level
 * up (useLiveRun) so that mock and real connections behave identically.
 */
export function connectLiveSocket(url: string, handlers: LiveHandlers): LiveConnection {
  let closedByUs = false;
  let socket: WebSocket;
  try {
    socket = new WebSocket(url);
  } catch {
    queueMicrotask(() => handlers.onClose?.('connect_failed'));
    return { close: () => undefined };
  }
  socket.onopen = () => handlers.onOpen?.();
  socket.onmessage = (ev) => {
    try {
      handlers.onMessage(JSON.parse(String(ev.data)) as LiveMessage);
    } catch {
      /* ignore malformed frames */
    }
  };
  socket.onclose = (ev) => {
    if (!closedByUs) handlers.onClose?.(ev.reason || `closed (${ev.code})`);
  };
  return {
    close: () => {
      closedByUs = true;
      socket.close();
    },
  };
}
