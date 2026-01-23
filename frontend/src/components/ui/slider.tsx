import * as React from "react";
import { cn } from "@/lib/utils";

interface SliderProps extends React.InputHTMLAttributes<HTMLInputElement> {
  onValueChange?: (value: number[]) => void;
}

const Slider = React.forwardRef<HTMLInputElement, SliderProps>(
  ({ className, value, onValueChange, onChange, ...props }, ref) => {
    const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
      const newValue = parseFloat(e.target.value);
      if (onValueChange) {
        onValueChange([newValue]);
      }
      if (onChange) {
        onChange(e);
      }
    };

    return (
      <input
        type="range"
        ref={ref}
        value={Array.isArray(value) ? value[0] : value}
        onChange={handleChange}
        className={cn(
          "w-full h-1.5 bg-muted rounded-full appearance-none cursor-pointer",
          "[&::-webkit-slider-thumb]:appearance-none",
          "[&::-webkit-slider-thumb]:h-4",
          "[&::-webkit-slider-thumb]:w-4",
          "[&::-webkit-slider-thumb]:rounded-full",
          "[&::-webkit-slider-thumb]:bg-primary",
          "[&::-webkit-slider-thumb]:border",
          "[&::-webkit-slider-thumb]:border-primary/50",
          "[&::-webkit-slider-thumb]:shadow",
          "[&::-webkit-slider-thumb]:cursor-grab",
          "[&::-webkit-slider-thumb]:active:cursor-grabbing",
          "[&::-webkit-slider-thumb]:hover:bg-primary/80",
          "[&::-webkit-slider-thumb]:transition-colors",
          "[&::-moz-range-thumb]:h-4",
          "[&::-moz-range-thumb]:w-4",
          "[&::-moz-range-thumb]:rounded-full",
          "[&::-moz-range-thumb]:bg-primary",
          "[&::-moz-range-thumb]:border",
          "[&::-moz-range-thumb]:border-primary/50",
          "[&::-moz-range-thumb]:shadow",
          "[&::-moz-range-thumb]:cursor-grab",
          "[&::-moz-range-thumb]:active:cursor-grabbing",
          "[&::-moz-range-thumb]:hover:bg-primary/80",
          "[&::-moz-range-track]:bg-muted",
          "[&::-moz-range-track]:rounded-full",
          "[&::-moz-range-track]:h-1.5",
          "focus:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
          "disabled:pointer-events-none disabled:opacity-50",
          className,
        )}
        {...props}
      />
    );
  },
);

Slider.displayName = "Slider";

export { Slider };
