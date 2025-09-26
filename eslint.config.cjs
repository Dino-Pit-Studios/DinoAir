module.exports = [
  // Global ignores (ESLint v9 Flat Config)
  {
    ignores: [
      'node_modules',
      'dist',
      'build',
      'API_files',
      'monitoring',
      '**/*.d.ts',
      '**/*.config.js',
      '**/*.config.ts',
      '*.config.js',
      '*.config.ts',
    ],
  },
  // TypeScript/TSX rules for src
  {
    files: ['src/**/*.{ts,tsx}'],
    languageOptions: {
      parser: require('@typescript-eslint/parser'),
      ecmaVersion: 2022,
      sourceType: 'module',
      parserOptions: {
        ecmaFeatures: { jsx: true },
        // Do not require type-aware linting for these rules
        project: false,
      },
    },
    plugins: {
      import: require('eslint-plugin-import'),
      '@typescript-eslint': require('@typescript-eslint/eslint-plugin'),
      prettier: require('eslint-plugin-prettier'),
    },
    settings: {
      // Enable TS path resolution for eslint-plugin-import if used
      'import/resolver': {
        typescript: {
          alwaysTryTypes: true,
          project: ['./tsconfig.json'],
        },
      },
    },
    rules: {
      // Import hygiene
      'import/no-duplicates': 'error',
      // Order and group imports with alphabetical order and blank lines between groups
      'import/order': [
        'error',
        {
          groups: [
            'builtin',
            'external',
            'internal',
            'parent',
            'sibling',
            'index',
            'object',
            'type',
          ],
          'newlines-between': 'always',
          alphabetize: { order: 'asc', caseInsensitive: true },
        },
      ],
      // Disable core rule to avoid overlap with plugin-import
      'no-duplicate-imports': 'off',

      // TS unused vars
      '@typescript-eslint/no-unused-vars': [
        'error',
        { argsIgnorePattern: '^_', varsIgnorePattern: '^_' },
      ],

      // Prettier integration (optional)
      'prettier/prettier': 'warn',
    },
  },
];
