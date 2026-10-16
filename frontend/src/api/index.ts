import type { ApiClient } from './client';
import { createHttpClient } from './httpClient';
import { createMockClient } from './mockClient';

export const USE_MOCK = import.meta.env.VITE_USE_MOCK === 'true';
export const API_URL = (import.meta.env.VITE_API_URL || 'http://localhost:8000').replace(/\/$/, '');

/** The one API client the whole app uses. Components never know which implementation is active. */
export const api: ApiClient = USE_MOCK ? createMockClient() : createHttpClient(API_URL);

export * from './client';
export * from './types';
