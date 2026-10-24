<script setup>
import { ref, onMounted } from 'vue';
import api from '@/auth';

const message = ref("")
const error = ref("")

const fetchGreeting = async () => {
  try {
    const response = await api.get('/')
    message.value = response.data.text || response.data.message || 'Добро пожаловать'
  } catch(err) {
    console.error(err)
    error.value = "Ошибка при обращении к API: " + (err.response?.data?.detail || err.message)
  }
}

onMounted(() => fetchGreeting())
</script>

<template>
  <div class="container mt-5 text-center">
    <h1>Главная страница</h1>
    <p v-if="message" class="lead">{{ message }}</p>
    <p v-if="error" class="text-danger">{{ error }}</p>

    <div class="mt-4" v-if="!error">
      <RouterLink to="/create-room" class="btn btn-primary btn-lg">Создать новую комнату</RouterLink>
    </div>
  </div>
</template>
