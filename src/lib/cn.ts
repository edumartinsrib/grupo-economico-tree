export type ClassName = string | false | null | undefined | Record<string, boolean>;

export function cn(...values: ClassName[]): string {
  return values
    .flatMap((value) => {
      if (!value) return [];
      if (typeof value === "string") return [value];
      return Object.entries(value)
        .filter(([, enabled]) => enabled)
        .map(([name]) => name);
    })
    .join(" ");
}
