<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

const props = defineProps({
  annotation: {
    type: Object,
    required: true,
  },
  color: {
    type: String,
    default: '#61afef',
  },
  isHost: {
    type: Boolean,
    default: false,
  },
  lineStart: {
    type: Number,
    default: null,
  },
  lineEnd: {
    type: Number,
    default: null,
  },
  position: {
    type: Object,
    default: () => ({ top: 0, left: 0 }),
  },
})

const emit = defineEmits(['close', 'remove'])

const panel = ref(null)

const lineLabel = computed(() => {
  const start = props.lineStart ?? props.annotation.selection.startLineNumber
  const end = props.lineEnd ?? props.annotation.selection.endLineNumber
  return start === end ? `Строка ${start}` : `Строки ${start}–${end}`
})

function close() {
  emit('close')
}

function onPointerDown(event) {
  if (panel.value?.contains(event.target)) return
  if (event.target.closest?.('[data-annotation-popup-ignore]')) return
  close()
}

function onKeydown(event) {
  if (event.key === 'Escape') close()
}

onMounted(() => {
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
      ref="panel"
      class="annotation-popup"
      role="dialog"
      aria-label="Пометка на коде"
      :style="{ top: `${position.top}px`, left: `${position.left}px` }"
    >
      <div class="annotation-popup-head">
        <span class="annotation-popup-author" :style="{ color }">
          {{ annotation.username }}
        </span>
        <span class="annotation-popup-file">{{ annotation.file }}</span>
        <button
          type="button"
          class="annotation-popup-close"
          aria-label="Закрыть"
          @click="emit('close')"
        >
          ×
        </button>
      </div>

      <p class="annotation-popup-lines">{{ lineLabel }}</p>
      <p class="annotation-popup-text">{{ annotation.text }}</p>

      <div v-if="isHost" class="annotation-popup-actions">
        <button
          type="button"
          class="annotation-popup-remove"
          @click="emit('remove')"
        >
          Удалить пометку
        </button>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.annotation-popup {
  position: fixed;
  z-index: 60;
  width: 300px;
  max-width: calc(100vw - 16px);
  max-height: calc(100vh - 16px);
  overflow-y: auto;
  padding: 12px;
  border: 1px solid var(--border-strong);
  border-radius: 12px;
  background: var(--surface);
  box-shadow: var(--shadow);
}

.annotation-popup-head {
  display: flex;
  align-items: center;
  gap: 8px;
}

.annotation-popup-author {
  overflow: hidden;
  font-size: 13px;
  font-weight: 700;
  white-space: nowrap;
  text-overflow: ellipsis;
}

.annotation-popup-file {
  margin-left: auto;
  flex: none;
  color: var(--text-dim);
  font-family: var(--font-mono);
  font-size: 11px;
}

.annotation-popup-close {
  flex: none;
  width: 22px;
  height: 22px;
  display: grid;
  place-items: center;
  padding: 0;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: var(--text-dim);
  font-size: 17px;
  line-height: 1;
  cursor: pointer;
  transition: background-color 0.16s ease, color 0.16s ease;
}

.annotation-popup-close:hover {
  background: var(--surface-2);
  color: var(--text);
}

.annotation-popup-lines {
  margin: 6px 0 0;
  color: var(--text-dim);
  font-size: 11.5px;
}

.annotation-popup-text {
  margin: 8px 0 0;
  max-height: 220px;
  overflow-y: auto;
  color: var(--text);
  font-size: 13.5px;
  line-height: 1.5;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.annotation-popup-actions {
  display: flex;
  justify-content: flex-end;
  margin-top: 12px;
  padding-top: 10px;
  border-top: 1px solid var(--border);
}

.annotation-popup-remove {
  padding: 6px 10px;
  border: 1px solid rgba(229, 83, 61, 0.4);
  border-radius: 7px;
  background: transparent;
  color: var(--danger-text);
  font-size: 12.5px;
  font-weight: 600;
  cursor: pointer;
  transition: background-color 0.16s ease, border-color 0.16s ease,
    color 0.16s ease;
}

.annotation-popup-remove:hover {
  background: var(--danger-soft);
  border-color: var(--danger);
  color: var(--danger-text-hover);
}
</style>
