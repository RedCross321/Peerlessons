<script setup>
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

const props = defineProps({
  participant: {
    type: Object,
    required: true,
  },
  isCurrentEditor: {
    type: Boolean,
    default: false,
  },
  annotationsBanned: {
    type: Boolean,
    default: false,
  },
  position: {
    type: Object,
    default: () => ({ top: 0, left: 0 }),
  },
})

const emit = defineEmits(['grant', 'revoke', 'kick', 'toggle-ban', 'close'])

const menu = ref(null)
const confirmKick = ref(false)

function close() {
  emit('close')
}

// Исключение защищаем вторым нажатием: случайно выкинуть человека
// одним кликом слишком легко.
function requestKick() {
  if (!confirmKick.value) {
    confirmKick.value = true
    return
  }

  emit('kick')
}

function onPointerDown(event) {
  if (menu.value?.contains(event.target)) return
  // Кнопку «три точки» обрабатывает сам список участников, чтобы можно
  // было переключать меню между пользователями.
  if (event.target.closest?.('[data-participant-menu-trigger]')) return
  close()
}

function onKeydown(event) {
  if (event.key === 'Escape') close()
}

// Меню может остаться смонтированным, если ведущий открыл действия
// сразу для другого участника — сбрасываем подтверждение и фокус.
watch(
  () => props.participant.user_id,
  () => {
    confirmKick.value = false
    nextTick(() => menu.value?.querySelector('button')?.focus())
  }
)

onMounted(() => {
  nextTick(() => menu.value?.querySelector('button')?.focus())

  document.addEventListener('pointerdown', onPointerDown, true)
  document.addEventListener('keydown', onKeydown)
  window.addEventListener('resize', close)
  window.addEventListener('scroll', close, true)
})

onBeforeUnmount(() => {
  document.removeEventListener('pointerdown', onPointerDown, true)
  document.removeEventListener('keydown', onKeydown)
  window.removeEventListener('resize', close)
  window.removeEventListener('scroll', close, true)
})
</script>

<template>
  <Teleport to="body">
    <div
      ref="menu"
      class="participant-menu"
      role="menu"
      :aria-label="`Действия: ${participant.username}`"
      :style="{ top: `${position.top}px`, left: `${position.left}px` }"
    >
      <p class="participant-menu-title">{{ participant.username }}</p>

      <button
        v-if="!isCurrentEditor"
        type="button"
        class="participant-menu-item"
        role="menuitem"
        @click="emit('grant')"
      >
        Дать права редактирования
      </button>
      <button
        v-else
        type="button"
        class="participant-menu-item"
        role="menuitem"
        @click="emit('revoke')"
      >
        Забрать права редактирования
      </button>

      <button
        type="button"
        class="participant-menu-item"
        role="menuitem"
        @click="emit('toggle-ban')"
      >
        {{ annotationsBanned ? 'Разрешить пометки' : 'Запретить пометки' }}
      </button>

      <div class="participant-menu-divider" aria-hidden="true"></div>

      <button
        type="button"
        class="participant-menu-item participant-menu-item--danger"
        :class="{ 'is-confirming': confirmKick }"
        role="menuitem"
        @click="requestKick"
      >
        {{ confirmKick ? 'Точно исключить?' : 'Исключить из комнаты' }}
      </button>
    </div>
  </Teleport>
</template>

<style scoped>
.participant-menu {
  position: fixed;
  z-index: 60;
  min-width: 220px;
  padding: 6px;
  border: 1px solid var(--border-strong);
  border-radius: 12px;
  background: var(--surface);
  box-shadow: var(--shadow);
}

.participant-menu-title {
  margin: 0;
  padding: 8px 10px 6px;
  overflow: hidden;
  color: var(--text-dim);
  font-size: 12px;
  font-weight: 700;
  white-space: nowrap;
  text-overflow: ellipsis;
}

.participant-menu-item {
  display: block;
  width: 100%;
  padding: 9px 10px;
  border: 0;
  border-radius: 8px;
  background: transparent;
  color: var(--text);
  font-size: 13.5px;
  font-weight: 500;
  text-align: left;
  cursor: pointer;
  transition: background-color 0.16s ease, color 0.16s ease;
}

.participant-menu-item:hover {
  background: var(--surface-2);
}

.participant-menu-divider {
  height: 1px;
  margin: 4px 6px;
  background: var(--border);
}

.participant-menu-item--danger {
  color: var(--danger-text);
}

.participant-menu-item--danger:hover {
  background: var(--danger-soft);
  color: var(--danger-text-hover);
}

.participant-menu-item--danger.is-confirming {
  background: var(--danger-soft);
  border: 1px solid rgba(229, 83, 61, 0.35);
  color: var(--danger-text-hover);
  font-weight: 600;
}
</style>
