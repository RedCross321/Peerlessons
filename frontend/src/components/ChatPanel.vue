<script setup>
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import api from '@/auth'
import { getErrorMessages } from '@/utils/errors'

const props = defineProps({
  socket: {
    type: Object,
    default: null
  },
  send: {
    type: Function,
    required: true
  },
  roomId: {
    type: [String, Number],
    default: ''
  },
  myUserId: {
    type: [Number, String],
    default: null
  },
  myUsername: {
    type: String,
    default: ''
  },
  isHost: {
    type: Boolean,
    default: false
  },
  connectionStatus: {
    type: String,
    default: 'connecting'
  },
  userColor: {
    type: Function,
    required: true
  }
})

const REACTIONS = ['👍', '❤️', '😄', '🎉', '👀', '✅']
const PAGE_SIZE = 50

const messages = ref([])
const pinned = ref([])
const text = ref('')
const listEl = ref(null)
const expanded = ref(true)
const unreadCount = ref(0)
const mentionCount = ref(0)
const hasMore = ref(false)
const loadingMore = ref(false)
const historyError = ref('')
const reactionPickerId = ref(null)
const copiedKey = ref('')
const pendingDeleteId = ref(null)
const typingUsers = ref({})
const typingTimers = new Map()

let attachedSocket = null
let readTimer = null
let typingSendTimer = null
let typingLastSentAt = 0
let ignoreScrollRead = false
let deleteTimer = null

const canSend = computed(
  () =>
    props.connectionStatus === 'online' && text.value.trim().length > 0
)

const typingText = computed(() => {
  const names = Object.values(typingUsers.value)
  if (!names.length) return ''
  if (names.length === 1) return `${names[0]} печатает…`
  if (names.length === 2) return `${names[0]} и ${names[1]} печатают…`
  return 'Несколько человек печатают…'
})

function normalizeMessage(message) {
  if (!message || message.id == null) return null

  return {
    ...message,
    mentions: Array.isArray(message.mentions) ? message.mentions : [],
    reactions: Array.isArray(message.reactions) ? message.reactions : []
  }
}

function applyRoomState(data) {
  resetTyping()

  messages.value = (Array.isArray(data.chatMessages) ? data.chatMessages : [])
    .map(normalizeMessage)
    .filter(Boolean)
  unreadCount.value = Number(data.chatUnreadCount) || 0
  mentionCount.value = Number(data.chatMentionCount) || 0
  hasMore.value = Boolean(data.chatHasMore)
  historyError.value = ''
  reactionPickerId.value = null
  applyPinned(data.chatPinned)

  nextTick(() => scrollToBottom(true))
}

function addMessage(raw) {
  const message = normalizeMessage(raw)
  if (!message) return
  if (messages.value.some((item) => item.id === message.id)) return

  const wasAtBottom = expanded.value && isAtBottom()

  messages.value.push(message)
  clearTypingFor(message.user_id)
  nextTick(() => scrollToBottom(wasAtBottom))

  if (message.user_id === props.myUserId) {
    nextTick(() => scrollToBottom(true))
    scheduleRead(true)
    return
  }

  if (expanded.value && !document.hidden && wasAtBottom) {
    scheduleRead()
    return
  }

  unreadCount.value += 1
  if (message.mentions.includes(props.myUserId)) {
    mentionCount.value += 1
  }
}

function isAtBottom() {
  const list = listEl.value
  if (!list) return false
  return list.scrollHeight - list.scrollTop - list.clientHeight < 80
}

function scrollToBottom(force = false) {
  const list = listEl.value
  if (!list) return
  if (!force && list.scrollHeight - list.scrollTop - list.clientHeight > 80) {
    return
  }

  ignoreScrollRead = true
  list.scrollTop = list.scrollHeight
  setTimeout(() => {
    ignoreScrollRead = false
  }, 200)
}

function onScroll() {
  if (ignoreScrollRead) return
  if (expanded.value && isAtBottom()) scheduleRead(true)
}

function scheduleRead(force = false) {
  if (!expanded.value || props.connectionStatus !== 'online') return
  if (!force && (!isAtBottom() || document.hidden)) return

  clearTimeout(readTimer)
  readTimer = setTimeout(() => {
    readTimer = null
    if (!expanded.value) return
    if (!force && !isAtBottom()) return

    const last = messages.value[messages.value.length - 1]
    if (!last) return

    props.send({ type: 'chat-mark-read', message_id: last.id })
    unreadCount.value = 0
    mentionCount.value = 0
  }, 500)
}

function sendMessage() {
  const value = text.value.trim()
  if (!value || props.connectionStatus !== 'online') return

  stopTyping()
  props.send({ type: 'chat-message', text: value })
  text.value = ''

  nextTick(() => scrollToBottom(true))
  scheduleRead(true)
}

function toggleExpanded() {
  expanded.value = !expanded.value

  if (!expanded.value) {
    clearTimeout(readTimer)
    readTimer = null
    return
  }

  nextTick(() => {
    scrollToBottom(true)
    scheduleRead(true)
  })
}

function noteTyping() {
  if (props.connectionStatus !== 'online' || !text.value.trim()) return

  const now = Date.now()
  if (now - typingLastSentAt > 1500) {
    typingLastSentAt = now
    props.send({ type: 'chat-typing', typing: true })
  }

  clearTimeout(typingSendTimer)
  typingSendTimer = setTimeout(stopTyping, 2500)
}

function stopTyping() {
  clearTimeout(typingSendTimer)
  typingSendTimer = null

  if (!typingLastSentAt) return
  typingLastSentAt = 0
  props.send({ type: 'chat-typing', typing: false })
}

function clearTypingFor(userId) {
  const key = String(userId)
  const timer = typingTimers.get(key)
  if (timer) clearTimeout(timer)
  typingTimers.delete(key)

  if (key in typingUsers.value) {
    const next = { ...typingUsers.value }
    delete next[key]
    typingUsers.value = next
  }
}

function applyTyping(data) {
  if (!data || data.user_id === props.myUserId) return

  const key = String(data.user_id)
  const timer = typingTimers.get(key)
  if (timer) clearTimeout(timer)
  typingTimers.delete(key)

  if (!data.typing) {
    clearTypingFor(data.user_id)
    return
  }

  typingUsers.value = {
    ...typingUsers.value,
    [key]: data.username || 'Участник'
  }
  typingTimers.set(
    key,
    setTimeout(() => clearTypingFor(data.user_id), 3000)
  )
}

function resetTyping() {
  for (const timer of typingTimers.values()) clearTimeout(timer)
  typingTimers.clear()
  typingUsers.value = {}
  clearTimeout(typingSendTimer)
  typingSendTimer = null
  typingLastSentAt = 0
}

function applyReactions(messageId, reactions) {
  const normalized = Array.isArray(reactions) ? reactions : []

  const message = messages.value.find((item) => item.id === messageId)
  if (message) message.reactions = normalized

  const pinnedMessage = pinned.value.find((item) => item.id === messageId)
  if (pinnedMessage) pinnedMessage.reactions = normalized
}

function toggleReactionPicker(messageId) {
  reactionPickerId.value =
    reactionPickerId.value === messageId ? null : messageId
}

function toggleReaction(message, emoji) {
  reactionPickerId.value = null
  props.send({ type: 'chat-reaction', message_id: message.id, emoji })
}

function applyPinned(list) {
  pinned.value = (Array.isArray(list) ? list : [])
    .map(normalizeMessage)
    .filter(Boolean)

  const pinnedIds = new Set(pinned.value.map((message) => message.id))
  for (const message of messages.value) {
    message.pinned = pinnedIds.has(message.id)
  }
}

function togglePin(message) {
  if (!props.isHost) return
  props.send({
    type: 'chat-pin',
    message_id: message.id,
    pinned: !message.pinned
  })
}

function requestDeleteMessage(message) {
  if (pendingDeleteId.value !== message.id) {
    pendingDeleteId.value = message.id
    clearTimeout(deleteTimer)
    deleteTimer = setTimeout(() => {
      pendingDeleteId.value = null
      deleteTimer = null
    }, 3000)
    return
  }

  clearTimeout(deleteTimer)
  deleteTimer = null
  pendingDeleteId.value = null
  props.send({ type: 'chat-delete', message_id: message.id })
}

function onEscape() {
  reactionPickerId.value = null
  pendingDeleteId.value = null
}

function scrollToMessage(messageId) {
  nextTick(() => {
    const element = document.getElementById(`chat-msg-${messageId}`)
    element?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
  })
}

async function loadMore() {
  if (loadingMore.value || !hasMore.value || !messages.value.length) return
  if (!props.roomId) return

  loadingMore.value = true
  historyError.value = ''

  const list = listEl.value
  const previousHeight = list?.scrollHeight || 0
  const previousTop = list?.scrollTop || 0

  try {
    const oldest = messages.value[0]
    const { data } = await api.get(`/room/${props.roomId}/chat`, {
      params: { before_id: oldest.id, limit: PAGE_SIZE }
    })

    const page = Array.isArray(data)
      ? data.map(normalizeMessage).filter(Boolean)
      : []

    if (!page.length) {
      hasMore.value = false
      return
    }

    const existing = new Set(messages.value.map((message) => message.id))
    const older = page.filter((message) => !existing.has(message.id))

    messages.value = [...older, ...messages.value]
    hasMore.value = page.length === PAGE_SIZE

    await nextTick()
    if (list) {
      list.scrollTop = list.scrollHeight - previousHeight + previousTop
    }
  } catch (err) {
    historyError.value = getErrorMessages(
      err,
      'Не удалось загрузить историю'
    )[0]
  } finally {
    loadingMore.value = false
  }
}

function parseParts(value) {
  const source = String(value || '')
  const parts = []
  const fence = /```([A-Za-z0-9_+-]*)\n?([\s\S]*?)```/g
  let last = 0
  let match

  while ((match = fence.exec(source))) {
    if (match.index > last) {
      parts.push({ type: 'text', text: source.slice(last, match.index) })
    }
    parts.push({
      type: 'code',
      lang: match[1],
      code: match[2].replace(/\n$/, '')
    })
    last = fence.lastIndex
  }

  if (last < source.length) {
    parts.push({ type: 'text', text: source.slice(last) })
  }

  return parts
}

function splitSegments(value) {
  const source = String(value || '')
  const segments = []
  const pattern = /(@[A-Za-z0-9_]+)|`([^`\n]+)`/g
  let last = 0
  let match

  while ((match = pattern.exec(source))) {
    if (match.index > last) {
      segments.push({ type: 'text', value: source.slice(last, match.index) })
    }

    if (match[1]) {
      segments.push({ type: 'mention', value: match[1].slice(1) })
    } else {
      segments.push({ type: 'inline-code', value: match[2] })
    }

    last = pattern.lastIndex
  }

  if (last < source.length) {
    segments.push({ type: 'text', value: source.slice(last) })
  }

  return segments
}

function isMyMention(name) {
  return String(name || '').toLowerCase() === props.myUsername.toLowerCase()
}

function copyCode(code, key) {
  if (!navigator.clipboard?.writeText) return

  navigator.clipboard
    .writeText(code)
    .then(() => {
      copiedKey.value = key
      setTimeout(() => {
        if (copiedKey.value === key) copiedKey.value = ''
      }, 1500)
    })
    .catch(() => {})
}

function formatTime(value) {
  if (!value) return ''

  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''

  return date.toLocaleTimeString('ru-RU', {
    hour: '2-digit',
    minute: '2-digit'
  })
}

function formatDateTime(value) {
  if (!value) return ''

  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''

  return date.toLocaleString('ru-RU', {
    day: 'numeric',
    month: 'long',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit'
  })
}

function onSocketMessage(event) {
  let data
  try {
    data = JSON.parse(event.data)
  } catch {
    return
  }
  if (!data || typeof data !== 'object') return

  if (data.type === 'room-state') {
    applyRoomState(data)
    return
  }
  if (data.type === 'chat-message' && data.message) {
    addMessage(data.message)
    return
  }
  if (data.type === 'chat-typing') {
    applyTyping(data)
    return
  }
  if (data.type === 'chat-reaction') {
    applyReactions(data.message_id, data.reactions)
    return
  }
  if (data.type === 'chat-pinned') {
    applyPinned(data.pinned)
    return
  }
  if (data.type === 'chat-deleted') {
    messages.value = messages.value.filter(
      (message) => message.id !== data.message_id
    )
    if (pendingDeleteId.value === data.message_id) {
      pendingDeleteId.value = null
    }
    if (Array.isArray(data.pinned)) applyPinned(data.pinned)
    return
  }
  if (data.type === 'chat-reset') {
    messages.value = (Array.isArray(data.messages) ? data.messages : [])
      .map(normalizeMessage)
      .filter(Boolean)
    applyPinned(data.pinned)
    historyError.value = ''
    reactionPickerId.value = null
    nextTick(() => scrollToBottom(true))
  }
}

function detachSocket() {
  if (!attachedSocket) return
  attachedSocket.removeEventListener('message', onSocketMessage)
  attachedSocket = null
}

function resetChat() {
  messages.value = []
  pinned.value = []
  unreadCount.value = 0
  mentionCount.value = 0
  hasMore.value = false
  loadingMore.value = false
  historyError.value = ''
  reactionPickerId.value = null
  pendingDeleteId.value = null
  resetTyping()

  clearTimeout(readTimer)
  readTimer = null
  clearTimeout(deleteTimer)
  deleteTimer = null
}

function attachSocket(socket) {
  detachSocket()
  if (!socket) return

  resetChat()
  attachedSocket = socket
  socket.addEventListener('message', onSocketMessage)
}

watch(
  () => props.socket,
  (socket) => {
    attachSocket(socket)
    if (!socket) resetChat()
  },
  { immediate: true, flush: 'sync' }
)

onBeforeUnmount(() => {
  detachSocket()
  clearTimeout(readTimer)
  clearTimeout(typingSendTimer)
  clearTimeout(deleteTimer)
  resetTyping()
})
</script>

<template>
  <section
    id="roomChat"
    class="side-card chat-card"
    role="region"
    aria-label="Чат комнаты"
    tabindex="-1"
    @keydown.esc="onEscape"
  >
    <h3 class="side-title chat-title">
      <span class="chat-title-main">
        Чат
        <span class="count">{{ messages.length }}</span>
        <span
          v-if="mentionCount"
          class="chat-unread is-mention"
          :title="`Упоминаний: ${mentionCount}`"
        >
          @{{ mentionCount }}
        </span>
        <span
          v-else-if="unreadCount"
          class="chat-unread"
          :title="`Непрочитанных: ${unreadCount}`"
        >
          {{ unreadCount }}
        </span>
      </span>

      <button
        type="button"
        class="chat-toggle"
        :aria-expanded="expanded"
        aria-controls="roomChatBody"
        :title="expanded ? 'Свернуть чат' : 'Развернуть чат'"
        @click="toggleExpanded"
      >
        {{ expanded ? '▾' : '▸' }}
      </button>
    </h3>

    <div
      v-show="expanded"
      id="roomChatBody"
      class="chat-body"
      tabindex="-1"
    >
      <div v-if="pinned.length" class="chat-pinned">
        <div
          v-for="message in pinned"
          :key="message.id"
          class="chat-pinned-row"
        >
          <button
            type="button"
            class="chat-pinned-item"
            :title="message.text"
            @click="scrollToMessage(message.id)"
          >
            <span class="chat-pinned-pin" aria-hidden="true">📌</span>
            <span class="chat-pinned-author">{{ message.username }}</span>
            <span class="chat-pinned-text">{{ message.text }}</span>
          </button>
          <button
            v-if="isHost"
            type="button"
            class="chat-pinned-remove"
            title="Открепить"
            aria-label="Открепить сообщение"
            @click.stop="togglePin(message)"
          >
            ×
          </button>
        </div>
      </div>

      <div
        ref="listEl"
        class="chat-messages"
        role="log"
        aria-live="polite"
        aria-relevant="additions text"
        @scroll="onScroll"
      >
        <button
          v-if="hasMore"
          type="button"
          class="chat-load-more"
          :disabled="loadingMore"
          @click="loadMore"
        >
          {{ loadingMore ? 'Загружаем…' : 'Загрузить ещё' }}
        </button>

        <p v-if="historyError" class="field-error chat-history-error">
          {{ historyError }}
        </p>

        <p v-if="!messages.length" class="side-empty">
          Сообщений пока нет. Напишите первым.
        </p>

        <div
          v-for="message in messages"
          :id="`chat-msg-${message.id}`"
          :key="message.id"
          :class="[
            'chat-message',
            {
              own: message.user_id === myUserId,
              mentioned: message.mentions.includes(myUserId)
            }
          ]"
        >
          <div class="chat-bubble">
            <div class="chat-meta">
              <span
                class="chat-author"
                :style="{ color: userColor(message.user_id) }"
              >
                {{ message.user_id === myUserId ? 'Вы' : message.username }}
              </span>
              <time
                class="chat-time"
                :datetime="message.created_at"
                :title="formatDateTime(message.created_at)"
              >
                {{ formatTime(message.created_at) }}
              </time>
              <button
                v-if="isHost"
                type="button"
                class="chat-pin-btn"
                :class="{ active: message.pinned }"
                :aria-pressed="message.pinned"
                :title="message.pinned ? 'Открепить сообщение' : 'Закрепить сообщение'"
                :aria-label="message.pinned ? 'Открепить сообщение' : 'Закрепить сообщение'"
                @click.stop="togglePin(message)"
              >
                📌
              </button>
              <button
                v-if="message.user_id === myUserId || isHost"
                type="button"
                class="chat-delete-btn"
                :class="{ confirm: pendingDeleteId === message.id }"
                :title="
                  pendingDeleteId === message.id
                    ? 'Нажмите ещё раз, чтобы удалить'
                    : 'Удалить сообщение'
                "
                :aria-label="
                  pendingDeleteId === message.id
                    ? 'Подтвердить удаление сообщения'
                    : 'Удалить сообщение'
                "
                @click.stop="requestDeleteMessage(message)"
              >
                ×
              </button>
            </div>

            <template
              v-for="(part, partIndex) in parseParts(message.text)"
              :key="partIndex"
            >
              <div v-if="part.type === 'code'" class="chat-code-wrap">
                <button
                  type="button"
                  class="chat-code-copy"
                  @click.stop="copyCode(part.code, `${message.id}:${partIndex}`)"
                >
                  {{
                    copiedKey === `${message.id}:${partIndex}`
                      ? 'Скопировано'
                      : 'Копировать'
                  }}
                </button>
                <pre class="chat-code"><code>{{ part.code }}</code></pre>
              </div>
              <p v-else class="chat-text">
                <template
                  v-for="(segment, segmentIndex) in splitSegments(part.text)"
                  :key="segmentIndex"
                >
                  <span
                    v-if="segment.type === 'mention'"
                    :class="[
                      'chat-mention',
                      { 'is-me': isMyMention(segment.value) }
                    ]"
                  >
                    @{{ segment.value }}
                  </span>
                  <code
                    v-else-if="segment.type === 'inline-code'"
                    class="chat-inline-code"
                  >
                    {{ segment.value }}
                  </code>
                  <template v-else>{{ segment.value }}</template>
                </template>
              </p>
            </template>

            <div class="chat-reactions">
              <button
                v-for="reaction in message.reactions"
                :key="reaction.emoji"
                type="button"
                :class="[
                  'chat-reaction',
                  { mine: reaction.user_ids.includes(myUserId) }
                ]"
                :aria-pressed="reaction.user_ids.includes(myUserId)"
                :aria-label="`${reaction.emoji}: ${reaction.count}`"
                @click.stop="toggleReaction(message, reaction.emoji)"
              >
                {{ reaction.emoji }} <span>{{ reaction.count }}</span>
              </button>

              <div class="chat-reaction-add">
                <button
                  type="button"
                  class="chat-reaction-more"
                  aria-label="Добавить реакцию"
                  title="Добавить реакцию"
                  @click.stop="toggleReactionPicker(message.id)"
                >
                  ＋
                </button>
                <div
                  v-if="reactionPickerId === message.id"
                  class="chat-reaction-picker"
                  role="group"
                  aria-label="Выбрать реакцию"
                >
                  <button
                    v-for="emoji in REACTIONS"
                    :key="emoji"
                    type="button"
                    class="chat-reaction-option"
                    :aria-label="`Реакция ${emoji}`"
                    @click.stop="toggleReaction(message, emoji)"
                  >
                    {{ emoji }}
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <p
        class="chat-typing"
        :class="{ visible: typingText }"
        aria-live="polite"
      >
        {{ typingText }}
      </p>

      <form class="chat-compose" @submit.prevent="sendMessage">
        <textarea
          v-model="text"
          class="input chat-input"
          rows="2"
          maxlength="1000"
          placeholder="Сообщение…"
          aria-label="Сообщение в чат"
          :disabled="connectionStatus !== 'online'"
          @input="noteTyping"
          @blur="stopTyping"
          @keydown.enter.exact.prevent="sendMessage"
        ></textarea>
        <button
          type="submit"
          class="btn btn-primary btn-sm chat-send"
          :disabled="!canSend"
        >
          Отправить
        </button>
      </form>
    </div>
  </section>
</template>

<style scoped>
.side-card {
  padding: 14px;
  border: 1px solid var(--border);
  border-radius: 12px;
  background: var(--surface);
}

.side-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
  color: var(--text-dim);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.count {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 20px;
  height: 20px;
  padding: 0 6px;
  border: 1px solid var(--border);
  border-radius: 999px;
  background: var(--surface-2);
  color: var(--text-muted);
  font-size: 11px;
  font-weight: 600;
  line-height: 1;
}

.side-empty {
  margin: 0;
  color: var(--text-dim);
  font-size: 13px;
  line-height: 1.5;
}

.chat-card {
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.chat-title {
  gap: 8px;
}

.chat-title-main {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
}

.chat-toggle {
  flex-shrink: 0;
  width: 22px;
  height: 22px;
  display: grid;
  place-items: center;
  padding: 0;
  border: 0;
  border-radius: 5px;
  background: transparent;
  color: var(--text-dim);
  font-size: 13px;
  line-height: 1;
  cursor: pointer;
}

.chat-toggle:hover {
  background: var(--surface-2);
  color: var(--text);
}

.chat-unread {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 18px;
  height: 18px;
  padding: 0 5px;
  border-radius: 999px;
  background: var(--accent-soft);
  color: var(--accent-strong);
  font-size: 10px;
  font-weight: 700;
  line-height: 1;
  letter-spacing: 0;
  text-transform: none;
}

.chat-unread.is-mention {
  background: var(--danger-soft);
  color: var(--danger-text);
}

.chat-body {
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.chat-pinned {
  display: flex;
  flex-direction: column;
  gap: 3px;
  max-height: 92px;
  margin-bottom: 8px;
  padding: 5px 6px;
  overflow-y: auto;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--surface-2);
}

.chat-pinned-row {
  display: flex;
  align-items: center;
  gap: 2px;
}

.chat-pinned-item {
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: baseline;
  gap: 5px;
  padding: 2px 3px;
  overflow: hidden;
  border: 0;
  border-radius: 5px;
  background: transparent;
  color: var(--text-muted);
  font-size: 11px;
  text-align: left;
  cursor: pointer;
}

.chat-pinned-item:hover {
  background: var(--surface-3);
  color: var(--text);
}

.chat-pinned-pin {
  flex-shrink: 0;
  font-size: 9px;
}

.chat-pinned-author {
  flex-shrink: 0;
  color: var(--text-dim);
  font-weight: 700;
}

.chat-pinned-text {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.chat-pinned-remove {
  flex-shrink: 0;
  width: 18px;
  height: 18px;
  display: grid;
  place-items: center;
  padding: 0;
  border: 0;
  border-radius: 4px;
  background: transparent;
  color: var(--text-dim);
  font-size: 13px;
  line-height: 1;
  cursor: pointer;
}

.chat-pinned-remove:hover {
  background: var(--danger-soft);
  color: var(--danger-text);
}

.chat-messages {
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-height: 96px;
  max-height: 280px;
  padding: 2px;
  overflow-y: auto;
  scrollbar-width: thin;
}

.chat-load-more {
  align-self: center;
  padding: 3px 10px;
  border: 1px solid var(--border);
  border-radius: 999px;
  background: transparent;
  color: var(--text-dim);
  font-size: 10.5px;
  font-weight: 600;
  cursor: pointer;
}

.chat-load-more:hover:not(:disabled) {
  background: var(--surface-2);
  color: var(--text);
}

.chat-load-more:disabled {
  opacity: 0.5;
  cursor: default;
}

.chat-history-error {
  margin: 0;
}

.chat-message {
  display: flex;
  justify-content: flex-start;
  content-visibility: auto;
  contain-intrinsic-size: 64px;
}

.chat-message.own {
  justify-content: flex-end;
}

.chat-bubble {
  max-width: 86%;
  padding: 7px 10px;
  border: 1px solid var(--border);
  border-radius: 10px 10px 10px 3px;
  background: var(--surface-2);
}

.chat-message.own .chat-bubble {
  border-color: var(--accent-border);
  border-radius: 10px 10px 3px 10px;
  background: var(--accent-soft);
}

.chat-message.mentioned .chat-bubble {
  border-color: var(--accent-border);
  box-shadow: 0 0 0 1px var(--accent-soft);
}

.chat-meta {
  display: flex;
  align-items: baseline;
  gap: 8px;
  margin-bottom: 2px;
}

.chat-message.own .chat-meta {
  justify-content: flex-end;
}

.chat-author {
  overflow: hidden;
  font-size: 11px;
  font-weight: 700;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.chat-time {
  color: var(--text-dim);
  font-size: 10px;
  white-space: nowrap;
}

.chat-pin-btn {
  flex-shrink: 0;
  padding: 0 2px;
  border: 0;
  background: transparent;
  color: var(--text-dim);
  font-size: 10px;
  line-height: 1;
  opacity: 0.55;
  cursor: pointer;
}

.chat-pin-btn:hover,
.chat-pin-btn.active {
  opacity: 1;
}

.chat-delete-btn {
  flex-shrink: 0;
  width: 18px;
  height: 18px;
  display: grid;
  place-items: center;
  padding: 0;
  border: 0;
  border-radius: 4px;
  background: transparent;
  color: var(--text-dim);
  font-size: 13px;
  line-height: 1;
  opacity: 0.55;
  cursor: pointer;
}

.chat-delete-btn:hover {
  background: var(--danger-soft);
  color: var(--danger-text);
  opacity: 1;
}

.chat-delete-btn.confirm {
  background: var(--danger);
  color: #fff;
  opacity: 1;
}

.chat-text {
  margin: 0;
  color: var(--text);
  font-size: 13px;
  line-height: 1.4;
  overflow-wrap: anywhere;
  white-space: pre-wrap;
}

.chat-mention {
  color: var(--accent-strong);
  font-weight: 600;
}

.chat-mention.is-me {
  border-radius: 3px;
  background: var(--accent-soft);
  text-decoration: underline;
}

.chat-inline-code {
  padding: 1px 4px;
  border: 1px solid var(--border);
  border-radius: 4px;
  background: var(--bg-raised);
  color: var(--accent-strong);
  font-family: var(--font-mono);
  font-size: 11.5px;
}

.chat-code-wrap {
  position: relative;
  margin: 6px 0 2px;
}

.chat-code {
  margin: 0;
  padding: 8px 10px;
  overflow-x: auto;
  border: 1px solid var(--border);
  border-radius: 7px;
  background: var(--bg-raised);
  color: var(--text);
  font-family: var(--font-mono);
  font-size: 11.5px;
  line-height: 1.45;
  white-space: pre;
}

.chat-code-copy {
  position: absolute;
  top: 4px;
  right: 4px;
  padding: 2px 6px;
  border: 1px solid var(--border);
  border-radius: 5px;
  background: var(--surface);
  color: var(--text-dim);
  font-size: 9.5px;
  font-weight: 600;
  cursor: pointer;
  opacity: 0.55;
  transition: opacity 0.16s ease, background-color 0.16s ease,
    color 0.16s ease;
}

.chat-code-wrap:hover .chat-code-copy,
.chat-code-copy:focus-visible {
  opacity: 1;
}

.chat-code-copy:hover {
  background: var(--surface-2);
  color: var(--text);
}

.chat-reactions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px;
  margin-top: 5px;
}

.chat-reaction {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  padding: 1px 6px;
  border: 1px solid var(--border);
  border-radius: 999px;
  background: var(--surface);
  color: var(--text-muted);
  font-size: 10.5px;
  line-height: 1.5;
  cursor: pointer;
}

.chat-reaction:hover {
  border-color: var(--border-strong);
  color: var(--text);
}

.chat-reaction.mine {
  border-color: var(--accent-border);
  background: var(--accent-soft);
  color: var(--accent-strong);
}

.chat-reaction-add {
  position: relative;
  display: inline-flex;
}

.chat-reaction-more {
  width: 20px;
  height: 20px;
  display: grid;
  place-items: center;
  padding: 0;
  border: 1px solid transparent;
  border-radius: 999px;
  background: transparent;
  color: var(--text-dim);
  font-size: 12px;
  line-height: 1;
  cursor: pointer;
}

.chat-reaction-more:hover {
  background: var(--surface-3);
  color: var(--text);
}

.chat-reaction-picker {
  position: absolute;
  right: 0;
  bottom: calc(100% + 4px);
  z-index: 5;
  display: flex;
  gap: 2px;
  padding: 4px;
  border: 1px solid var(--border-strong);
  border-radius: 8px;
  background: var(--surface);
  box-shadow: var(--shadow);
}

.chat-reaction-option {
  width: 24px;
  height: 24px;
  display: grid;
  place-items: center;
  padding: 0;
  border: 0;
  border-radius: 5px;
  background: transparent;
  font-size: 14px;
  line-height: 1;
  cursor: pointer;
}

.chat-reaction-option:hover {
  background: var(--surface-2);
}

.chat-typing {
  min-height: 16px;
  margin: 4px 0 0;
  color: var(--text-dim);
  font-size: 11px;
  font-style: italic;
  opacity: 0;
  transition: opacity 0.16s ease;
}

.chat-typing.visible {
  opacity: 1;
}

.chat-compose {
  display: flex;
  align-items: flex-end;
  gap: 6px;
  margin-top: 6px;
}

.chat-input {
  flex: 1;
  min-width: 0;
  min-height: 42px;
  max-height: 92px;
  padding: 8px 10px;
  font-size: 13px;
  line-height: 1.4;
  resize: none;
}

.chat-send {
  flex-shrink: 0;
  height: 42px;
}

@media (max-width: 560px) {
  .chat-messages {
    max-height: 240px;
  }

  .chat-input {
    font-size: 16px;
  }

  .chat-send {
    min-height: 44px;
  }

  .chat-toggle,
  .chat-pin-btn,
  .chat-delete-btn,
  .chat-reaction-more {
    min-width: 32px;
    min-height: 32px;
  }
}
</style>
