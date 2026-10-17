<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import api, { saveAuth } from '@/auth'

const router = useRouter()
const email = ref('')
const password = ref('')
const errorMessage = ref('')

const login = async () => {
  errorMessage.value = ''
  try {
    const { data } = await api.post('/api/login', {
      email: email.value,
      password: password.value
    })
    saveAuth(data.access_token, data.user)
    router.push('/')
  } catch (err) {
    errorMessage.value = err.response?.data?.detail || 'Ошибка входа'
  }
}
</script>

<template>
  <div class="container">
    <h2>Вход</h2>
    <div v-if="errorMessage" class="alert alert-danger">{{ errorMessage }}</div>
    <form @submit.prevent="login">
      <div class="form-group">
        <label>Email</label>
        <input type="email" class="form-control" v-model="email" required />
      </div>
      <div class="form-group">
        <label>Пароль</label>
        <input type="password" class="form-control" v-model="password" required />
      </div>
      <button type="submit" class="btn btn-primary">Войти</button>
    </form>
    <p>Нет аккаунта? <RouterLink :to="{ name: 'reg-page' }">Зарегистрироваться</RouterLink></p>
  </div>
</template>
