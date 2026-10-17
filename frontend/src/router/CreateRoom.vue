<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import api from '@/auth'

const router = useRouter()
const title = ref('Тестовая комната')

async function create() {
  const { data } = await api.post('/api/rooms', { title: title.value })
  // Сохраняем себя как ведущего
  localStorage.setItem('user_id', '1')
  localStorage.setItem('username', 'Ведущий')
  router.push(`/room/${data.id}`)
}
</script>

<template>
  <div style="padding: 40px">
    <h2>Создать комнату</h2>
    <input v-model="title" />
    <button @click="create">Создать</button>
  </div>
</template>
