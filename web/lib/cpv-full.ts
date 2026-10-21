/**
 * The full official CPV 2008 vocabulary (9,454 codes, English titles verbatim; source and licence in lib/data/cpv-full.json). About 370 kB, so
 * it is never imported statically: the supplier page and its report load this module with a dynamic import (a chunk of its own), and every
 * other page keeps the 371-code selection of lib/cpv.ts.
 */
import data from './data/cpv-full.json';

export const CPV_FULL_SOURCE = { source: data._source, licence: data._licence, retrieved: data._retrieved };
export const CPV_FULL: ReadonlyMap<string, string> = new Map(Object.entries(data.codes as Record<string, string>));
