import { forwardRef, type ButtonHTMLAttributes } from "react";
import { cn } from "../../utils/format";

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "default" | "outline" | "ghost" | "destructive";
  size?: "default" | "sm" | "icon";
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant = "default", size = "default", type = "button", ...props }, ref) => (
    <button
      ref={ref}
      type={type}
      className={cn(
        "inline-flex shrink-0 items-center justify-center gap-2 rounded-lg text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 disabled:pointer-events-none disabled:opacity-50",
        variant === "default" && "bg-neutral-900 text-white hover:bg-neutral-700 dark:bg-neutral-100 dark:text-neutral-900 dark:hover:bg-white",
        variant === "outline" && "border border-neutral-200 bg-white hover:bg-neutral-50 dark:border-neutral-700 dark:bg-neutral-900 dark:hover:bg-neutral-800",
        variant === "ghost" && "hover:bg-neutral-100 dark:hover:bg-neutral-800",
        variant === "destructive" && "bg-red-600 text-white hover:bg-red-500",
        size === "default" && "h-10 px-4",
        size === "sm" && "h-8 rounded-md px-2.5 text-xs",
        size === "icon" && "h-9 w-9",
        className,
      )}
      {...props}
    />
  ),
);
Button.displayName = "Button";
