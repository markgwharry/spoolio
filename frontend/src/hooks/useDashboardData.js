import { useCallback, useEffect, useState } from 'react';
import { requestJson } from '../api/request';
import useMetadata, { FILAMENT_METADATA } from './useMetadata';


export default function useDashboardData(authFetch) {
  const [spools, setSpools] = useState([]);
  const [refills, setRefills] = useState([]);
  const [emptySpools, setEmptySpools] = useState([]);
  const metadata = useMetadata(authFetch, FILAMENT_METADATA);
  const reloadMetadata = metadata.reload;
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const reloadSpools = useCallback(async () => {
    const data = await requestJson(
      authFetch,
      '/api/spools/',
      undefined,
      'Failed to load spools.',
    );
    const nextSpools = Array.isArray(data.spools) ? data.spools : [];
    setSpools(nextSpools);
    return nextSpools;
  }, [authFetch]);

  const reloadEmptySpools = useCallback(async () => {
    try {
      const data = await requestJson(
        authFetch,
        '/api/empty-spools/',
        undefined,
        'Failed to load empty spools.',
      );
      const nextEmptySpools = Array.isArray(data.empty_spools)
        ? data.empty_spools
        : [];
      setEmptySpools(nextEmptySpools);
      return nextEmptySpools;
    } catch (requestError) {
      setEmptySpools([]);
      return [];
    }
  }, [authFetch]);

  const reload = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      await reloadSpools();

      await reloadMetadata();

      try {
        const refillData = await requestJson(
          authFetch,
          '/api/refills/',
          undefined,
          'Failed to load refills.',
        );
        setRefills(Array.isArray(refillData.refills) ? refillData.refills : []);
      } catch (requestError) {
        setRefills([]);
      }
      await reloadEmptySpools();
    } catch (requestError) {
      if (requestError.status === 401) {
        setError('Session expired. Please log in again.');
        setSpools([]);
      } else {
        setError(requestError.message || 'Error loading data.');
      }
    } finally {
      setLoading(false);
    }
  }, [authFetch, reloadMetadata, reloadEmptySpools, reloadSpools]);

  useEffect(() => {
    reload();
  }, [reload]);

  return {
    spools,
    setSpools,
    refills,
    setRefills,
    emptySpools,
    setEmptySpools,
    materials: metadata.materials,
    setMaterials: (update) => metadata.setCollection('materials', update),
    colors: metadata.colors,
    setColors: (update) => metadata.setCollection('colors', update),
    manufacturers: metadata.manufacturers,
    setManufacturers: (update) => metadata.setCollection('manufacturers', update),
    spoolTypes: metadata.spoolTypes,
    setSpoolTypes: (update) => metadata.setCollection('spoolTypes', update),
    subtypes: metadata.subtypes,
    setSubtypes: (update) => metadata.setCollection('subtypes', update),
    loading,
    error,
    reload,
    reloadSpools,
    reloadEmptySpools,
  };
}
