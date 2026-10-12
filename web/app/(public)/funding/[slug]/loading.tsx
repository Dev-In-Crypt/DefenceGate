import { Skeleton } from '@/components/dg/feedback';

export default function Loading() {
  return (
    <div role="status" aria-label="Loading call" className="flex flex-col gap-6">
      <Skeleton className="h-5 w-64" />
      <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_340px]">
        <div className="flex flex-col gap-6">
          <div className="flex gap-2"><Skeleton className="h-[26px] w-14 rounded-pill" /><Skeleton className="h-[26px] w-20 rounded-pill" /></div>
          <Skeleton className="h-24 w-full" />
          <div className="grid grid-cols-[repeat(auto-fit,minmax(200px,1fr))] gap-3">
            {Array.from({ length: 6 }, (_, i) => <Skeleton key={i} className="h-[76px]" />)}
          </div>
          <Skeleton className="h-64 rounded-lg" />
        </div>
        <Skeleton className="h-80 rounded-lg" />
      </div>
      <span className="sr-only">Loading</span>
    </div>
  );
}
