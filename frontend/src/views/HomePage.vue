<script setup>
import { useRouter } from 'vue-router'
import { getUser, isLoggedIn, logout } from '@/auth'
import { setPageSeo } from '@/utils/seo'

const router = useRouter()
const authenticated = isLoggedIn()
const username = getUser()?.username || 'участник'

setPageSeo({
  title: 'Peerlessons — совместное редактирование кода в реальном времени',
  description:
    'Peerlessons — self-hosted платформа для совместного редактирования кода: комнаты, Monaco Editor, передача прав и живой предпросмотр HTML/CSS/JS.',
  path: '/',
  robots: 'index, follow',
})

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

      <p v-if="authenticated" class="home-lead">
        Создайте комнату и делитесь редактором в реальном времени — без установки
        и лишних настроек.
      </p>
      <p v-else class="home-lead">
        Создайте аккаунт, чтобы открыть комнату, пригласить участников и писать
        код вместе в реальном времени.
      </p>

      <div class="home-actions">
        <template v-if="authenticated">
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
        </template>
        <template v-else>
          <RouterLink to="/register" class="btn btn-primary btn-lg">
            Создать аккаунт
          </RouterLink>
          <RouterLink to="/login" class="btn btn-ghost btn-lg">
            Войти
          </RouterLink>
        </template>
      </div>

      <p v-if="authenticated" class="home-note">
        Вы вошли как <b>{{ username }}</b>
      </p>
      <p v-else class="home-note">
        <a href="/about/">Подробнее о проекте</a>
      </p>
    </div>
  </main>
</template>
