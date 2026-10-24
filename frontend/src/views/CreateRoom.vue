<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import api from '@/auth'

const router = useRouter()
const title = ref('Новая комната для кодирования')
const isLoading = ref(false)
const errorMessage = ref('')

async function create() {
  if (!title.value.trim()) {
    errorMessage.value = 'Название комнаты не может быть пустым'
    return
  }

  isLoading.value = true
  errorMessage.value = ''

  try {
    const { data } = await api.post('/room', { title: title.value })

    router.push(`/room/${data.id}`)
  } catch (err) {
    console.error('Ошибка создания комнаты:', err)
    errorMessage.value = err.response?.data?.detail || 'Не удалось создать комнату'
  } finally {
    isLoading.value = false
  }
}
</script>

<template>
  <div class="container mt-5">
    <div class="row justify-content-center">
      <div class="col-md-6">
        <div class="card shadow-sm">
          <div class="card-body p-4">
            <h2 class="card-title text-center mb-4">Создать комнату</h2>

            <div v-if="errorMessage" class="alert alert-danger">
              {{ errorMessage }}
            </div>

            <form @submit.prevent="create">
              <div class="mb-3">
                <label for="roomTitle" class="form-label">Название комнаты</label>
                <input
                  type="text"
                  id="roomTitle"
                  class="form-control"
                  v-model="title"
                  required
                  :disabled="isLoading"
                  placeholder="Например: Алгоритмы на Python"
                />
              </div>

              <button type="submit" class="btn btn-primary w-100" :disabled="isLoading">
                <span v-if="isLoading" class="spinner-border spinner-border-sm me-2"></span>
                {{ isLoading ? 'Создание...' : 'Создать' }}
              </button>
            </form>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
