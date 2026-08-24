import { useCallback, useEffect, useMemo, useState } from 'react';
import { requestJson } from '../api/request';

export const FILAMENT_METADATA = [
  'materials',
  'colors',
  'manufacturers',
  'spoolTypes',
  'subtypes',
];
export const ANALYTICS_METADATA = ['materials', 'colors'];
export const HARDWARE_METADATA = ['materials', 'colors', 'manufacturers'];
export const BITS_METADATA = ['bitCategories'];

const definitions = {
  materials: { url: '/api/materials/', responseKey: 'materials' },
  colors: { url: '/api/colors/', responseKey: 'colors' },
  manufacturers: { url: '/api/manufacturers/', responseKey: 'manufacturers' },
  spoolTypes: { url: '/api/spooltypes/', responseKey: 'spool_types' },
  subtypes: { url: '/api/subtypes/', responseKey: 'subtypes' },
  bitCategories: { url: '/api/bitcategories/', responseKey: 'categories' },
};

const cacheByAuthFetch = new WeakMap();

function cacheFor(authFetch) {
  if (!cacheByAuthFetch.has(authFetch)) cacheByAuthFetch.set(authFetch, new Map());
  return cacheByAuthFetch.get(authFetch);
}

async function loadResource(authFetch, name, force) {
  const definition = definitions[name];
  if (!definition) throw new Error(`Unknown metadata resource: ${name}`);
  const cache = cacheFor(authFetch);
  const cached = cache.get(name);
  if (!force && cached?.data) return cached.data;
  if (cached?.promise) return cached.promise;

  const promise = requestJson(
    authFetch,
    definition.url,
    undefined,
    `Failed to load ${name}.`,
  ).then((response) => {
    const items = Array.isArray(response[definition.responseKey])
      ? response[definition.responseKey]
      : [];
    cache.set(name, { data: items });
    return items;
  }).catch((error) => {
    cache.delete(name);
    throw error;
  });
  cache.set(name, { promise });
  return promise;
}

export default function useMetadata(authFetch, resourceNames = FILAMENT_METADATA, options = {}) {
  const resourceKey = resourceNames.join(',');
  const selectedNames = useMemo(() => resourceKey.split(',').filter(Boolean), [resourceKey]);
  const [collections, setCollections] = useState(() => Object.fromEntries(
    selectedNames.map((name) => [name, cacheFor(authFetch).get(name)?.data || []]),
  ));
  const [loading, setLoading] = useState(Boolean(options.auto));
  const [error, setError] = useState('');

  const setCollection = useCallback((name, update) => {
    setCollections((current) => {
      const currentItems = current[name] || [];
      const nextItems = typeof update === 'function' ? update(currentItems) : update;
      cacheFor(authFetch).set(name, { data: nextItems });
      return { ...current, [name]: nextItems };
    });
  }, [authFetch]);

  const reload = useCallback(async ({ force = false } = {}) => {
    setLoading(true);
    setError('');
    try {
      const results = await Promise.allSettled(
        selectedNames.map((name) => loadResource(authFetch, name, force)),
      );
      const nextCollections = Object.fromEntries(
        selectedNames
          .map((name, index) => [name, results[index]])
          .filter(([, result]) => result.status === 'fulfilled')
          .map(([name, result]) => [name, result.value]),
      );
      setCollections((current) => ({ ...current, ...nextCollections }));
      const failed = results.find((result) => result.status === 'rejected');
      if (failed) throw failed.reason;
      return nextCollections;
    } catch (requestError) {
      setError(requestError.message || 'Failed to load metadata.');
      throw requestError;
    } finally {
      setLoading(false);
    }
  }, [authFetch, selectedNames]);

  const auto = Boolean(options.auto);
  useEffect(() => {
    setCollections(Object.fromEntries(
      selectedNames.map((name) => [name, cacheFor(authFetch).get(name)?.data || []]),
    ));
  }, [authFetch, selectedNames]);

  useEffect(() => {
    if (auto) reload().catch(() => {});
  }, [auto, reload]);

  return {
    ...Object.fromEntries(selectedNames.map((name) => [name, collections[name] || []])),
    loading,
    error,
    reload,
    setCollection,
  };
}
