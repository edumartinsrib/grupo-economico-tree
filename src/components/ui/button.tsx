import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import type { ButtonHTMLAttributes } from "react";
import { cn } from "../../lib/cn";

const buttonVariants = cva(
  "inline-flex h-9 items-center justify-center gap-2 whitespace-nowrap rounded-md border text-sm font-semibold transition active:translate-y-px disabled:pointer-events-none disabled:opacity-50",
  {
    variants: {
      variant: {
        primary: "border-emerald-700 bg-emerald-700 text-white hover:bg-emerald-800",
        secondary: "border-zinc-300 bg-white text-zinc-800 hover:border-zinc-400 hover:bg-zinc-50",
        ghost: "border-transparent bg-transparent text-zinc-700 hover:bg-zinc-100 hover:text-zinc-950",
        danger: "border-red-200 bg-red-50 text-red-800 hover:bg-red-100",
      },
      size: {
        sm: "h-8 px-2.5 text-xs",
        md: "h-9 px-3",
        icon: "h-9 w-9 px-0",
      },
    },
    defaultVariants: {
      variant: "secondary",
      size: "md",
    },
  },
);

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> &
  VariantProps<typeof buttonVariants> & {
    asChild?: boolean;
  };

export function Button({ className, variant, size, asChild = false, ...props }: ButtonProps) {
  const Component = asChild ? Slot : "button";

  return <Component className={cn(buttonVariants({ variant, size }), className)} {...props} />;
}

