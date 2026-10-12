import { CallCardSkeleton, Skeleton } from '@/components/dg/feedback';

const SKELETON_CARDS = 3;

export default function Loading() {
  return (
    <div role="status" aria-label="Loading funding calls" className="flex flex-col gap-6">
      <Skeleton className="h-5 w-40" />
      <div className="flex flex-col gap-3"><Skeleton className="h-12 w-72" /><Skeleton className="h-5 w-full max-w-xl" /></div>
      <div className="grid items-start gap-6 lg:grid-cols-[280px_minmax(0,1fr)]">
        <Skeleton className="hidden h-[640px] rounded-lg lg:block" />
        <div className="flex flex-col gap-4">
          <Skeleton className="h-11 w-full" />
          {Array.from({ length: SKELETON_CARDS }, (_, i) => <CallCardSkeleton key={i} />)}
        </div>
      </div>
      <span className="sr-only">Loading</span>
    </div>
  );
}
