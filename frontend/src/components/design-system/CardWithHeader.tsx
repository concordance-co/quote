import type { ReactNode } from "react";
import { cn } from "@/lib/utils";
import {
  DsPanel,
  DsPanelContent,
  DsPanelHeader,
  DsPanelTitle,
} from "@/components/design-system/Panel";

type CardWithHeaderProps = {
  title: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  headerClassName?: string;
  contentClassName?: string;
};

export function CardWithHeader({
  title,
  subtitle,
  actions,
  children,
  className,
  headerClassName,
  contentClassName,
}: CardWithHeaderProps) {
  return (
    <DsPanel className={cn("card-with-header", className)}>
      <DsPanelHeader
        className={cn(
          "card-with-header__header flex items-center justify-between gap-3",
          headerClassName,
        )}
      >
        <div className="min-w-0">
          <DsPanelTitle>{title}</DsPanelTitle>
          {subtitle ? (
            <div className="card-with-header__subtitle text-2xs text-muted-foreground">
              {subtitle}
            </div>
          ) : null}
        </div>
        {actions ? <div className="shrink-0">{actions}</div> : null}
      </DsPanelHeader>
      <DsPanelContent className={cn("card-with-header__content", contentClassName)}>
        {children}
      </DsPanelContent>
    </DsPanel>
  );
}
