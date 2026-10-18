import { useEffect, useSyncExternalStore } from 'react';
import { getServerSnapshot, getSnapshot, mount, refresh, subscribe, unmount, type FitSnapshot } from './fit-store';

/** For a badge or an item of a list: the state of the store, with the item registered while it is on the page. */
export function useFit(id: string): FitSnapshot {
  useEffect(() => {
    mount(id);
    return () => unmount(id);
  }, [id]);
  return useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
}

/** For the filter: the state of the store, with no call registered. */
export function useFitState(): FitSnapshot {
  useEffect(() => { refresh(); }, []);
  return useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
}
