/**
 * Необязательная инициализация Sentry для фронтенда.
 * Модуль загружается динамически только при заданном VITE_SENTRY_DSN,
 * поэтому SDK не попадает в критический путь загрузки приложения.
 */
export function initFrontendSentry(app, router) {
  const dsn = import.meta.env.VITE_SENTRY_DSN
  if (!dsn) return Promise.resolve(false)

  const rawRate = Number(import.meta.env.VITE_SENTRY_TRACES_SAMPLE_RATE ?? 0.1)
  const tracesSampleRate = Number.isFinite(rawRate)
    ? Math.min(Math.max(rawRate, 0), 1)
    : 0.1

  return import('@sentry/vue')
    .then((Sentry) => {
      Sentry.init({
        app,
        dsn,
        environment:
          import.meta.env.VITE_SENTRY_ENVIRONMENT || import.meta.env.MODE,
        release: import.meta.env.VITE_SENTRY_RELEASE || undefined,
        tracesSampleRate,
        sendDefaultPii: false,
        integrations: [Sentry.browserTracingIntegration({ router })],
      })

      Sentry.setTag('app', 'peerlessons-frontend')
      return true
    })
    .catch(() => false)
}
