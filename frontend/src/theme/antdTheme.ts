import { theme as antdTheme, type ThemeConfig } from 'antd'

// Mirrors the hex values in src/index.css's `:root` / `:root[data-theme='dark']`
// blocks. Kept as literals (rather than `var(--color-*-value)`) because antd's
// ConfigProvider tokens are consumed by its own CSS-in-JS engine, which needs
// concrete values to derive the rest of the palette from.
const lightPalette = {
  background: '#f7f5f0',
  surface: '#ffffff',
  border: '#e2ded2',
  foreground: '#1f2a24',
  muted: '#6b6a5f',
  accent: '#0f5c47',
  danger: '#a3312a',
}

const darkPalette = {
  background: '#14181a',
  surface: '#1b201f',
  border: '#2c3431',
  foreground: '#e8ece8',
  muted: '#98a29a',
  accent: '#4fb08a',
  danger: '#e07b73',
}

const fontFamily = "ui-sans-serif, system-ui, -apple-system, 'Segoe UI', sans-serif"

function buildTheme(
  palette: typeof lightPalette,
  algorithm: ThemeConfig['algorithm'],
): ThemeConfig {
  return {
    algorithm,
    token: {
      colorPrimary: palette.accent,
      colorError: palette.danger,
      colorTextBase: palette.foreground,
      colorBgBase: palette.background,
      colorBgContainer: palette.surface,
      colorBgLayout: palette.background,
      colorBorder: palette.border,
      colorTextSecondary: palette.muted,
      borderRadius: 8,
      fontFamily,
    },
  }
}

export const antdThemes: Record<'light' | 'dark', ThemeConfig> = {
  light: buildTheme(lightPalette, antdTheme.defaultAlgorithm),
  dark: buildTheme(darkPalette, antdTheme.darkAlgorithm),
}
