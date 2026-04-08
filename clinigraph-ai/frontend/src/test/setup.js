/**
 * Vitest global setup file.
 *
 * Imported once before all test files.  Registers @testing-library/jest-dom
 * custom matchers (toBeInTheDocument, toHaveClass, etc.) on the global
 * `expect` so every test file can use them without explicit imports.
 */
import '@testing-library/jest-dom';
