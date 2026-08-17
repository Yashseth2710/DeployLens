import { cva, type VariantProps } from "class-variance-authority";
import type { ComponentProps } from "react";

import { cn } from "@/lib/cn";

/**
 * Press controls: square-cornered, hairline-ruled, with the label set as a
 * plate label. The primary action lays down ink; everything else is a rule.
 */
const button = cva(
  "label inline-flex items-center justify-center gap-2 rounded-sheet border !tracking-[0.14em] transition-[background-color,border-color,color] duration-150 ease-pull disabled:pointer-events-none disabled:opacity-45",
  {
    variants: {
      variant: {
        primary:
          "border-accent bg-accent !text-accent-ink hover:border-accent-strong hover:bg-accent-strong",
        secondary:
          "border-rule-strong bg-transparent !text-ink hover:border-ink-faint hover:bg-sheet-raised",
        quiet:
          "border-transparent bg-transparent !text-ink-quiet hover:border-rule hover:!text-ink",
      },
      size: {
        default: "px-4 py-2.5",
        compact: "px-2.5 py-1.5",
      },
    },
    defaultVariants: { variant: "secondary", size: "default" },
  },
);

export function Button({
  className,
  variant,
  size,
  ...props
}: ComponentProps<"button"> & VariantProps<typeof button>) {
  return <button className={cn(button({ variant, size }), className)} {...props} />;
}

export function ButtonLink({
  className,
  variant,
  size,
  ...props
}: ComponentProps<"a"> & VariantProps<typeof button>) {
  return <a className={cn(button({ variant, size }), className)} {...props} />;
}
