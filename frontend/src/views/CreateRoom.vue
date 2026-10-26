<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import api from '@/auth'
import ErrorAlert from '@/components/ErrorAlert.vue'
import { getErrorMessages } from '@/utils/errors'

const router = useRouter()
const title = ref('')
const titleError = ref('')
const isLoading = ref(false)
const errorMessages = ref([])

function clearTitleError() {
  titleError.value = ''
  if (errorMessages.value.length) errorMessages.value = []
}

function validate() {
  const value = title.value.trim()

  if (!value) {
    titleError.value = 'Введите название комнаты'
    return false
  }

  if (value.length < 3) {
    titleError.value = 'Минимум 3 символа'
    return false
  }

  titleError.value = ''
  return true
}

async function create() {
  errorMessages.value = []

  if (!validate()) return

  isLoading.value = true

  try {
    const { data } = await api.post('/room', { title: title.value.trim() })

    router.push(`/room/${data.id}`)
  } catch (err) {
    console.error('Ошибка создания комнаты:', err)
    errorMessages.value = getErrorMessages(err, 'Не удалось создать комнату')
  } finally {
    isLoading.value = false
  }
}
</script>

<template>
  <main class="page">
    <section class="card auth-card">
      <div class="auth-head">
        <RouterLink to="/" class="brand auth-brand">
          <span class="brand-mark">/</span>
          <span class="brand-name">Peerlessons</span>
        </RouterLink>
        <h1 class="auth-title">Новая комната</h1>
        <p class="auth-sub">Дайте комнате имя — остальное настроится само</p>
      </div>

      <ErrorAlert :messages="errorMessages" title="Не удалось создать комнату" />

      <form class="auth-form" novalidate @submit.prevent="create">
        <div class="field">
          <label class="label" for="roomTitle">Название комнаты</label>
          <input
            type="text"
            id="roomTitle"
            class="input"
            v-model="title"
            required
            :disabled="isLoading"
            :aria-invalid="!!titleError"
            placeholder="Например: Алгоритмы на Python"
            maxlength="80"
            @input="clearTitleError"
          />
          <div v-if="titleError" class="field-error">
            {{ titleError }}
          </div>
        </div>

        <button
          type="submit"
          class="btn btn-primary btn-block btn-lg auth-submit"
          :disabled="isLoading"
        >
          <span v-if="isLoading" class="spinner" aria-hidden="true"></span>
          {{ isLoading ? 'Создаём комнату…' : 'Создать комнату' }}
        </button>

        <RouterLink to="/" class="btn btn-ghost btn-block btn-lg cancel-link">
          Отмена
        </RouterLink>
      </form>
    </section>
  </main>
</template>
