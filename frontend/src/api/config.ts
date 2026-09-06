export type DataMode = 'mock' | 'http';

function readMode(raw: string | undefined): DataMode {
  return raw === 'http' ? 'http' : 'mock';
}

/** Default empty base uses the Vite proxy to the engine. */
export const apiBase = (import.meta.env.VITE_API_BASE_URL as string | undefined)?.replace(/\/$/, '') ?? '';

export const dataMode: DataMode = readMode(import.meta.env.VITE_DATA_MODE as string | undefined);

export const isHttpMode = dataMode === 'http';

export function apiUrl(path: string): string {
  const normalized = path.startsWith('/') ? path : `/${path}`;
  return `${apiBase}${normalized}`;
}
