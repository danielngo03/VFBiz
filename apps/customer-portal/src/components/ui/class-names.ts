import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function mergeClassNames(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}
