import '@testing-library/jest-dom/vitest';
import 'vitest-axe/extend-expect';

// framer-motion's useReducedMotion() calls window.matchMedia, which
// jsdom doesn't implement. Always reports "no preference" in tests --
// deterministic, and no test in this suite asserts on animation state.
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  }),
});
