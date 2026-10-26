<script setup>
import { useRouter } from 'vue-router'
import { getUser, logout } from '@/auth'

const router = useRouter()
const username = getUser()?.username || 'участник'

function handleLogout() {
  logout()
  router.replace({ name: 'login-page' })
}
</script>

<template>
  <main class="page">
    <div class="home-inner">
      <div class="home-brand">
        <span class="brand">
          <span class="brand-mark">/</span>
          <span class="brand-name">Peerlessons</span>
        </span>
      </div>

      <span class="home-rule"></span>

      <h1 class="home-title">
        Пишите код <span>вместе</span>,<br>
        прямо сейчас
      </h1>

      <p class="home-lead">
        Создайте комнату и делитесь редактором в реальном времени — без установки
        и лишних настроек.
      </p>

      <div class="home-actions">
        <RouterLink to="/create-room" class="btn btn-primary btn-lg">
          Создать комнату
        </RouterLink>
        <button
          type="button"
          class="btn btn-ghost btn-lg btn-logout"
          @click="handleLogout"
        >
          Выйти из аккаунта
        </button>
      </div>

      <p class="home-note">Вы вошли как <b>{{ username }}</b></p>
    </div>
  </main>
</template>
