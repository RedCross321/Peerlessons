<script setup>
import { nextTick, onBeforeUnmount, onMounted, ref } from 'vue'

const props = defineProps({
  mode: {
    type: String,
    default: 'create',
  },
  fileName: {
    type: String,
    default: '',
  },
  error: {
    type: String,
    default: '',
  },
  busy: {
    type: Boolean,
    default: false,
  },
  position: {
    type: Object,
    default: () => ({ top: 0, left: 0 }),
  },
})

const emit = defineEmits(['submit', 'close'])

const panel = ref(null)
const input = ref(null)
const name = ref('')

function close() {
  emit('close')
}

function submit() {
  if (props.busy) return
  emit('submit', props.mode === 'create' ? name.value : props.fileName)
}

function onPointerDown(event) {
  if (panel.value?.contains(event.target)) return
  if (event.target.closest?.('[data-file-dialog-trigger]')) return
  close()
}

function onKeydown(event) {
  if (event.key === 'Escape') close()
}

onMounted(() => {
  if (props.mode === 'create') {
    nextTick(() => input.value?.focus())
  }

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
    <form
      ref="panel"
      class="file-dialog"
      role="dialog"
      :aria-label="mode === 'create' ? 'Новый файл' : 'Удаление файла'"
      :style="{ top: `${position.top}px`, left: `${position.left}px` }"
      @submit.prevent="submit"
    >
      <p class="file-dialog-title">
        {{ mode === 'create' ? 'Новый файл' : 'Удалить файл?' }}
      </p>

      <template v-if="mode === 'create'">
        <label class="label" for="new-room-file">Имя файла</label>
        <input
          id="new-room-file"
          ref="input"
          v-model="name"
          class="input file-dialog-input"
          type="text"
          placeholder="например, about.html"
          maxlength="64"
          autocomplete="off"
          spellcheck="false"
          :disabled="busy"
        />
        <p class="field-hint">Доступны расширения .html, .css и .js</p>
      </template>

      <p v-else class="file-dialog-text">
        Файл <b>{{ fileName }}</b> будет удалён у всех участников.
      </p>

      <p v-if="error" class="field-error file-dialog-error">{{ error }}</p>

      <div class="file-dialog-actions">
        <button
          type="submit"
          class="btn btn-xs"
          :class="mode === 'create' ? 'btn-primary' : 'btn-danger'"
          :disabled="busy"
        >
          {{ mode === 'create' ? 'Создать' : 'Удалить' }}
        </button>
        <button
          type="button"
          class="btn btn-ghost btn-xs"
          @click="emit('close')"
        >
          Отмена
        </button>
      </div>
    </form>
  </Teleport>
</template>

<style scoped>
.file-dialog {
  position: fixed;
  z-index: 60;
  width: 260px;
  max-width: calc(100vw - 16px);
  padding: 14px;
  border: 1px solid var(--border-strong);
  border-radius: 12px;
  background: var(--surface);
  box-shadow: var(--shadow);
}

.file-dialog-title {
  margin: 0 0 10px;
  font-size: 14px;
  font-weight: 700;
}

.file-dialog-input {
  margin: 6px 0 8px;
  padding: 9px 11px;
  font-size: 13px;
}

.file-dialog-text {
  margin: 0 0 10px;
  color: var(--text-muted);
  font-size: 13px;
  line-height: 1.5;
}

.file-dialog-text b {
  color: var(--text);
}

.file-dialog-error {
  margin: 8px 0 0;
}

.file-dialog-actions {
  display: flex;
  gap: 8px;
  margin-top: 12px;
}
</style>
