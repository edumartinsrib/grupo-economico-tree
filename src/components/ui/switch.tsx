import type { InputHTMLAttributes } from "react";
import { cn } from "../../lib/cn";

type SwitchProps = Omit<InputHTMLAttributes<HTMLInputElement>, "type">;

export function Switch({ className, ...props }: SwitchProps) {
  return (
    <input
      type="checkbox"
      className={cn(
        "h-5 w-9 cursor-pointer appearance-none rounded-full border border-zinc-300 bg-zinc-200 p-0.5 transition before:block before:h-4 before:w-4 before:rounded-full before:bg-white before:shadow-sm before:transition checked:border-emerald-700 checked:bg-emerald-700 checked:before:translate-x-4 focus:outline-none focus:ring-2 focus:ring-emerald-100 disabled:cursor-not-allowed disabled:opacity-50",
        className,
      )}
      {...props}
    />
  );
}

