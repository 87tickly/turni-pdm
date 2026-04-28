/**
 * Vitest setup: jest-dom matchers + polyfill localStorage.
 *
 * jsdom in vitest 2 in alcuni casi non espone un Storage funzionante:
 * sostituiamo con un map in-memory deterministico per i test.
 */
import "@testing-library/jest-dom/vitest";
import { afterEach, beforeEach } from "vitest";

class MemoryStorage implements Storage {
  private store = new Map<string, string>();

  get length(): number {
    return this.store.size;
  }

  clear(): void {
    this.store.clear();
  }

  getItem(key: string): string | null {
    return this.store.get(key) ?? null;
  }

  setItem(key: string, value: string): void {
    this.store.set(key, String(value));
  }

  removeItem(key: string): void {
    this.store.delete(key);
  }

  key(index: number): string | null {
    return Array.from(this.store.keys())[index] ?? null;
  }
}

const storage = new MemoryStorage();
Object.defineProperty(globalThis, "localStorage", {
  configurable: true,
  value: storage,
});
Object.defineProperty(globalThis, "sessionStorage", {
  configurable: true,
  value: new MemoryStorage(),
});

beforeEach(() => {
  storage.clear();
});

afterEach(() => {
  storage.clear();
});
