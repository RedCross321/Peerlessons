import { createRouter, createWebHistory } from 'vue-router'
import { isLoggedIn } from '@/auth'

import CreateRoom from '@/views/CreateRoom.vue'
import LoginPage from '@/views/LoginPage.vue'
import RegisterPage from '@/views/RegisterPage.vue'
import HomePage from '@/views/HomePage.vue'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: "/",
      name: "index",
      component: HomePage,
      meta: { public: true }
    },
    {
      path: "/login",
      name: "login-page",
      component: LoginPage,
      meta: { public: true, guestOnly: true }
    },
    {
      path: "/register",
      name: "reg-page",
      component: RegisterPage,
      meta: { public: true, guestOnly: true }
    },
    {
      path: '/create-room',
      name: 'create-room',
      component: CreateRoom,
    },
    {
      path: '/room/:id',
      name: 'room',
      component: () => import('../views/CodeRoom.vue'),
    },
    {
      path: '/:pathMatch(.*)*',
      name: 'not-found',
      redirect: { name: 'index' }
    },
  ],
})

// Все маршруты, кроме помеченных meta.public, требуют авторизации.
// Неавторизованного пользователя отправляем на вход, запоминая исходный путь.
router.beforeEach((to, from, next) => {
  const authenticated = isLoggedIn()

  if (!to.meta.public && !authenticated) {
    next({ name: 'login-page', query: { redirect: to.fullPath } })
    return
  }

  // Залогиненному пользователю незачем видеть страницы входа и регистрации.
  if (to.meta.guestOnly && authenticated) {
    next({ name: 'index' })
    return
  }

  next()
})

export default router
