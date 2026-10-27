<script setup>
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import api, { saveAuth } from '@/auth'
import ErrorAlert from '@/components/ErrorAlert.vue'
import { getErrorMessages } from '@/utils/errors'
import { setPageSeo } from '@/utils/seo'

const router = useRouter()
const username = ref('')
const email = ref('')
const password = ref('')
const password_check = ref('')
const fieldErrors = ref({})
const errorMessages = ref([])
const successMessage = ref('')
const isLoading = ref(false)

setPageSeo({
  title: 'Регистрация — Peerlessons',
  description:
    'Создайте аккаунт Peerlessons, чтобы работать над кодом вместе в реальном времени.',
  path: '/register',
  robots: 'noindex, follow',
})

// Путь, на который нужно вернуться после регистрации и входа.
const redirectTarget = computed(() => {
  const redirect = router.currentRoute.value.query.redirect
  return typeof redirect === 'string' && redirect.startsWith('/') ? redirect : null
})

const passwordsMismatch = computed(
  () => password_check.value.length > 0 && password.value !== password_check.value
)

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

function clearFieldError(field) {
  if (errorMessages.value.length) errorMessages.value = []

  if (!fieldErrors.value[field]) return

  const next = { ...fieldErrors.value }
  delete next[field]
  fieldErrors.value = next
}

function clearPasswordErrors() {
  if (errorMessages.value.length) errorMessages.value = []

  const next = { ...fieldErrors.value }
  delete next.password
  delete next.password_check
  fieldErrors.value = next
}

function validateForm() {
  const errors = {}
  const name = username.value.trim()
  const mail = email.value.trim()

  if (!name) {
    errors.username = 'Введите имя пользователя'
  } else if (name.length < 2) {
    errors.username = 'Минимум 2 символа'
  } else if (name.length > 50) {
    errors.username = 'Максимум 50 символов'
  } else if (!/^[a-zA-Z0-9_]+$/.test(name)) {
    errors.username = 'Только латиница, цифры и знак подчёркивания'
  }

  if (!mail) {
    errors.email = 'Введите email'
  } else if (!EMAIL_RE.test(mail)) {
    errors.email = 'Некорректный email'
  }

  if (!password.value) {
    errors.password = 'Введите пароль'
  } else if (password.value.length < 8) {
    errors.password = 'Минимум 8 символов'
  }

  if (!password_check.value) {
    errors.password_check = 'Повторите пароль'
  } else if (password.value !== password_check.value) {
    errors.password_check = 'Пароли не совпадают'
  }

  fieldErrors.value = errors
  return Object.keys(errors).length === 0
}

const register_user = async () => {
  errorMessages.value = []
  successMessage.value = ''

  if (!validateForm()) return

  isLoading.value = true

  try {
    await api.post('/auth/register', {
      username: username.value.trim(),
      email: email.value.trim(),
      password: password.value
    })

    const { data: loginData } = await api.post('/auth/login', {
      email: email.value.trim(),
      password: password.value
    }, {
      headers: {
        'Content-Type': 'application/json'
      }
    })

    saveAuth(loginData.access_token, loginData.refresh_token, loginData.user)

    successMessage.value = 'Регистрация успешна! Переходим...'

    setTimeout(() => {
      router.replace(redirectTarget.value || '/')
    }, 800)
  } catch (err) {
    console.error('Ошибка при регистрации/входе:', err)
    errorMessages.value = getErrorMessages(err, 'Не удалось зарегистрироваться')
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
        <h1 class="auth-title">Создать аккаунт</h1>
        <p class="auth-sub">Пара полей — и можно приглашать в комнату</p>
      </div>

      <ErrorAlert :messages="errorMessages" title="Не удалось зарегистрироваться" />
      <div v-if="successMessage" class="alert alert-success" role="alert">
        {{ successMessage }}
      </div>

      <form class="auth-form" novalidate @submit.prevent="register_user">
        <div class="field">
          <label class="label" for="username">Имя пользователя</label>
          <input
            type="text"
            id="username"
            class="input"
            v-model="username"
            required
            :disabled="isLoading"
            :aria-invalid="!!fieldErrors.username"
            placeholder="Ваше имя"
            autocomplete="username"
            @input="clearFieldError('username')"
          />
          <div v-if="fieldErrors.username" class="field-error">
            {{ fieldErrors.username }}
          </div>
        </div>

        <div class="field">
          <label class="label" for="email">Электронная почта</label>
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
            placeholder="Минимум 8 символов"
            autocomplete="new-password"
            @input="clearPasswordErrors"
          />
          <div v-if="!fieldErrors.password" class="field-hint">
            Сложность оценивается по энтропии
          </div>
          <div v-if="fieldErrors.password" class="field-error">
            {{ fieldErrors.password }}
          </div>
        </div>

        <div class="field">
          <label class="label" for="password_check">Повторите пароль</label>
          <input
            type="password"
            id="password_check"
            class="input"
            v-model="password_check"
            required
            :disabled="isLoading"
            :aria-invalid="!!fieldErrors.password_check"
            placeholder="Ещё раз"
            autocomplete="new-password"
            @input="clearPasswordErrors"
          />
          <div v-if="fieldErrors.password_check" class="field-error">
            {{ fieldErrors.password_check }}
          </div>
          <div v-else-if="passwordsMismatch" class="field-error">
            Пароли не совпадают
          </div>
        </div>

        <button
          type="submit"
          class="btn btn-primary btn-block btn-lg auth-submit"
          :disabled="isLoading"
        >
          <span v-if="isLoading" class="spinner" aria-hidden="true"></span>
          {{ isLoading ? 'Создаём аккаунт…' : 'Зарегистрироваться' }}
        </button>
      </form>

      <p class="auth-footer">
        Уже зарегистрированы?
        <RouterLink :to="{ name: 'login-page', query: redirectTarget ? { redirect: redirectTarget } : {} }">
          Войти
        </RouterLink>
        <span class="dot-sep">·</span>
        <a href="/about/">О проекте</a>
      </p>
    </section>
  </main>
</template>
