<script setup>
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import api, { getUser, isLoggedIn, logout } from '@/auth'
import { getErrorMessages } from '@/utils/errors'
import { setPageSeo } from '@/utils/seo'
import { collapse } from '@/motion'

const router = useRouter()
const authenticated = isLoggedIn()
const username = getUser()?.username || 'участник'

const aliasInput = ref('')
const joinError = ref('')
const joinLoading = ref(false)

const rooms = ref([])
const roomsLoading = ref(false)
const roomsError = ref('')
const deleteError = ref('')
const pendingDeleteId = ref(null)
const deletingId = ref(null)

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

function roomLink(room) {
  return `/room/${room.alias || room.id}`
}

function showRoomKey(room) {
  return roomKey(room).trim().toLowerCase() !== String(room.title || '').trim().toLowerCase()
}

function roomKey(room) {
  return room.alias || String(room.id).slice(0, 8)
}

function formatCreatedAt(value) {
  if (!value) return ''

  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''

  return date.toLocaleDateString('ru-RU', {
    day: 'numeric',
    month: 'long',
    year: 'numeric'
  })
}

async function loadRooms() {
  if (!authenticated) return

  roomsLoading.value = true
  roomsError.value = ''
  deleteError.value = ''

  try {
    const { data } = await api.get('/rooms/mine')
    rooms.value = Array.isArray(data) ? data : []
  } catch (err) {
    roomsError.value = getErrorMessages(err, 'Не удалось загрузить комнаты')[0]
  } finally {
    roomsLoading.value = false
  }
}

function requestDelete(room) {
  if (deletingId.value) return

  deleteError.value = ''
  pendingDeleteId.value = room.id
}

function cancelDelete() {
  pendingDeleteId.value = null
}

function removeRoom(id) {
  rooms.value = rooms.value.filter((room) => room.id !== id)
  pendingDeleteId.value = null
}

async function confirmDelete(room) {
  if (deletingId.value) return

  deletingId.value = room.id
  deleteError.value = ''

  try {
    await api.delete(`/room/${room.id}`)
    removeRoom(room.id)
  } catch (err) {
    // 404 — комнаты уже нет, убираем её из списка.
    if (err?.response?.status === 404) {
      removeRoom(room.id)
    } else {
      deleteError.value = getErrorMessages(err, 'Не удалось удалить комнату')[0]
    }
  } finally {
    deletingId.value = null
  }
}

function onRoomLeave(el, done) {
  collapse(el).then(done)
}

onMounted(() => {
  if (authenticated) loadRooms()
})
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

      <span
       
        class="home-rule"
      ></span>

      <h1 class="home-title">
        Пишите код
        <span class="home-title-accent">вместе<i
            class="home-title-underline"
            aria-hidden="true"
          ></i></span>,<br>
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
          <RouterLink to="/settings" class="btn btn-secondary btn-lg">
            Настройки
          </RouterLink>
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

      <section
        v-if="authenticated"
       
        class="home-rooms"
        aria-labelledby="homeRoomsTitle"
      >
        <div class="home-rooms-head">
          <h2 id="homeRoomsTitle" class="home-rooms-title">Мои комнаты</h2>
          <span
            v-if="rooms.length"
            class="home-rooms-count"
          >{{ rooms.length }}</span>
        </div>

        <ul v-if="roomsLoading && !rooms.length" class="home-rooms-list" aria-hidden="true">
          <li v-for="n in 3" :key="n" class="home-room home-room--skeleton">
            <span class="skeleton skeleton-title"></span>
            <span class="skeleton skeleton-meta"></span>
          </li>
        </ul>

        <div
          v-else-if="roomsError"
          class="home-rooms-state home-rooms-state-error"
        >
          <p class="field-error">{{ roomsError }}</p>
          <button
            type="button"
            class="btn btn-secondary btn-sm"
            @click="loadRooms"
          >
            Повторить
          </button>
        </div>

        <p v-else-if="!rooms.length" class="home-rooms-state">
          Здесь появятся комнаты, которые вы создали.
        </p>

        <TransitionGroup
          v-else
          tag="ul"
          class="home-rooms-list"
          :css="false"
          @leave="onRoomLeave"
        >
          <li
            v-for="room in rooms"
            :key="room.id"
            class="home-room"
          >
            <div class="home-room-main">
              <RouterLink class="home-room-title" :to="roomLink(room)">
                {{ room.title }}
              </RouterLink>
              <p class="home-room-meta">
                <span v-if="showRoomKey(room)" class="home-room-alias">{{ roomKey(room) }}</span>
                <span
                  v-if="formatCreatedAt(room.created_at)"
                  class="home-room-date"
                >
                  создана {{ formatCreatedAt(room.created_at) }}
                </span>
              </p>
            </div>

            <div class="home-room-actions">
              <template v-if="pendingDeleteId === room.id">
                <button
                  type="button"
                  class="btn btn-danger btn-sm"
                  :disabled="deletingId !== null"
                  @click="confirmDelete(room)"
                >
                  {{ deletingId === room.id ? 'Удаляем…' : 'Точно удалить' }}
                </button>
                <button
                  type="button"
                  class="btn btn-ghost btn-sm"
                  :disabled="deletingId !== null"
                  @click="cancelDelete"
                >
                  Отмена
                </button>
              </template>
              <template v-else>
                <RouterLink
                  :to="roomLink(room)"
                  class="btn btn-secondary btn-sm"
                >
                  Открыть
                </RouterLink>
                <button
                  type="button"
                  class="btn btn-sm home-room-delete"
                  :disabled="deletingId !== null"
                  @click="requestDelete(room)"
                >
                  Удалить
                </button>
              </template>
            </div>
          </li>
        </TransitionGroup>

        <p v-if="deleteError" class="field-error home-rooms-delete-error">
          {{ deleteError }}
        </p>
      </section>

      <div v-if="authenticated" class="home-account">
        <p class="home-note">
          Вы вошли как <b>{{ username }}</b>
        </p>
        <button
          type="button"
          class="btn btn-ghost btn-sm btn-logout"
          @click="handleLogout"
        >
          Выйти
        </button>
      </div>
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

.home-rooms {
  max-width: 520px;
  margin: 34px auto 0;
  text-align: left;
}

.home-rooms-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}

.home-rooms-title {
  margin: 0;
  color: var(--text-dim);
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}

.home-rooms-count {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 22px;
  height: 22px;
  padding: 0 7px;
  border: 1px solid var(--border);
  border-radius: 999px;
  background: var(--surface-2);
  color: var(--text-muted);
  font-size: 12px;
  font-weight: 600;
  line-height: 1;
}

.home-rooms-state {
  margin: 0;
  color: var(--text-muted);
  font-size: 13.5px;
}

.home-rooms-state-error {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 10px;
}

.home-rooms-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.home-room {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 13px 15px;
  border: 1px solid var(--border);
  border-radius: 12px;
  background: var(--card-bg, var(--surface));
  box-shadow: 0 1px 0 var(--card-highlight) inset;
  transition: border-color var(--dur) var(--ease-out),
    transform 0.5s var(--ease-spring, var(--ease-out)),
    box-shadow var(--dur) var(--ease-out);
  content-visibility: auto;
  contain-intrinsic-size: 64px;
}

.home-room:not(.home-room--skeleton):hover {
  border-color: var(--border-strong);
  transform: translateY(-2px);
  box-shadow: 0 1px 0 var(--card-highlight) inset,
    0 14px 30px -18px rgba(0, 0, 0, 0.55);
}

.home-room--skeleton {
  flex-direction: column;
  align-items: flex-start;
  gap: 8px;
}

.skeleton {
  display: block;
  height: 12px;
  border-radius: 6px;
  background: linear-gradient(
    90deg,
    var(--surface-2) 0%,
    var(--surface-3) 40%,
    var(--surface-2) 80%
  );
  background-size: 300% 100%;
  animation: skeleton-shimmer 1.4s var(--ease-in-out) infinite;
}

.skeleton-title {
  width: 46%;
  height: 14px;
}

.skeleton-meta {
  width: 28%;
}

@keyframes skeleton-shimmer {
  from {
    background-position: 100% 0;
  }
  to {
    background-position: -50% 0;
  }
}

.home-room-main {
  min-width: 0;
}

.home-room-title {
  display: block;
  transition: color var(--dur-fast) var(--ease-out);
  overflow: hidden;
  color: var(--text);
  font-size: 14.5px;
  font-weight: 600;
  text-decoration: none;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.home-room-title:hover {
  color: var(--accent-strong);
}

.home-room-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin: 4px 0 0;
  color: var(--text-dim);
  font-size: 12px;
}

.home-room-alias {
  font-family: var(--font-mono);
}

.home-room-actions {
  display: flex;
  flex-shrink: 0;
  gap: 8px;
}

.home-room-delete {
  background: transparent;
  border-color: var(--border);
  color: var(--danger-text);
}

.home-room-delete:hover:not(:disabled) {
  background: var(--danger-soft);
  border-color: var(--danger);
  color: var(--danger-text-hover);
}

.home-rooms-delete-error {
  margin-top: 10px;
}

.home-account {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 14px;
  flex-wrap: wrap;
  margin-top: 30px;
}

.home-account .home-note {
  margin-top: 0;
}

@media (max-width: 560px) {
  .home-join-row {
    flex-direction: column;
  }

  .home-room {
    flex-direction: column;
    align-items: stretch;
  }

  .home-room-actions {
    width: 100%;
  }

  .home-room-actions .btn {
    flex: 1;
  }
}
</style>
