<script setup>
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import api, { saveAuth } from '@/auth'
import ErrorAlert from '@/components/ErrorAlert.vue'
import { getErrorMessages } from '@/utils/errors'

const router = useRouter()
const email = ref('')
const password = ref('')
const fieldErrors = ref({})
const errorMessages = ref([])
const isLoading = ref(false)

// Путь, на который нужно вернуться после входа (защищаемся от внешних редиректов).
const redirectTarget = computed(() => {
  const redirect = router.currentRoute.value.query.redirect
  return typeof redirect === 'string' && redirect.startsWith('/') ? redirect : null
})

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

  if (!validateForm()) return

  isLoading.value = true

  try {
    const payload = {
      email: email.value.trim(),
      password: password.value
    }
    const { data } = await api.post('/auth/login', payload, {
      headers: {
        'Content-Type': 'application/json'
      }
    })

    saveAuth(data.access_token, data.refresh_token, data.user)

    router.replace(redirectTarget.value || '/')
  } catch (err) {
    console.error('Ошибка входа:', err)
    errorMessages.value = getErrorMessages(err, 'Не удалось войти')
  } finally {
    isLoading.value = false
  }
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
        <h1 class="auth-title">С возвращением</h1>
        <p class="auth-sub">Войдите, чтобы продолжить работу в комнатах</p>
      </div>

      <ErrorAlert :messages="errorMessages" title="Не удалось войти" />

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

        <button
          type="submit"
          class="btn btn-primary btn-block btn-lg auth-submit"
          :disabled="isLoading"
        >
          <span v-if="isLoading" class="spinner" aria-hidden="true"></span>
          {{ isLoading ? 'Входим…' : 'Войти' }}
        </button>
      </form>

      <p class="auth-footer">
        Нет аккаунта?
        <RouterLink :to="{ name: 'reg-page', query: redirectTarget ? { redirect: redirectTarget } : {} }">
          Создать аккаунт
        </RouterLink>
      </p>
    </section>
  </main>
</template>
