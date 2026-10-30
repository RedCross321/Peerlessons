<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import api, { saveAuth, saveUser } from '@/auth'
import ErrorAlert from '@/components/ErrorAlert.vue'
import { useTheme } from '@/theme'
import { getErrorMessages } from '@/utils/errors'
import { setPageSeo } from '@/utils/seo'

const route = useRoute()
const router = useRouter()

const loading = ref(true)
const account = ref(null)
const errorMessages = ref([])
const successMessage = ref('')

const username = ref('')
const usernameLoading = ref(false)

const newEmail = ref('')
const emailPassword = ref('')
const emailCode = ref('')
const emailLoading = ref(false)
const pendingEmail = ref(null)

const currentPassword = ref('')
const newPassword = ref('')
const newPasswordCheck = ref('')
const passwordLoading = ref(false)

const totpEnabled = ref(false)
const totpSetup = ref(null)
const setupPassword = ref('')
const totpCode = ref('')
const totpLoading = ref(false)
const recoveryCodes = ref([])
const disablePassword = ref('')
const disableCode = ref('')

const emailChangeToken = computed(() => String(route.query.email_change_token || ''))

// ===== Разделы настроек =====
const settingsSections = [
  {
    id: 'profile',
    label: 'Профиль',
    icon: 'M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2M12 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8z',
  },
  {
    id: 'security',
    label: 'Безопасность',
    icon: 'M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z',
  },
  {
    id: 'appearance',
    label: 'Оформление',
    icon: 'M12 17a5 5 0 1 0 0-10 5 5 0 0 0 0 10zM12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42',
  },
]

function readSectionFromQuery() {
  const tab = String(route.query.tab || '')
  return settingsSections.some((section) => section.id === tab) ? tab : 'profile'
}

const activeSection = ref(readSectionFromQuery())

watch(
  () => route.query.tab,
  () => {
    activeSection.value = readSectionFromQuery()
  },
)

function selectSection(id) {
  if (activeSection.value === id) return
  activeSection.value = id

  const query = { ...route.query }
  if (id === 'profile') {
    delete query.tab
  } else {
    query.tab = id
  }

  router.replace({ query })
}

// ===== Тема =====
const { themePreference, resolvedTheme, setTheme } = useTheme()

const themeOptions = [
  { value: 'system', label: 'Системная', description: 'Как в настройках ОС' },
  { value: 'dark', label: 'Тёмная', description: 'Всегда тёмная' },
  { value: 'light', label: 'Светлая', description: 'Всегда светлая' },
]

const resolvedThemeLabel = computed(() => (resolvedTheme.value === 'light' ? 'светлая' : 'тёмная'))

setPageSeo({
  title: 'Настройки — Peerlessons',
  description:
    'Настройки аккаунта Peerlessons: профиль, пароль, двухфакторная аутентификация и тема оформления.',
  path: '/settings',
  robots: 'noindex, nofollow',
  canonical: false,
})

function clearMessages() {
  errorMessages.value = []
  successMessage.value = ''
}

function applyUser(user) {
  account.value = { ...(account.value || {}), ...user }
  username.value = user.username || ''
  saveUser({
    id: user.id,
    username: user.username,
    email: user.email,
    is_active: user.is_active,
  })
}

function applyAccount(data) {
  account.value = data
  username.value = data.username || ''
  totpEnabled.value = Boolean(data.totp_enabled)
  pendingEmail.value = data.pending_email || null
  saveUser({
    id: data.id,
    username: data.username,
    email: data.email,
    is_active: data.is_active,
  })
}

async function loadAccount() {
  loading.value = true

  try {
    const { data } = await api.get('/account')
    applyAccount(data)
  } catch (err) {
    console.error('Ошибка загрузки аккаунта:', err)
    errorMessages.value = getErrorMessages(err, 'Не удалось загрузить аккаунт')
  } finally {
    loading.value = false
  }
}

async function saveUsername() {
  clearMessages()

  if (!username.value.trim()) {
    errorMessages.value = ['Введите имя пользователя']
    return
  }

  usernameLoading.value = true

  try {
    const { data } = await api.patch('/account/username', {
      username: username.value.trim(),
    })
    applyUser(data)
    successMessage.value = 'Логин обновлён'
  } catch (err) {
    errorMessages.value = getErrorMessages(err, 'Не удалось изменить логин')
  } finally {
    usernameLoading.value = false
  }
}

async function changePassword() {
  clearMessages()

  if (!currentPassword.value) {
    errorMessages.value = ['Введите текущий пароль']
    return
  }

  if (newPassword.value.length < 8) {
    errorMessages.value = ['Новый пароль должен содержать минимум 8 символов']
    return
  }

  if (newPassword.value !== newPasswordCheck.value) {
    errorMessages.value = ['Пароли не совпадают']
    return
  }

  passwordLoading.value = true

  try {
    const { data } = await api.post('/account/password', {
      current_password: currentPassword.value,
      new_password: newPassword.value,
    })

    saveAuth(data.access_token, data.refresh_token, data.user)
    applyUser(data.user)

    currentPassword.value = ''
    newPassword.value = ''
    newPasswordCheck.value = ''
    successMessage.value = 'Пароль изменён. Остальные сессии будут завершены.'
  } catch (err) {
    errorMessages.value = getErrorMessages(err, 'Не удалось изменить пароль')
  } finally {
    passwordLoading.value = false
  }
}

async function changeEmail() {
  clearMessages()

  if (!newEmail.value.trim()) {
    errorMessages.value = ['Введите новую почту']
    return
  }

  if (!emailPassword.value) {
    errorMessages.value = ['Введите текущий пароль']
    return
  }

  emailLoading.value = true

  try {
    const { data } = await api.post('/account/email', {
      password: emailPassword.value,
      new_email: newEmail.value.trim(),
    })

    if (data.status === 'pending') {
      pendingEmail.value = data.email
      emailCode.value = ''
      emailPassword.value = ''
      successMessage.value = 'Код подтверждения отправлен на новую почту'
    } else {
      applyUser(data)
      pendingEmail.value = null
      newEmail.value = ''
      emailPassword.value = ''
      successMessage.value = 'Почта обновлена'
    }
  } catch (err) {
    errorMessages.value = getErrorMessages(err, 'Не удалось изменить почту')
  } finally {
    emailLoading.value = false
  }
}

async function confirmEmailChange(useToken = false) {
  clearMessages()

  const payload = useToken ? { token: emailChangeToken.value } : { code: emailCode.value.trim() }

  if (!useToken && payload.code.length !== 6) {
    errorMessages.value = ['Введите 6-значный код из письма']
    return
  }

  emailLoading.value = true

  try {
    const { data } = await api.post('/account/email/confirm', payload)
    applyUser(data)
    pendingEmail.value = null
    emailCode.value = ''
    newEmail.value = ''
    successMessage.value = 'Почта подтверждена и обновлена'

    if (emailChangeToken.value) {
      // Убираем токен из адреса, сохраняя выбранный раздел настроек.
      const query = { ...route.query }
      delete query.email_change_token
      router.replace({ query })
    }
  } catch (err) {
    errorMessages.value = getErrorMessages(err, 'Не удалось подтвердить почту')
  } finally {
    emailLoading.value = false
  }
}

async function startTotpSetup() {
  clearMessages()

  if (!setupPassword.value) {
    errorMessages.value = ['Введите текущий пароль']
    return
  }

  totpLoading.value = true

  try {
    const { data } = await api.post('/account/totp/setup', {
      password: setupPassword.value,
    })
    totpSetup.value = data
    totpCode.value = ''
    recoveryCodes.value = []
    setupPassword.value = ''
    successMessage.value = 'Отсканируйте QR-код и введите код из приложения'
  } catch (err) {
    errorMessages.value = getErrorMessages(err, 'Не удалось начать настройку TOTP')
  } finally {
    totpLoading.value = false
  }
}

async function enableTotp() {
  clearMessages()

  if (!totpCode.value.trim()) {
    errorMessages.value = ['Введите код из приложения']
    return
  }

  totpLoading.value = true

  try {
    const { data } = await api.post('/account/totp/enable', {
      code: totpCode.value.trim(),
    })
    recoveryCodes.value = data.recovery_codes || []
    totpEnabled.value = true
    totpSetup.value = null
    totpCode.value = ''
    account.value = { ...(account.value || {}), totp_enabled: true }
    successMessage.value =
      'TOTP включён. Сохраните коды восстановления — они показываются один раз.'
  } catch (err) {
    errorMessages.value = getErrorMessages(err, 'Не удалось включить TOTP')
  } finally {
    totpLoading.value = false
  }
}

function cancelTotpSetup() {
  totpSetup.value = null
  totpCode.value = ''
  setupPassword.value = ''
  clearMessages()
}

async function disableTotp() {
  clearMessages()

  if (!disablePassword.value) {
    errorMessages.value = ['Введите пароль']
    return
  }

  if (!disableCode.value.trim()) {
    errorMessages.value = ['Введите код из приложения']
    return
  }

  totpLoading.value = true

  try {
    await api.post('/account/totp/disable', {
      password: disablePassword.value,
      code: disableCode.value.trim(),
    })
    totpEnabled.value = false
    account.value = { ...(account.value || {}), totp_enabled: false }
    disablePassword.value = ''
    disableCode.value = ''
    recoveryCodes.value = []
    successMessage.value = 'TOTP отключён'
  } catch (err) {
    errorMessages.value = getErrorMessages(err, 'Не удалось отключить TOTP')
  } finally {
    totpLoading.value = false
  }
}

async function copyRecoveryCodes() {
  try {
    await navigator.clipboard.writeText(recoveryCodes.value.join('\n'))
    successMessage.value = 'Коды восстановления скопированы'
  } catch {
    successMessage.value = 'Не удалось скопировать коды — выделите их вручную'
  }
}

onMounted(loadAccount)
</script>

<template>
  <main class="page">
    <div class="account-inner">
      <div class="account-head">
        <RouterLink to="/" class="brand brand--compact">
          <span class="brand-mark">/</span>
          <span class="brand-name">Peerlessons</span>
        </RouterLink>
        <RouterLink to="/" class="btn btn-ghost btn-sm"> На главную </RouterLink>
      </div>

      <ErrorAlert :messages="errorMessages" title="Не удалось сохранить изменения" />
      <div v-if="successMessage" class="alert alert-success" role="alert">
        {{ successMessage }}
      </div>

      <div v-if="loading" class="card account-card account-loading">
        <span class="spinner" aria-hidden="true"></span>
        <span>Загружаем аккаунт…</span>
      </div>

      <div v-else-if="account" class="settings-layout">
        <aside class="card settings-nav">
          <p class="settings-nav-title">Настройки</p>
          <nav class="settings-nav-list" aria-label="Разделы настроек">
            <button
              v-for="section in settingsSections"
              :key="section.id"
              type="button"
              class="settings-nav-item"
              :class="{ 'is-active': activeSection === section.id }"
              :aria-current="activeSection === section.id ? 'page' : undefined"
              @click="selectSection(section.id)"
            >
              <svg
                class="settings-nav-icon"
                viewBox="0 0 24 24"
                width="18"
                height="18"
                fill="none"
                stroke="currentColor"
                stroke-width="1.7"
                stroke-linecap="round"
                stroke-linejoin="round"
                aria-hidden="true"
              >
                <path :d="section.icon" />
              </svg>
              <span>{{ section.label }}</span>
            </button>
          </nav>
        </aside>

        <div class="settings-content">
          <section v-show="activeSection === 'profile'" class="card account-card">
            <h2 class="account-section-title">Профиль</h2>
            <p class="account-section-sub">
              Текущая почта: <b>{{ account.email }}</b>
            </p>

            <form class="auth-form" novalidate @submit.prevent="saveUsername">
              <div class="field">
                <label class="label" for="account-username">Логин</label>
                <input
                  id="account-username"
                  class="input"
                  type="text"
                  v-model="username"
                  required
                  :disabled="usernameLoading"
                  maxlength="50"
                  autocomplete="username"
                />
              </div>
              <div class="account-actions">
                <button type="submit" class="btn btn-primary" :disabled="usernameLoading">
                  <span v-if="usernameLoading" class="spinner" aria-hidden="true"></span>
                  Сохранить логин
                </button>
              </div>
            </form>

            <div class="account-section">
              <h3 class="account-section-title account-section-title--small">Изменить почту</h3>
              <p class="account-section-sub">На новую почту придёт код подтверждения.</p>

              <form class="auth-form" novalidate @submit.prevent="changeEmail">
                <div class="field">
                  <label class="label" for="account-new-email"> Новая почта </label>
                  <input
                    id="account-new-email"
                    class="input"
                    type="email"
                    v-model="newEmail"
                    required
                    :disabled="emailLoading"
                    placeholder="new@example.com"
                    autocomplete="email"
                  />
                </div>
                <div class="field">
                  <label class="label" for="account-email-password"> Текущий пароль </label>
                  <input
                    id="account-email-password"
                    class="input"
                    type="password"
                    v-model="emailPassword"
                    required
                    :disabled="emailLoading"
                    autocomplete="current-password"
                  />
                </div>
                <div class="account-actions">
                  <button type="submit" class="btn btn-primary" :disabled="emailLoading">
                    <span v-if="emailLoading" class="spinner" aria-hidden="true"></span>
                    Изменить почту
                  </button>
                </div>
              </form>

              <div v-if="pendingEmail" class="account-pending">
                <p class="account-pending-title">
                  Ожидает подтверждения: <b>{{ pendingEmail }}</b>
                </p>
                <div class="field">
                  <label class="label" for="account-email-code"> Код из письма </label>
                  <input
                    id="account-email-code"
                    class="input code-input"
                    type="text"
                    inputmode="numeric"
                    maxlength="6"
                    v-model="emailCode"
                    :disabled="emailLoading"
                    placeholder="000000"
                    autocomplete="one-time-code"
                  />
                </div>
                <div class="account-actions">
                  <button
                    type="button"
                    class="btn btn-primary"
                    :disabled="emailLoading"
                    @click="confirmEmailChange(false)"
                  >
                    Подтвердить код
                  </button>
                  <button
                    v-if="emailChangeToken"
                    type="button"
                    class="btn btn-ghost"
                    :disabled="emailLoading"
                    @click="confirmEmailChange(true)"
                  >
                    Подтвердить по ссылке
                  </button>
                </div>
              </div>
              <div v-else-if="emailChangeToken" class="account-pending">
                <p class="account-pending-title">Есть ссылка подтверждения новой почты.</p>
                <button
                  type="button"
                  class="btn btn-primary"
                  :disabled="emailLoading"
                  @click="confirmEmailChange(true)"
                >
                  Подтвердить новую почту
                </button>
              </div>
            </div>
          </section>

          <section v-show="activeSection === 'security'" class="card account-card">
            <h2 class="account-section-title">Безопасность</h2>
            <p class="account-section-sub">Пароль и двухфакторная аутентификация.</p>

            <div class="account-section">
              <h3 class="account-section-title account-section-title--small">Пароль</h3>
              <p class="account-section-sub">
                После смены пароля остальные сессии будут завершены.
              </p>

              <form class="auth-form" novalidate @submit.prevent="changePassword">
                <div class="field">
                  <label class="label" for="account-current-password"> Текущий пароль </label>
                  <input
                    id="account-current-password"
                    class="input"
                    type="password"
                    v-model="currentPassword"
                    required
                    :disabled="passwordLoading"
                    autocomplete="current-password"
                  />
                </div>
                <div class="field">
                  <label class="label" for="account-new-password"> Новый пароль </label>
                  <input
                    id="account-new-password"
                    class="input"
                    type="password"
                    v-model="newPassword"
                    required
                    :disabled="passwordLoading"
                    placeholder="Минимум 8 символов"
                    autocomplete="new-password"
                  />
                </div>
                <div class="field">
                  <label class="label" for="account-new-password-check">
                    Повторите новый пароль
                  </label>
                  <input
                    id="account-new-password-check"
                    class="input"
                    type="password"
                    v-model="newPasswordCheck"
                    required
                    :disabled="passwordLoading"
                    autocomplete="new-password"
                  />
                </div>
                <div class="account-actions">
                  <button type="submit" class="btn btn-primary" :disabled="passwordLoading">
                    <span v-if="passwordLoading" class="spinner" aria-hidden="true"></span>
                    Изменить пароль
                  </button>
                </div>
              </form>
            </div>

            <div class="account-section">
              <h3 class="account-section-title account-section-title--small">
                Двухфакторная аутентификация
              </h3>
              <p class="account-section-sub">
                Статус:
                <span class="badge" :class="{ 'badge-accent': totpEnabled }">
                  {{ totpEnabled ? 'включена' : 'выключена' }}
                </span>
              </p>

              <template v-if="totpEnabled">
                <form class="auth-form" novalidate @submit.prevent="disableTotp">
                  <div class="field">
                    <label class="label" for="totp-disable-password"> Текущий пароль </label>
                    <input
                      id="totp-disable-password"
                      class="input"
                      type="password"
                      v-model="disablePassword"
                      required
                      :disabled="totpLoading"
                      autocomplete="current-password"
                    />
                  </div>
                  <div class="field">
                    <label class="label" for="totp-disable-code">
                      Код из приложения или код восстановления
                    </label>
                    <input
                      id="totp-disable-code"
                      class="input"
                      type="text"
                      v-model="disableCode"
                      required
                      :disabled="totpLoading"
                      placeholder="000000 или XXXX-XXXX"
                      autocomplete="one-time-code"
                      maxlength="9"
                    />
                  </div>
                  <div class="account-actions">
                    <button type="submit" class="btn btn-danger" :disabled="totpLoading">
                      <span v-if="totpLoading" class="spinner" aria-hidden="true"></span>
                      Отключить TOTP
                    </button>
                  </div>
                </form>
              </template>

              <template v-else>
                <template v-if="!totpSetup">
                  <form class="auth-form" novalidate @submit.prevent="startTotpSetup">
                    <div class="field">
                      <label class="label" for="totp-setup-password"> Текущий пароль </label>
                      <input
                        id="totp-setup-password"
                        class="input"
                        type="password"
                        v-model="setupPassword"
                        required
                        :disabled="totpLoading"
                        autocomplete="current-password"
                      />
                    </div>
                    <div class="account-actions">
                      <button type="submit" class="btn btn-primary" :disabled="totpLoading">
                        <span v-if="totpLoading" class="spinner" aria-hidden="true"></span>
                        Подключить TOTP
                      </button>
                    </div>
                  </form>
                </template>

                <template v-else>
                  <p class="account-section-sub">
                    Отсканируйте QR-код в приложении-аутентификаторе (Google Authenticator, Aegis,
                    1Password и т.п.).
                  </p>
                  <img
                    :src="totpSetup.qr_data_uri"
                    alt="QR-код для подключения TOTP"
                    class="totp-qr"
                  />
                  <p class="account-section-sub">Или введите секрет вручную:</p>
                  <code class="totp-secret">{{ totpSetup.secret }}</code>

                  <form class="auth-form" novalidate @submit.prevent="enableTotp">
                    <div class="field">
                      <label class="label" for="totp-enable-code"> Код из приложения </label>
                      <input
                        id="totp-enable-code"
                        class="input code-input"
                        type="text"
                        inputmode="numeric"
                        maxlength="6"
                        v-model="totpCode"
                        required
                        :disabled="totpLoading"
                        placeholder="000000"
                        autocomplete="one-time-code"
                      />
                    </div>
                    <div class="account-actions">
                      <button type="submit" class="btn btn-primary" :disabled="totpLoading">
                        <span v-if="totpLoading" class="spinner" aria-hidden="true"></span>
                        Включить TOTP
                      </button>
                      <button
                        type="button"
                        class="btn btn-ghost"
                        :disabled="totpLoading"
                        @click="cancelTotpSetup"
                      >
                        Отмена
                      </button>
                    </div>
                  </form>
                </template>
              </template>

              <div v-if="recoveryCodes.length" class="account-pending">
                <p class="account-pending-title">Коды восстановления</p>
                <p class="account-section-sub">
                  Сохраните их. Больше они показаны не будут. Каждый код можно использовать один
                  раз.
                </p>
                <div class="recovery-codes">
                  <code v-for="recoveryCode in recoveryCodes" :key="recoveryCode">
                    {{ recoveryCode }}
                  </code>
                </div>
                <div class="account-actions">
                  <button type="button" class="btn btn-secondary" @click="copyRecoveryCodes">
                    Скопировать коды
                  </button>
                </div>
              </div>
            </div>
          </section>

          <section v-show="activeSection === 'appearance'" class="card account-card">
            <h2 class="account-section-title">Оформление</h2>
            <p class="account-section-sub">Тема интерфейса. Выбор сохраняется в этом браузере.</p>

            <div class="theme-options" role="radiogroup" aria-label="Тема оформления">
              <button
                v-for="option in themeOptions"
                :key="option.value"
                type="button"
                class="theme-option"
                :class="[
                  `theme-option--${option.value}`,
                  { 'is-active': themePreference === option.value },
                ]"
                role="radio"
                :aria-checked="themePreference === option.value"
                @click="setTheme(option.value)"
              >
                <span class="theme-preview" aria-hidden="true">
                  <span class="theme-preview-bar"></span>
                  <span class="theme-preview-body">
                    <span class="theme-preview-side"></span>
                    <span class="theme-preview-main"></span>
                  </span>
                </span>
                <span class="theme-option-body">
                  <span class="theme-option-label">{{ option.label }}</span>
                  <span class="theme-option-desc">
                    {{ option.description }}
                  </span>
                </span>
                <span class="theme-option-check" aria-hidden="true">
                  {{ themePreference === option.value ? '✓' : '' }}
                </span>
              </button>
            </div>

            <p class="field-hint theme-hint">
              Сейчас используется
              <b>{{ resolvedThemeLabel }}</b> тема.
            </p>
          </section>
        </div>
      </div>
    </div>
  </main>
</template>
