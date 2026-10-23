/**
 * The full official CPV 2008 vocabulary (9,454 codes, English titles verbatim; source and licence in lib/data/cpv-full.json). About 370 kB, so
 * it is never imported statically: the supplier page and its report load this module with a dynamic import (a chunk of its own), and every
 * other page keeps the 371-code selection of lib/cpv.ts.
 */
import data from './data/cpv-full.json';
import { titleHasWord } from './cpv';

export const CPV_FULL_SOURCE = { source: data._source, licence: data._licence, retrieved: data._retrieved };
export const CPV_FULL: ReadonlyMap<string, string> = new Map(Object.entries(data.codes as Record<string, string>));

/** WP-90: whether a search word begins a word of the English title of `code` in the full vocabulary, as the API's tender search reads it. */
export const cpvTitleHasWord = (code: string, word: string): boolean => titleHasWord(CPV_FULL.get(code), word);
