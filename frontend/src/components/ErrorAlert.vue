<script setup>
import { computed } from 'vue'

const props = defineProps({
  messages: {
    type: [String, Array],
    default: () => []
  },
  title: {
    type: String,
    default: 'Проверьте введённые данные'
  }
})

const list = computed(() => {
  if (!props.messages) return []

  const values = Array.isArray(props.messages) ? props.messages : [props.messages]

  return values.filter(value => typeof value === 'string' && value.trim())
})
</script>

<template>
  <div
    v-if="list.length"
    class="alert alert-error form-alert"
    role="alert"
    aria-live="assertive"
  >
    <span class="form-alert-icon" aria-hidden="true">!</span>
    <div class="form-alert-body">
      <p class="form-alert-title">{{ title }}</p>
      <ul class="form-alert-list">
        <li v-for="(message, index) in list" :key="index">{{ message }}</li>
      </ul>
    </div>
  </div>
</template>

<style scoped>
.form-alert {
  display: flex;
  align-items: flex-start;
  gap: 12px;
}

.form-alert-icon {
  flex: none;
  width: 20px;
  height: 20px;
  margin-top: 1px;
  display: grid;
  place-items: center;
  border-radius: 50%;
  background: rgba(229, 83, 61, 0.22);
  color: #ffb0a3;
  font-family: var(--font-mono);
  font-size: 12px;
  font-weight: 700;
  line-height: 1;
}

.form-alert-body {
  min-width: 0;
}

.form-alert-title {
  margin: 0 0 4px;
  color: #ffc2b8;
  font-size: 13px;
  font-weight: 700;
}

.form-alert-list {
  display: flex;
  flex-direction: column;
  gap: 3px;
  margin: 0;
  padding-left: 16px;
  color: #ffb0a3;
  font-size: 13px;
}
</style>
