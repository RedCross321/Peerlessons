<script setup>
import axios from 'axios';
import { ref, onMounted } from 'vue';

const message = ref("")
const error = ref("")

const fetchGreeting = async () => {
  try {
    const response = await axios.get('/api')
    message.value = response.data.text
  } catch(err) {
    error.value = "Ошибка при обращение к api" + err.message
  }
}

onMounted(() => fetchGreeting())
</script>

<template>
  <p>Главная страничка сайта</p>
  <p>{{ message }}</p>
</template>

<style scoped></style>
