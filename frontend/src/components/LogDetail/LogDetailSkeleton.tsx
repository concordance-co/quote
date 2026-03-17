import { Skeleton } from "@/components/ui/skeleton";
import {
  DsPanel,
  DsPanelContent,
  DsPanelHeader,
} from "@/components/design-system/Panel";

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

      <DsPanel>
        <div className="px-3 py-2">
          <Skeleton className="h-4 w-full max-w-md" />
        </div>
      </DsPanel>

      <div>
        <Skeleton className="h-8 w-80 mb-2" />
        <DsPanel>
          <DsPanelHeader>
            <Skeleton className="h-4 w-32" />
          </DsPanelHeader>
          <DsPanelContent>
            <Skeleton className="h-[300px] w-full" />
          </DsPanelContent>
        </DsPanel>
      </div>
    </div>
  );
}
