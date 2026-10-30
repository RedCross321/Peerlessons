import { computed, ref, watch } from 'vue'

const STORAGE_KEY = 'peerlessons-theme'

// Значение 'system' означает «как в операционной системе».
const THEMES = ['system', 'dark', 'light']

const THEME_COLORS = {
  dark: '#090b10',
  light: '#f4f5f8',
}

function readStoredTheme() {
  try {
    const value = localStorage.getItem(STORAGE_KEY)
    return THEMES.includes(value) ? value : 'system'
  } catch {
    // В приватном режиме localStorage может быть недоступен.
    return 'system'
  }
}

function getSystemTheme() {
  if (typeof window === 'undefined' || !window.matchMedia) return 'dark'
  return window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark'
}

const themePreference = ref(readStoredTheme())
const systemTheme = ref(getSystemTheme())

// Итоговая тема: либо явный выбор пользователя, либо тема системы.
const resolvedTheme = computed(() =>
  themePreference.value === 'system' ? systemTheme.value : themePreference.value,
)

function applyTheme(value) {
  if (typeof document === 'undefined') return

  const root = document.documentElement
  root.dataset.theme = value
  root.style.colorScheme = value

  document
    .querySelector('meta[name="theme-color"]')
    ?.setAttribute('content', THEME_COLORS[value] || THEME_COLORS.dark)
}

watch(resolvedTheme, applyTheme, { immediate: true })

if (typeof window !== 'undefined' && window.matchMedia) {
  const media = window.matchMedia('(prefers-color-scheme: light)')
  const syncSystemTheme = (event) => {
    systemTheme.value = event.matches ? 'light' : 'dark'
  }

  if (media.addEventListener) {
    media.addEventListener('change', syncSystemTheme)
  } else if (media.addListener) {
    // Safari < 14.
    media.addListener(syncSystemTheme)
  }
}

export function setTheme(value) {
  if (!THEMES.includes(value)) return

  themePreference.value = value

  try {
    localStorage.setItem(STORAGE_KEY, value)
  } catch {
    // Если сохранить не удалось, тема всё равно применится в текущей сессии.
  }
}

export function useTheme() {
  return { themePreference, resolvedTheme, setTheme }
}
