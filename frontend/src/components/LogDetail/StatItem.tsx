import { cn } from "@/lib/utils";

interface StatItemProps {
  label: string;
  value: string | number;
  highlight?: boolean;
}

export function StatItem({ label, value, highlight = false }: StatItemProps) {
  return (
    <div className="flex items-center gap-1.5">
      <span className="text-muted-foreground">{label}:</span>
      <span
        className={cn(
          "font-medium",
          highlight &&
            typeof value === "number" &&
            value > 0 &&
            "text-pink-400",
        )}
      >
        {value}
      </span>
    </div>
  );
}
