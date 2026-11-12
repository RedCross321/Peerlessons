<script setup>
import { ref } from 'vue'

defineOptions({ inheritAttrs: false })

const model = defineModel({ type: String, default: '' })
const visible = ref(false)
</script>

<template>
  <div class="password-input">
    <input
      v-bind="$attrs"
      v-model="model"
      :type="visible ? 'text' : 'password'"
      class="input password-input__field"
    />
    <button
      type="button"
      class="password-input__toggle"
      :aria-label="visible ? 'Скрыть пароль' : 'Показать пароль'"
      :aria-pressed="visible"
      :title="visible ? 'Скрыть пароль' : 'Показать пароль'"
      :disabled="$attrs.disabled === true || $attrs.disabled === ''"
      @click="visible = !visible"
    >
      <svg
        v-if="!visible"
        viewBox="0 0 24 24"
        width="18"
        height="18"
        fill="none"
        stroke="currentColor"
        stroke-width="2"
        stroke-linecap="round"
        stroke-linejoin="round"
        aria-hidden="true"
      >
        <path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z" />
        <circle cx="12" cy="12" r="3" />
      </svg>
      <svg
        v-else
        viewBox="0 0 24 24"
        width="18"
        height="18"
        fill="none"
        stroke="currentColor"
        stroke-width="2"
        stroke-linecap="round"
        stroke-linejoin="round"
        aria-hidden="true"
      >
        <path d="M10.6 5.1A10.4 10.4 0 0 1 12 5c6.5 0 10 7 10 7a17.6 17.6 0 0 1-2.6 3.5" />
        <path d="M6.6 6.6A17.4 17.4 0 0 0 2 12s3.5 7 10 7a9.7 9.7 0 0 0 5.4-1.6" />
        <path d="M9.9 9.9a3 3 0 0 0 4.2 4.2" />
        <path d="M2 2l20 20" />
      </svg>
    </button>
  </div>
</template>

<style scoped>
.password-input {
  position: relative;
  width: 100%;
}

.password-input__field {
  padding-right: 46px;
}

.password-input__toggle {
  position: absolute;
  top: 50%;
  right: 6px;
  transform: translateY(-50%);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  padding: 0;
  border: 0;
  border-radius: 8px;
  background: transparent;
  color: var(--text-muted, var(--placeholder));
  cursor: pointer;
  transition: color 0.16s ease, background-color 0.16s ease;
}

.password-input__toggle:hover:not(:disabled) {
  color: var(--text);
  background: var(--accent-soft);
}

.password-input__toggle:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 1px;
}

.password-input__toggle:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
</style>
