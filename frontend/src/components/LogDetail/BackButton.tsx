import { Link } from "react-router-dom";
import { ArrowLeft } from "lucide-react";
import { Button } from "@/components/ui/button";

interface BackButtonProps {
  onClick?: () => void;
}

export function BackButton({ onClick }: BackButtonProps) {
  if (onClick) {
    return (
      <Button
        variant="ghost"
        size="sm"
        onClick={onClick}
        className="h-7 text-xs gap-1 px-2"
      >
        <ArrowLeft className="h-3 w-3" />
        Back
      </Button>
    );
  }

  return (
    <Button
      variant="ghost"
      size="sm"
      asChild
      className="h-7 text-xs gap-1 px-2"
    >
      <Link to="/">
        <ArrowLeft className="h-3 w-3" />
        Back
      </Link>
    </Button>
  );
}
