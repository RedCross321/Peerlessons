<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import api, { saveAuth } from '@/auth'

const router = useRouter()
const username = ref('')
const email = ref('')
const password = ref('')
const password_check = ref('')
const valid_password = ref(true)
const errorMessage = ref('')
const successMessage = ref('')
const isLoading = ref(false)

const psw_check_valid = () => {
  valid_password.value = password.value === password_check.value && password.value.length > 0
}

const register_user = async () => {
  errorMessage.value = ''
  successMessage.value = ''
  psw_check_valid()

  if (!valid_password.value) {
    errorMessage.value = 'Пароли не совпадают или слишком короткие'
    return
  }

  isLoading.value = true
  try {
    await api.post('/auth/register', {
          username: username.value,
          email: email.value,
          password: password.value
        })


    const { data: loginData } = await api.post('/auth/login', {
      email: email.value,
      password: password.value
    }, {
      headers: {
        'Content-Type': 'application/json'
      }
    })

    saveAuth(loginData.access_token, loginData.user)

    successMessage.value = 'Регистрация успешна! Переходим...'

    setTimeout(() => {
      router.push('/')
    }, 800)

  } catch (err) {
    console.error('Ошибка при регистрации/входе:', err)
    if (err.response?.status === 422) {
      const details = err.response.data.detail
      if (Array.isArray(details)) {
        errorMessage.value = details.map(e => {
          const field = e.loc?.length > 1 ? e.loc[1] : 'field'
          return `• ${field}: ${e.msg}`
        }).join('\n')
      } else {
        errorMessage.value = 'Ошибка валидации данных'
      }
    } else if (err.response?.data?.detail) {
      errorMessage.value = err.response.data.detail
    } else {
      errorMessage.value = 'Ошибка сервера. Попробуйте позже.'
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
            <h2 class="card-title text-center mb-2">Регистрация</h2>
            <p class="text-center text-muted mb-4">Введите свои данные для создания аккаунта</p>

            <div v-if="errorMessage" class="alert alert-danger" role="alert" style="white-space: pre-line;">
              {{ errorMessage }}
            </div>
            <div v-if="successMessage" class="alert alert-success" role="alert">
              {{ successMessage }}
            </div>

            <form @submit.prevent="register_user">
              <div class="mb-3">
                <label for="username" class="form-label">Имя пользователя</label>
                <input
                  type="text"
                  id="username"
                  class="form-control"
                  v-model="username"
                  required
                  :disabled="isLoading"
                  placeholder="Ваше имя"
                />
              </div>

              <div class="mb-3">
                <label for="email" class="form-label">Электронная почта</label>
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
                  @input="psw_check_valid"
                />
              </div>

              <div class="mb-3">
                <label for="password_check" class="form-label">Повторите пароль</label>
                <input
                  type="password"
                  id="password_check"
                  class="form-control"
                  v-model="password_check"
                  required
                  :disabled="isLoading"
                  @input="psw_check_valid"
                />
                <div v-if="password_check && !valid_password" class="form-text text-danger">
                  Пароли не совпадают!
                </div>
              </div>

              <button type="submit" class="btn btn-primary w-100" :disabled="isLoading || !valid_password">
                <span v-if="isLoading" class="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span>
                {{ isLoading ? 'Регистрация...' : 'Зарегистрироваться' }}
              </button>
            </form>

            <div class="text-center mt-3">
              <p class="mb-0">Уже зарегистрированы? <RouterLink :to="{ name: 'login-page' }">Войдите в систему</RouterLink></p>
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
