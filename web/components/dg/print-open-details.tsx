'use client';

import { useEffect } from 'react';

/**
 * Opens every closed disclosure (`details`) of the page while it is printed, and closes again the ones it opened (QA m-16: a call page
 * printed "Conditions as published by the source" without its text). CSS cannot open a closed `details`, so this listens to the print events.
 */
export function PrintOpenDetails() {
  useEffect(() => {
    let opened: HTMLDetailsElement[] = [];
    const before = () => {
      opened = [...document.querySelectorAll<HTMLDetailsElement>('main details:not([open])')];
      for (const d of opened) d.open = true;
    };
    const after = () => { for (const d of opened) d.open = false; opened = []; };
    window.addEventListener('beforeprint', before);
    window.addEventListener('afterprint', after);
    return () => { window.removeEventListener('beforeprint', before); window.removeEventListener('afterprint', after); };
  }, []);
  return null;
}
