import { useCallback, useMemo } from 'react';
import { requestJson } from '../api/request';


export default function useSpoolMutations(authFetch) {
  const request = useCallback(
    (url, options, fallbackMessage) => requestJson(
      authFetch,
      url,
      options,
      fallbackMessage,
    ),
    [authFetch],
  );

  return useMemo(() => ({
    createMetadata: (collection, payload) => request(
      `/api/${collection}/`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      },
      `Failed to add ${collection}.`,
    ),
    addSpool: async (payload) => {
      const data = await request(
        '/api/spools/',
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        },
        'Failed to add spool.',
      );
      return data.spool;
    },
    addRefill: async (payload) => {
      const data = await request(
        '/api/refills/',
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        },
        'Failed to add refill',
      );
      return data.refill;
    },
    addEmptySpool: async (payload) => {
      const data = await request(
        '/api/empty-spools/',
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        },
        'Failed to add empty spool',
      );
      return data.empty_spool;
    },
    assembleRefill: async (payload) => {
      const data = await request(
        '/api/assemble/',
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        },
        'Failed to assemble refill',
      );
      return data.spool;
    },
    deleteRefill: (refillId) => request(
      `/api/refills/${refillId}/`,
      { method: 'DELETE' },
      'Failed to delete refill',
    ),
    loadSpoolHistory: async () => {
      const data = await request(
        '/api/spoolhistory/',
        undefined,
        'Failed to fetch spool history.',
      );
      return Array.isArray(data.history) ? data.history : [];
    },
    loadAdminMetadata: () => request(
      '/api/admin/metadata',
      undefined,
      'Failed to load metadata.',
    ),
    updateSpoolType: (id, fields) => request(
      `/api/spooltypes/${id}`,
      {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(fields),
      },
      'Failed to update spool type.',
    ),
    deleteSpoolType: (id) => request(
      `/api/spooltypes/${id}`,
      { method: 'DELETE' },
      'Failed to delete spool type.',
    ),
    deleteManufacturer: (id) => request(
      `/api/manufacturers/${id}`,
      { method: 'DELETE' },
      'Failed to delete manufacturer.',
    ),
    clearSubtype: (name) => request(
      `/api/subtypes/${encodeURIComponent(name)}`,
      { method: 'DELETE' },
      'Failed to clear subtype.',
    ),
  }), [request]);
}
