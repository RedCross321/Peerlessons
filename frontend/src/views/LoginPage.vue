<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import api, { saveAuth } from '@/auth'

const router = useRouter()
const email = ref('')
const password = ref('')
const errorMessage = ref('')
const isLoading = ref(false)

const login = async () => {
  errorMessage.value = ''
  isLoading.value = true

  try {
    const payload = {
      email: email.value,
      password: password.value
    }
    const { data } = await api.post('/auth/login', payload, {
      headers: {
        'Content-Type': 'application/json'
      }
    })

    saveAuth(data.access_token, data.user)

    const redirect = router.currentRoute.value.query.redirect
    router.push(redirect || '/')

  } catch (err) {
    console.error('Ошибка входа:', err)
    if (err.response?.status === 401) {
      errorMessage.value = 'Неверный email или пароль'
    } else if (err.response?.status === 422) {
      errorMessage.value = 'Ошибка валидации данных. Проверьте формат email.'
    } else {
      errorMessage.value = err.response?.data?.detail || 'Ошибка входа'
    }
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
            <h2 class="card-title text-center mb-4">Вход</h2>

            <div v-if="errorMessage" class="alert alert-danger" role="alert">
              {{ errorMessage }}
            </div>

            <form @submit.prevent="login">
              <div class="mb-3">
                <label for="email" class="form-label">Email</label>
                <input
                  type="email"
                  id="email"
                  class="form-control"
                  v-model="email"
                  required
                  :disabled="isLoading"
                  placeholder="name@example.com"
                />
              </div>

              <div class="mb-3">
                <label for="password" class="form-label">Пароль</label>
                <input
                  type="password"
                  id="password"
                  class="form-control"
                  v-model="password"
                  required
                  :disabled="isLoading"
                />
              </div>

              <button type="submit" class="btn btn-primary w-100" :disabled="isLoading">
                <span v-if="isLoading" class="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span>
                {{ isLoading ? 'Выполняется вход...' : 'Войти' }}
              </button>
            </form>

            <div class="text-center mt-3">
              <p class="mb-0">Нет аккаунта? <RouterLink :to="{ name: 'reg-page' }">Зарегистрироваться</RouterLink></p>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.card {
  border-radius: 0.5rem;
}
</style>
