import axios from 'axios'

const ACCESS_TOKEN_KEY = 'token'
const REFRESH_TOKEN_KEY = 'refresh_token'
const USER_KEY = 'user'

// Обновляем access-токен чуть заранее, чтобы не ловить 401 на каждом запросе.
const REFRESH_BEFORE_EXPIRY_MS = 60_000

const api = axios.create({
  baseURL: '/api'
})

api.interceptors.request.use(config => {
  const token = localStorage.getItem(ACCESS_TOKEN_KEY)
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

function decodeJwtPayload(token) {
  if (!token) return null
  try {
    const base64 = token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')
    const padded = base64.padEnd(
      base64.length + ((4 - (base64.length % 4)) % 4),
      '='
    )
    return JSON.parse(atob(padded))
  } catch {
    return null
  }
}

export function saveUser(user) {
  localStorage.setItem(USER_KEY, JSON.stringify(user))
}

export function saveAuth(accessToken, refreshToken, user) {
  localStorage.setItem(ACCESS_TOKEN_KEY, accessToken)
  if (refreshToken) {
    localStorage.setItem(REFRESH_TOKEN_KEY, refreshToken)
  }
  localStorage.setItem(USER_KEY, JSON.stringify(user))
  scheduleTokenRefresh()
}

export function logout({ revoke = true } = {}) {
  clearTimeout(refreshTimer)
  refreshTimer = null

  const refreshToken = localStorage.getItem(REFRESH_TOKEN_KEY)

  localStorage.removeItem(ACCESS_TOKEN_KEY)
  localStorage.removeItem(REFRESH_TOKEN_KEY)
  localStorage.removeItem(USER_KEY)

  if (revoke && refreshToken) {
    // Отзываем токен на сервере, но не блокируем выход ожиданием сети.
    axios
      .post('/api/auth/logout', { refresh_token: refreshToken }, { timeout: 5_000 })
      .catch(() => {
        // Если сервер недоступен, локальная сессия всё равно уже завершена.
      })
  }
}

export function getUser() {
  const raw = localStorage.getItem(USER_KEY)
  return raw ? JSON.parse(raw) : null
}

export function getRefreshToken() {
  return localStorage.getItem(REFRESH_TOKEN_KEY)
}

export function isAccessTokenExpired(offsetMs = REFRESH_BEFORE_EXPIRY_MS) {
  const payload = decodeJwtPayload(localStorage.getItem(ACCESS_TOKEN_KEY))
  if (!payload?.exp) return true
  return payload.exp * 1000 <= Date.now() + offsetMs
}

export function isLoggedIn() {
  const accessToken = localStorage.getItem(ACCESS_TOKEN_KEY)
  const refreshToken = localStorage.getItem(REFRESH_TOKEN_KEY)
  if (!accessToken && !refreshToken) return false
  // С протухшим access-токеном можно продолжать работать: его обновит refresh.
  if (refreshToken) return true
  return !isAccessTokenExpired(0)
}

let refreshPromise = null
let refreshTimer = null

/**
 * Обновляет access-токен. Параллельные вызовы используют один запрос.
 */
export function refreshAccessToken() {
  if (refreshPromise) return refreshPromise

  refreshPromise = (async () => {
    const refreshToken = getRefreshToken()
    if (!refreshToken) {
      throw new Error('Refresh-токен отсутствует')
    }

    const { data } = await axios.post('/api/auth/refresh', {
      refresh_token: refreshToken
    })

    saveAuth(data.access_token, data.refresh_token || refreshToken, data.user)
    return data.access_token
  })().finally(() => {
    refreshPromise = null
  })

  return refreshPromise
}

/**
 * Проверяет, что access-токен ещё жив, и при необходимости обновляет его.
 * Возвращает false, если сессию восстановить не удалось.
 */
export async function ensureValidAccessToken() {
  if (!isAccessTokenExpired()) return true
  if (!getRefreshToken()) return false

  try {
    await refreshAccessToken()
    return true
  } catch {
    handleSessionExpired()
    return false
  }
}

export function scheduleTokenRefresh() {
  clearTimeout(refreshTimer)
  refreshTimer = null

  const payload = decodeJwtPayload(localStorage.getItem(ACCESS_TOKEN_KEY))
  if (!payload?.exp) return

  const delay = Math.max(
    payload.exp * 1000 - Date.now() - REFRESH_BEFORE_EXPIRY_MS,
    5_000
  )

  refreshTimer = setTimeout(async () => {
    try {
      await refreshAccessToken()
    } catch {
      handleSessionExpired()
    }
  }, delay)
}

/**
 * Сессия недействительна: чистим токены и отправляем на вход,
 * сохраняя путь, на который нужно вернуться после логина.
 */
export function handleSessionExpired() {
  // Токен уже недействителен — повторно отзывать его на сервере не нужно.
  logout({ revoke: false })

  if (typeof window === 'undefined') return
  const { pathname, search, hash } = window.location
  if (pathname === '/login' || pathname === '/register') return

  const redirect = encodeURIComponent(pathname + search + hash)
  window.location.assign(`/login?redirect=${redirect}`)
}

let authRefreshInitialized = false

/**
 * Запускает фоновое обновление токена при старте приложения.
 */
export function initAuthRefresh() {
  if (authRefreshInitialized) return
  authRefreshInitialized = true

  // Таймеры в фоновых вкладках могут задерживаться — догоняем при возврате.
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState !== 'visible') return
    if (!getRefreshToken() || !isAccessTokenExpired()) return
    refreshAccessToken().catch(handleSessionExpired)
  })

  if (!isLoggedIn()) return

  if (isAccessTokenExpired()) {
    refreshAccessToken().catch(handleSessionExpired)
  } else {
    scheduleTokenRefresh()
  }
}

api.interceptors.response.use(
  response => response,
  async error => {
    const original = error.config
    const status = error.response?.status

    if (status !== 401 || !original || original._retry) {
      return Promise.reject(error)
    }

    const url = original.url || ''
    if (
      url.includes('/auth/login') ||
      url.includes('/auth/register') ||
      url.includes('/auth/refresh') ||
      !getRefreshToken()
    ) {
      return Promise.reject(error)
    }

    original._retry = true

    try {
      await refreshAccessToken()
      // Повторяем исходный запрос: request-интерцептор подставит новый токен.
      return api(original)
    } catch (refreshError) {
      handleSessionExpired()
      return Promise.reject(refreshError)
    }
  }
)

export default api
