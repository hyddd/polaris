import { defineStore } from 'pinia'

const STORAGE_KEY = 'polaris-theme'

function getSystemTheme() {
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

export const useThemeStore = defineStore('theme', {
  state: () => ({
    mode: localStorage.getItem(STORAGE_KEY) || 'system', // 'dark' | 'light' | 'system'
    resolved: 'dark',
  }),
  actions: {
    init() {
      this.apply()
      // Listen for system theme changes
      window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => {
        if (this.mode === 'system') this.apply()
      })
    },
    setMode(mode) {
      this.mode = mode
      localStorage.setItem(STORAGE_KEY, mode)
      this.apply()
    },
    apply() {
      this.resolved = this.mode === 'system' ? getSystemTheme() : this.mode
      document.documentElement.setAttribute('data-theme', this.resolved)
      document.documentElement.classList.toggle('dark', this.resolved === 'dark')
    },
    toggle() {
      const next = this.resolved === 'dark' ? 'light' : 'dark'
      this.setMode(next)
    },
  },
})
