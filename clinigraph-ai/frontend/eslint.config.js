import js from '@eslint/js';
import globals from 'globals';
import reactPlugin from 'eslint-plugin-react';
import reactHooksPlugin from 'eslint-plugin-react-hooks';
import reactRefreshPlugin from 'eslint-plugin-react-refresh';

export default [
  // Base JS recommended rules.
  js.configs.recommended,

  // React-specific configuration.
  {
    files: ['src/**/*.{js,jsx}'],
    plugins: {
      react: reactPlugin,
      'react-hooks': reactHooksPlugin,
      'react-refresh': reactRefreshPlugin,
    },
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: 'module',
      globals: {
        ...globals.browser,
        // Vitest globals (describe, it, expect, vi, beforeEach, afterEach).
        ...globals.node,
      },
      parserOptions: {
        ecmaFeatures: { jsx: true },
      },
    },
    settings: {
      react: { version: 'detect' },
    },
    rules: {
      // React core rules.
      ...reactPlugin.configs.recommended.rules,
      'react/react-in-jsx-scope': 'off', // Not needed with React 17+ JSX transform.
      'react/prop-types': 'warn',

      // Hooks exhaustive-deps helps catch stale closure bugs.
      ...reactHooksPlugin.configs.recommended.rules,

      // Fast-refresh compliance: every file with JSX must export only components.
      'react-refresh/only-export-components': ['warn', { allowConstantExport: true }],

      // Style / hygiene
      'no-unused-vars': ['warn', { argsIgnorePattern: '^_' }],
      'no-console': ['warn', { allow: ['warn', 'error'] }],
    },
  },

  // Ignore build output and node_modules.
  {
    ignores: ['dist/', 'node_modules/'],
  },
];
