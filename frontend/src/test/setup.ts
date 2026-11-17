import "@testing-library/jest-dom/vitest";
import { vi } from "vitest";

Object.defineProperty(Element.prototype, "scrollTo", { value: vi.fn(), writable: true });
Object.defineProperty(Element.prototype, "scrollIntoView", { value: vi.fn(), writable: true });
Object.defineProperty(navigator, "clipboard", { value: { writeText: vi.fn().mockResolvedValue(undefined) }, configurable: true });

class ResizeObserverMock {
  observe() {}
  unobserve() {}
  disconnect() {}
}
Object.defineProperty(globalThis, "ResizeObserver", { value: ResizeObserverMock, writable: true });
