<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import api, { getUser, isLoggedIn, logout } from '@/auth'
import { getErrorMessages } from '@/utils/errors'
import { setPageSeo } from '@/utils/seo'

const router = useRouter()
const authenticated = isLoggedIn()
const username = getUser()?.username || 'участник'

const aliasInput = ref('')
const joinError = ref('')
const joinLoading = ref(false)

setPageSeo({
  title: 'Peerlessons — совместное редактирование кода в реальном времени',
  description:
    'Peerlessons — self-hosted платформа для совместного редактирования кода: комнаты, Monaco Editor, передача прав и живой предпросмотр HTML/CSS/JS.',
  path: '/',
  robots: 'index, follow',
})

function handleLogout() {
  logout()
  router.replace({ name: 'login-page' })
}

// Принимаем и псевдоним, и целую ссылку вида https://…/room/<alias>.
function normalizeRoomKey(value) {
  const trimmed = String(value || '').trim()
  const match = trimmed.match(/\/room\/([^/?#]+)/i)
  const raw = match ? match[1] : trimmed

  try {
    return decodeURIComponent(raw).trim()
  } catch {
    return raw.trim()
  }
}

async function join() {
  const alias = normalizeRoomKey(aliasInput.value)
  joinError.value = ''

  if (!alias) {
    joinError.value = 'Введите псевдоним комнаты'
    return
  }

  joinLoading.value = true
  try {
    const { data } = await api.get(
      `/rooms/by-alias/${encodeURIComponent(alias)}`
    )
    router.push(`/room/${data.alias || data.id}`)
  } catch (err) {
    joinError.value = getErrorMessages(err, 'Не удалось найти комнату')[0]
  } finally {
    joinLoading.value = false
  }
}
</script>

<template>
  <main class="page">
    <div class="home-inner">
      <div class="home-brand">
        <span class="brand">
          <span class="brand-mark">/</span>
          <span class="brand-name">Peerlessons</span>
        </span>
      </div>

      <span class="home-rule"></span>

      <h1 class="home-title">
        Пишите код <span>вместе</span>,<br>
        прямо сейчас
      </h1>

      <p v-if="authenticated" class="home-lead">
        Создайте комнату и делитесь редактором в реальном времени — без установки
        и лишних настроек.
      </p>
      <p v-else class="home-lead">
        Создайте аккаунт, чтобы открыть комнату, пригласить участников и писать
        код вместе в реальном времени.
      </p>

      <div class="home-actions">
        <template v-if="authenticated">
          <RouterLink to="/create-room" class="btn btn-primary btn-lg">
            Создать комнату
          </RouterLink>
          <RouterLink to="/account" class="btn btn-secondary btn-lg">
            Личный кабинет
          </RouterLink>
          <button
            type="button"
            class="btn btn-ghost btn-lg btn-logout"
            @click="handleLogout"
          >
            Выйти из аккаунта
          </button>
        </template>
        <template v-else>
          <RouterLink to="/register" class="btn btn-primary btn-lg">
            Создать аккаунт
          </RouterLink>
          <RouterLink to="/login" class="btn btn-ghost btn-lg">
            Войти
          </RouterLink>
        </template>
      </div>

      <form
        v-if="authenticated"
        class="home-join"
        novalidate
        @submit.prevent="join"
      >
        <label class="home-join-label" for="homeAlias">
          Подключиться по названию комнаты
        </label>
        <div class="home-join-row">
          <input
            id="homeAlias"
            v-model="aliasInput"
            class="input"
            type="text"
            placeholder="algoritmy-na-python"
            maxlength="120"
            autocomplete="off"
            spellcheck="false"
            :disabled="joinLoading"
            @input="joinError = ''"
          />
          <button
            type="submit"
            class="btn btn-secondary btn-lg"
            :disabled="joinLoading"
          >
            {{ joinLoading ? 'Ищем…' : 'Подключиться' }}
          </button>
        </div>
        <p v-if="joinError" class="field-error home-join-error">
          {{ joinError }}
        </p>
      </form>

      <p v-if="authenticated" class="home-note">
        Вы вошли как <b>{{ username }}</b>
      </p>
      <p v-else class="home-note">
        <a href="/about/">Подробнее о проекте</a>
      </p>
    </div>
  </main>
</template>

<style scoped>
.home-join {
  max-width: 520px;
  margin: 30px auto 0;
}

.home-join-label {
  display: block;
  margin-bottom: 8px;
  color: var(--text-dim);
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}

.home-join-row {
  display: flex;
  gap: 10px;
}

.home-join-row .input {
  flex: 1;
  min-width: 0;
}

.home-join-error {
  margin-top: 8px;
}

@media (max-width: 560px) {
  .home-join-row {
    flex-direction: column;
  }
}
</style>
