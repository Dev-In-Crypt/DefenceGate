import { SHARE_NOTE, fewAwardsLine } from '@/lib/coverage-copy';
import { NoteLine } from './blocks';

/**
 * WP-166: the one note beside every share, "where it wins", market total and competitor share from awards (SHARE_NOTE), with a line
 * when the figures stand on very few contracts (`contracts`, lib/coverage-copy.ts FEW_AWARDS).
 */
export function ShareNote({ contracts, className }: { contracts?: number | null; className?: string }) {
  const few = fewAwardsLine(contracts);
  return <NoteLine data-share-coverage className={className}>{SHARE_NOTE}{few ? ` ${few}` : ''}</NoteLine>;
}
