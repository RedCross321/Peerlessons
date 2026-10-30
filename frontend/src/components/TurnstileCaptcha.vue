<script setup>
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useTheme } from '@/theme'

const props = defineProps({
  siteKey: {
    type: String,
    default: ''
  }
})

const emit = defineEmits(['verified'])

const { resolvedTheme } = useTheme()

const container = ref(null)
let widgetId = null
let scriptPromise = null

function loadScript() {
  if (window.turnstile) return Promise.resolve(window.turnstile)

  if (!scriptPromise) {
    scriptPromise = new Promise((resolve, reject) => {
      const script = document.createElement('script')
      script.src =
        'https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit'
      script.async = true
      script.defer = true
      script.onload = () => resolve(window.turnstile)
      script.onerror = () => reject(new Error('Turnstile script failed'))
      document.head.appendChild(script)
    })
  }

  return scriptPromise
}

async function renderWidget() {
  if (!props.siteKey || !container.value) return

  try {
    const turnstile = await loadScript()
    if (!container.value) return

    widgetId = turnstile.render(container.value, {
      sitekey: props.siteKey,
      theme: resolvedTheme.value === 'light' ? 'light' : 'dark',
      language: 'ru',
      size: 'flexible',
      callback: (token) => emit('verified', token),
      'expired-callback': () => emit('verified', ''),
      'error-callback': () => emit('verified', '')
    })
  } catch (error) {
    console.error('Turnstile init failed:', error)
    emit('verified', '')
  }
}

function reset() {
  emit('verified', '')

  if (widgetId !== null && window.turnstile) {
    window.turnstile.reset(widgetId)
  }
}

onMounted(renderWidget)

// Виджет Turnstile не умеет менять тему на лету — перерисовываем его.
watch(resolvedTheme, () => {
  if (widgetId !== null && window.turnstile) {
    window.turnstile.remove(widgetId)
  }
  widgetId = null
  emit('verified', '')
  renderWidget()
})

onBeforeUnmount(() => {
  if (widgetId !== null && window.turnstile) {
    window.turnstile.remove(widgetId)
  }
  widgetId = null
})

defineExpose({ reset })
</script>

<template>
  <div v-if="siteKey" ref="container" class="turnstile" />
</template>
