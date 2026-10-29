<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import api, { saveAuth } from '@/auth'
import ErrorAlert from '@/components/ErrorAlert.vue'
import TurnstileCaptcha from '@/components/TurnstileCaptcha.vue'
import { getErrorMessages } from '@/utils/errors'
import { setPageSeo } from '@/utils/seo'

const route = useRoute()
const router = useRouter()

const email = ref(String(route.query.email || ''))
const code = ref('')
const token = ref(String(route.query.token || ''))
const captchaToken = ref('')
const captchaRef = ref(null)
const errorMessages = ref([])
const successMessage = ref('')
const isLoading = ref(false)
const resendLoading = ref(false)
const resendIn = ref(0)

const captchaSiteKey = import.meta.env.VITE_TURNSTILE_SITE_KEY || ''

let resendTimer = null

setPageSeo({
  title: 'Подтверждение почты — Peerlessons',
  description:
    'Подтвердите почту, чтобы завершить регистрацию в Peerlessons.',
  path: '/verify-email',
  robots: 'noindex, nofollow',
  canonical: false,
})

const redirectTarget = computed(() => {
  const redirect = route.query.redirect
  return typeof redirect === 'string' && redirect.startsWith('/')
    ? redirect
    : null
})

const expiresMinutes = computed(() => {
  const seconds = Number(route.query.expires_in)
  return Number.isFinite(seconds) && seconds > 0
    ? Math.max(1, Math.round(seconds / 60))
    : 15
})

const resendLabel = computed(() => {
  if (resendLoading.value) return 'Отправляем письмо…'
  if (resendIn.value > 0) return `Отправить снова через ${resendIn.value} с`
  return 'Отправить письмо снова'
})

function startResendCountdown(seconds) {
  clearInterval(resendTimer)
  resendIn.value = Math.max(0, Math.min(Number(seconds) || 0, 3600))

  if (!resendIn.value) return

  resendTimer = setInterval(() => {
    resendIn.value -= 1

    if (resendIn.value <= 0) {
      resendIn.value = 0
      clearInterval(resendTimer)
      resendTimer = null
    }
  }, 1000)
}

function onCodeInput(event) {
  code.value = event.target.value.replace(/\D/g, '').slice(0, 6)
}

function submit() {
  verify({
    useToken: Boolean(token.value) && code.value.length === 0
  })
}

async function verify({ useToken = false } = {}) {
  if (isLoading.value) return

  errorMessages.value = []
  successMessage.value = ''

  const targetEmail = email.value.trim()

  if (!targetEmail) {
    errorMessages.value = ['Введите email']
    return
  }

  if (!useToken && (code.value.length !== 6 || !/^\d{6}$/.test(code.value))) {
    errorMessages.value = ['Введите 6-значный код из письма']
    return
  }

  isLoading.value = true

  try {
    const payload = useToken
      ? { email: targetEmail, token: token.value }
      : { email: targetEmail, code: code.value }

    const { data } = await api.post('/auth/verify-email', payload)

    saveAuth(data.access_token, data.refresh_token, data.user)
    successMessage.value = 'Почта подтверждена! Переходим...'

    setTimeout(() => {
      router.replace(redirectTarget.value || '/')
    }, 600)
  } catch (err) {
    console.error('Ошибка подтверждения почты:', err)
    errorMessages.value = getErrorMessages(
      err,
      'Не удалось подтвердить почту'
    )

    if (useToken) {
      token.value = ''
    }
  } finally {
    isLoading.value = false
  }
}

async function resend() {
  if (resendLoading.value || resendIn.value > 0) return

  errorMessages.value = []
  successMessage.value = ''

  if (!email.value.trim()) {
    errorMessages.value = ['Введите email']
    return
  }

  if (captchaSiteKey && !captchaToken.value) {
    errorMessages.value = ['Подтвердите, что вы не робот']
    return
  }

  resendLoading.value = true

  try {
    const { data } = await api.post('/auth/resend-verification', {
      email: email.value.trim(),
      captcha_token: captchaToken.value || null
    })

    successMessage.value = 'Новое письмо отправлено. Проверьте почту.'
    startResendCountdown(data.resend_after)
  } catch (err) {
    console.error('Ошибка повторной отправки письма:', err)
    errorMessages.value = getErrorMessages(
      err,
      'Не удалось отправить письмо'
    )

    if (err.response?.status === 429) {
      const detail = String(err.response?.data?.detail || '')
      const match = detail.match(/(\d+)/)
      startResendCountdown(match ? Number(match[1]) : 60)
    }
  } finally {
    captchaRef.value?.reset()
    captchaToken.value = ''
    resendLoading.value = false
  }
}

onMounted(() => {
  const initialResend = Number(route.query.resend_after)
  if (Number.isFinite(initialResend) && initialResend > 0) {
    startResendCountdown(initialResend)
  }

  if (token.value && !email.value.trim()) {
    errorMessages.value = [
      'Ссылка неполная. Введите email и код из письма.'
    ]
  }
})

onUnmounted(() => {
  clearInterval(resendTimer)
})
</script>

<template>
  <main class="page">
    <section class="card auth-card">
      <div class="auth-head">
        <RouterLink to="/" class="brand auth-brand">
          <span class="brand-mark">/</span>
          <span class="brand-name">Peerlessons</span>
        </RouterLink>
        <h1 class="auth-title">Подтвердите почту</h1>
        <p class="auth-sub">
          Мы отправили шестизначный код на
          <b>{{ email || 'вашу почту' }}</b>
        </p>
      </div>

      <ErrorAlert
        :messages="errorMessages"
        title="Не удалось подтвердить почту"
      />
      <div v-if="successMessage" class="alert alert-success" role="alert">
        {{ successMessage }}
      </div>

      <div v-if="token && !code" class="alert alert-info" role="status">
        Ссылка подтверждения готова. Нажмите «Подтвердить почту», чтобы
        завершить регистрацию.
      </div>

      <form class="auth-form" novalidate @submit.prevent="submit">
        <div class="field">
          <label class="label" for="verify-email">Email</label>
          <input
            id="verify-email"
            class="input"
            type="email"
            v-model="email"
            required
            :disabled="isLoading"
            placeholder="name@example.com"
            autocomplete="email"
          />
        </div>

        <div class="field">
          <label class="label" for="verify-code">Код из письма</label>
          <input
            id="verify-code"
            class="input code-input"
            type="text"
            inputmode="numeric"
            pattern="[0-9]*"
            maxlength="6"
            :value="code"
            required
            :disabled="isLoading"
            placeholder="000000"
            autocomplete="one-time-code"
            @input="onCodeInput"
          />
          <div class="field-hint">
            Код действует {{ expiresMinutes }} минут
          </div>
        </div>

        <button
          type="submit"
          class="btn btn-primary btn-block btn-lg auth-submit"
          :disabled="isLoading"
        >
          <span v-if="isLoading" class="spinner" aria-hidden="true"></span>
          {{ isLoading ? 'Проверяем…' : 'Подтвердить почту' }}
        </button>
      </form>

      <div class="auth-divider">или</div>

      <TurnstileCaptcha
        v-if="captchaSiteKey"
        ref="captchaRef"
        :site-key="captchaSiteKey"
        @verified="captchaToken = $event"
      />

      <button
        type="button"
        class="btn btn-ghost btn-block"
        :disabled="resendLoading || resendIn > 0 || isLoading"
        @click="resend"
      >
        <span v-if="resendLoading" class="spinner" aria-hidden="true"></span>
        {{ resendLabel }}
      </button>

      <p class="auth-footer">
        Уже подтвердили?
        <RouterLink :to="{ name: 'login-page' }">Войти</RouterLink>
        <span class="dot-sep">·</span>
        <a href="/about/">О проекте</a>
      </p>
    </section>
  </main>
</template>
