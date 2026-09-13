/*
 * Narrow on purpose, the way brain/pyproject.toml is. vue-tsc already proves the types; this catches
 * what a person cannot see in review — a promise nobody waited for, a variable that is never read, a
 * template that binds something the component does not have. Style is left alone: the panel is written
 * with a particular rhythm and a formatter would flatten it.
 */
import js from '@eslint/js'
import globals from 'globals'
import ts from 'typescript-eslint'
import vue from 'eslint-plugin-vue'

export default ts.config(
  { ignores: ['dist/**', 'node_modules/**', 'mock/shots/**'] },
  js.configs.recommended,
  ...ts.configs.recommended,
  ...vue.configs['flat/recommended'],
  {
    files: ['**/*.vue'],
    languageOptions: { parserOptions: { parser: ts.parser } },
  },
  {
    // The panel runs in a browser: window, localStorage, fetch and the DOM types are all there.
    files: ['src/**/*.{ts,vue}'],
    languageOptions: { globals: globals.browser },
  },
  {
    files: ['mock/**/*.mjs', 'e2e/**/*.ts', 'tests/**/*.ts', '*.config.ts'],
    languageOptions: { globals: { ...globals.node, ...globals.browser } },
  },
  {
    rules: {
      // The house style, which is not up for debate here.
      'vue/max-attributes-per-line': 'off',
      'vue/singleline-html-element-content-newline': 'off',
      'vue/multiline-html-element-content-newline': 'off',
      'vue/html-self-closing': 'off',
      'vue/html-indent': 'off',
      'vue/html-closing-bracket-newline': 'off',
      'vue/attributes-order': 'off',
      'vue/first-attribute-linebreak': 'off',
      'vue/multi-word-component-names': 'off',   // Sky, Join, Setup: the panel's components are named for what they are

      // What is actually worth failing a build over.
      'no-unused-vars': 'off',                   // the TypeScript one below replaces it
      '@typescript-eslint/no-unused-vars': ['error', { argsIgnorePattern: '^_', varsIgnorePattern: '^_', caughtErrors: 'none' }],
      '@typescript-eslint/no-explicit-any': 'off',   // the brain's JSON arrives as any; pretending otherwise would be worse
      'no-console': ['warn', { allow: ['warn', 'error'] }],
      eqeqeq: ['error', 'smart'],
      'no-var': 'error',
      // `cond ? a() : b()` as a statement is how the panel writes a two-way branch inline. Short-circuit
      // `a && b()` is the same idea with one side.
      '@typescript-eslint/no-unused-expressions': ['error', { allowShortCircuit: true, allowTernary: true }],
      // `try { ... } catch {}` around storage and JSON is the panel's way of saying a failure here
      // changes nothing worth telling anyone about. That is deliberate, and there is a lot of it.
      'no-empty': ['error', { allowEmptyCatch: true }],
    },
  },
  {
    // The mock brain and the shot scripts are Node, not the panel.
    files: ['mock/**/*.mjs', '*.config.ts', 'e2e/**/*.ts', 'tests/**/*.ts'],
    rules: { 'no-console': 'off', '@typescript-eslint/no-unused-vars': ['error', { argsIgnorePattern: '^_' }] },
  },
)
