import { Skeleton } from "@/components/ui/skeleton";

export function LogDetailSkeleton() {
  return (
    <div className="space-y-3">
      <Skeleton className="h-7 w-16" />

      <div className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <Skeleton className="h-6 w-32" />
          <Skeleton className="h-5 w-12" />
          <Skeleton className="h-4 w-48" />
        </div>
        <div className="flex gap-1">
          <Skeleton className="h-7 w-7" />
          <Skeleton className="h-7 w-7" />
        </div>
      </div>

      <div className="panel">
        <div className="px-3 py-2">
          <Skeleton className="h-4 w-full max-w-md" />
        </div>
      </div>

      <div>
        <Skeleton className="h-8 w-80 mb-2" />
        <div className="panel">
          <div className="panel-header">
            <Skeleton className="h-4 w-32" />
          </div>
          <div className="panel-content">
            <Skeleton className="h-[300px] w-full" />
          </div>
        </div>
      </div>
    </div>
  );
}
