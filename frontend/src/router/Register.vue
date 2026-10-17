<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import api, { saveAuth } from '@/auth'   // путь подкорректируй

const router = useRouter()
const username = ref('')
const email = ref('')
const password = ref('')
const password_check = ref('')
const valid_password = ref(true)
const errorMessage = ref('')
const successMessage = ref('')

const psw_check_valid = () => {
  valid_password.value = password.value === password_check.value
}

const register_user = async () => {
  errorMessage.value = ''
  successMessage.value = ''
  psw_check_valid()
  if (!valid_password.value) {
    errorMessage.value = 'Пароли не совпадают'
    return
  }

  try {
    const { data } = await api.post('/api/register', {
      username: username.value,
      email: email.value,
      password: password.value
    })

    // Сразу логиним
    saveAuth(data.access_token, data.user)
    successMessage.value = 'Регистрация успешна! Переходим...'

    setTimeout(() => {
      router.push('/')  // или /create-room
    }, 800)

  } catch (err) {
    if (err.response?.status === 422) {
      const details = err.response.data.detail
      errorMessage.value = Array.isArray(details)
        ? details.map(e => '• ' + e.msg.replace(/^Value error,?\s*/i, '')).join('\n')
        : 'Ошибка валидации'
    } else if (err.response?.data?.detail) {
      errorMessage.value = err.response.data.detail
    } else {
      errorMessage.value = 'Ошибка сервера'
    }
  }
}

</script>

<template>

<div class="container">
  <div class="row">
      <div class="col-md-12">
          <h2>Регистрация</h2>
          <p>Введите свои данные.</p>
          <div v-if="errorMessage" class="alert alert-danger" style="white-space: pre-line;">
            {{ errorMessage }}
          </div>
          <div v-if="successMessage" class="alert alert-success">
            {{ successMessage }}
          </div>
          <form @submit.prevent="register_user" method="post">
              <div class="form-group">
                  <label>Имя</label>
                  <input type="text" name="name" class="form-control" required v-model="username">
              </div>
              <div class="form-group">
                  <label>Электронная почта</label>
                  <input type="email" name="email" class="form-control" required v-model="email" />
              </div>
              <div class="form-group">
                  <label>Пароль</label>
                  <input type="password" name="password" class="form-control" required v-model="password">
              </div>
              <div class="form-group">
                  <label>Повторите пароль</label>
                  <input type="password" name="confirm_password" class="form-control" required v-model="password_check">
              </div>
              <p v-if="!valid_password">Пароли не совпадают!</p>
              <div class="form-group">
                  <input type="submit" name="submit" class="btn btn-primary" value="Зарегистрироваться">
              </div>
              <p>Уже зарегистрированы? <RouterLink :to="{name: 'login-page'}">Войдите в систему</RouterLink>.</p>
          </form>
      </div>
  </div>
</div>
  <!-- <RouterView></RouterView> -->
</template>

<style scoped></style>
