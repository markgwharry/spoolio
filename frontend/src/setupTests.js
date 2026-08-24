import '@testing-library/jest-dom/vitest';
import { TextDecoder, TextEncoder } from 'node:util';

// Keep the browser Encoding API available in every supported jsdom release.
globalThis.TextDecoder ??= TextDecoder;
globalThis.TextEncoder ??= TextEncoder;
