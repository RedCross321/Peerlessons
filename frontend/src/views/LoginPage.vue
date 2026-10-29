<script setup>
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import api, { saveAuth } from '@/auth'
import ErrorAlert from '@/components/ErrorAlert.vue'
import TurnstileCaptcha from '@/components/TurnstileCaptcha.vue'
import { getErrorMessages } from '@/utils/errors'
import { setPageSeo } from '@/utils/seo'

const router = useRouter()
const email = ref('')
const password = ref('')
const fieldErrors = ref({})
const errorMessages = ref([])
const isLoading = ref(false)
const captchaSiteKey = import.meta.env.VITE_TURNSTILE_SITE_KEY || ''
const captchaToken = ref('')
const captchaRef = ref(null)
const needsVerification = ref(false)
const totpRequired = ref(false)
const totpChallenge = ref('')
const totpCode = ref('')
const totpLoading = ref(false)

setPageSeo({
  title: 'Peerlessons — совместное редактирование кода в реальном времени',
  description:
    'Peerlessons — self-hosted платформа для совместного редактирования кода: комнаты, Monaco Editor, передача прав и живой предпросмотр HTML/CSS/JS.',
  path: '/login',
  robots: 'noindex, follow',
})

// Путь, на который нужно вернуться после входа (защищаемся от внешних редиректов).
const redirectTarget = computed(() => {
  const redirect = router.currentRoute.value.query.redirect
  return typeof redirect === 'string' && redirect.startsWith('/') ? redirect : null
})

const verificationLink = computed(() => ({
  name: 'verify-email',
  query: {
    email: email.value,
    ...(redirectTarget.value ? { redirect: redirectTarget.value } : {})
  }
}))

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

function clearFieldError(field) {
  if (errorMessages.value.length) errorMessages.value = []

  if (!fieldErrors.value[field]) return

  const next = { ...fieldErrors.value }
  delete next[field]
  fieldErrors.value = next
}

function validateForm() {
  const errors = {}
  const mail = email.value.trim()

  if (!mail) {
    errors.email = 'Введите email'
  } else if (!EMAIL_RE.test(mail)) {
    errors.email = 'Некорректный email'
  }

  if (!password.value) {
    errors.password = 'Введите пароль'
  }

  fieldErrors.value = errors
  return Object.keys(errors).length === 0
}

const login = async () => {
  errorMessages.value = []
  needsVerification.value = false

  if (!validateForm()) return

  if (captchaSiteKey && !captchaToken.value) {
    errorMessages.value = ['Подтвердите, что вы не робот']
    return
  }

  isLoading.value = true

  try {
    const payload = {
      email: email.value.trim(),
      password: password.value,
      captcha_token: captchaToken.value || null
    }
    const { data } = await api.post('/auth/login', payload, {
      headers: {
        'Content-Type': 'application/json'
      }
    })

    if (data.totp_required) {
      totpRequired.value = true
      totpChallenge.value = data.challenge
      totpCode.value = ''
      return
    }

    saveAuth(data.access_token, data.refresh_token, data.user)
    router.replace(redirectTarget.value || '/')
  } catch (err) {
    console.error('Ошибка входа:', err)
    needsVerification.value = err.response?.status === 403
    errorMessages.value = getErrorMessages(err, 'Не удалось войти')
    captchaRef.value?.reset()
    captchaToken.value = ''
  } finally {
    isLoading.value = false
  }
}

function onTotpCodeInput(event) {
  totpCode.value = event.target.value
    .toUpperCase()
    .replace(/[^0-9A-Z-]/g, '')
    .slice(0, 9)
}

async function confirmTotp() {
  errorMessages.value = []

  if (!totpCode.value.trim()) {
    errorMessages.value = ['Введите код из приложения']
    return
  }

  totpLoading.value = true

  try {
    const { data } = await api.post('/auth/login/totp', {
      challenge: totpChallenge.value,
      code: totpCode.value.trim()
    })

    saveAuth(data.access_token, data.refresh_token, data.user)
    router.replace(redirectTarget.value || '/')
  } catch (err) {
    console.error('Ошибка подтверждения TOTP:', err)
    errorMessages.value = getErrorMessages(
      err,
      'Не удалось подтвердить код'
    )

    if (err.response?.status === 401) {
      totpRequired.value = false
      totpChallenge.value = ''
      totpCode.value = ''
      captchaToken.value = ''
    }
  } finally {
    totpLoading.value = false
  }
}

function backToPassword() {
  totpRequired.value = false
  totpChallenge.value = ''
  totpCode.value = ''
  captchaToken.value = ''
  errorMessages.value = []
}
</script>

<template>
  <main class="page">
    <section class="card auth-card">
      <div class="auth-head">
        <RouterLink to="/" class="brand auth-brand">
          <span class="brand-mark">/</span>
          <span class="brand-name">Peerlessons</span>
        </RouterLink>
        <h1 class="auth-title">
          {{ totpRequired ? 'Подтвердите вход' : 'С возвращением' }}
        </h1>
        <p class="auth-sub">
          {{ totpRequired
            ? 'Введите код из приложения-аутентификатора'
            : 'Войдите, чтобы продолжить работу в комнатах' }}
        </p>
      </div>

      <ErrorAlert
        :messages="errorMessages"
        :title="totpRequired ? 'Не удалось подтвердить код' : 'Не удалось войти'"
      />

      <template v-if="!totpRequired">
        <p v-if="needsVerification" class="auth-footer">
          <RouterLink :to="verificationLink">Подтвердить почту</RouterLink>
        </p>

        <form class="auth-form" novalidate @submit.prevent="login">
        <div class="field">
          <label class="label" for="email">Email</label>
          <input
            type="email"
            id="email"
            class="input"
            v-model="email"
            required
            :disabled="isLoading"
            :aria-invalid="!!fieldErrors.email"
            placeholder="name@example.com"
            autocomplete="email"
            @input="clearFieldError('email')"
          />
          <div v-if="fieldErrors.email" class="field-error">
            {{ fieldErrors.email }}
          </div>
        </div>

        <div class="field">
          <label class="label" for="password">Пароль</label>
          <input
            type="password"
            id="password"
            class="input"
            v-model="password"
            required
            :disabled="isLoading"
            :aria-invalid="!!fieldErrors.password"
            placeholder="••••••••"
            autocomplete="current-password"
            @input="clearFieldError('password')"
          />
          <div v-if="fieldErrors.password" class="field-error">
            {{ fieldErrors.password }}
          </div>
        </div>

        <TurnstileCaptcha
          v-if="captchaSiteKey"
          ref="captchaRef"
          :site-key="captchaSiteKey"
          @verified="captchaToken = $event"
        />

        <button
          type="submit"
          class="btn btn-primary btn-block btn-lg auth-submit"
          :disabled="isLoading"
        >
          <span v-if="isLoading" class="spinner" aria-hidden="true"></span>
          {{ isLoading ? 'Входим…' : 'Войти' }}
        </button>
        </form>
      </template>

      <form
        v-else
        class="auth-form"
        novalidate
        @submit.prevent="confirmTotp"
      >
        <div class="field">
          <label class="label" for="totp-login-code">
            Код из приложения
          </label>
          <input
            id="totp-login-code"
            class="input"
            type="text"
            inputmode="text"
            maxlength="9"
            :value="totpCode"
            required
            :disabled="totpLoading"
            placeholder="000000 или XXXX-XXXX"
            autocomplete="one-time-code"
            @input="onTotpCodeInput"
          />
          <div class="field-hint">
            Введите 6-значный код или код восстановления
          </div>
        </div>

        <button
          type="submit"
          class="btn btn-primary btn-block btn-lg auth-submit"
          :disabled="totpLoading"
        >
          <span v-if="totpLoading" class="spinner" aria-hidden="true"></span>
          {{ totpLoading ? 'Проверяем…' : 'Подтвердить код' }}
        </button>

        <button
          type="button"
          class="btn btn-ghost btn-block"
          :disabled="totpLoading"
          @click="backToPassword"
        >
          Назад
        </button>
      </form>

      <p class="auth-footer">
        Нет аккаунта?
        <RouterLink :to="{ name: 'reg-page', query: redirectTarget ? { redirect: redirectTarget } : {} }">
          Создать аккаунт
        </RouterLink>
        <span class="dot-sep">·</span>
        <a href="/about/">О проекте</a>
      </p>
    </section>
  </main>
</template>
