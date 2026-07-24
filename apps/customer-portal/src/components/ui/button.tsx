"use client";

import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import type { ButtonHTMLAttributes } from "react";
import { mergeClassNames } from "./class-names";

const buttonVariants = cva(
  "inline-flex min-h-11 items-center justify-center rounded-full border px-5 py-2.5 text-sm font-semibold transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--focus)] disabled:cursor-not-allowed disabled:opacity-50 motion-reduce:transition-none",
  {
    variants: {
      variant: {
        primary:
          "button-primary border-[var(--accent)] bg-[var(--accent)] text-[var(--accent-contrast)] hover:bg-[var(--accent-strong)]",
        secondary:
          "button-secondary border-[var(--border-strong)] bg-[var(--surface)] text-[var(--text)] hover:bg-[var(--surface-subtle)]",
        danger:
          "button-danger border-[var(--danger)] bg-[var(--danger)] text-white hover:bg-[var(--danger-strong)]",
        ghost:
          "border-transparent bg-transparent text-[var(--text)] hover:bg-[var(--surface-subtle)]",
      },
    },
    defaultVariants: {
      variant: "primary",
    },
  },
);

export interface ButtonProps
  extends ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  readonly asChild?: boolean;
}

export function Button({
  asChild = false,
  className,
  variant,
  type = "button",
  ...props
}: ButtonProps) {
  const Component = asChild ? Slot : "button";
  return (
    <Component
      className={mergeClassNames(buttonVariants({ variant }), className)}
      {...(asChild ? props : { type, ...props })}
    />
  );
}
