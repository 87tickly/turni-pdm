import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

/** Helper shadcn standard per concatenare classi Tailwind. */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
