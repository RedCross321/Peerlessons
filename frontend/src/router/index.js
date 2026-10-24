import { createRouter, createWebHistory } from 'vue-router'
import { isLoggedIn } from '@/auth'

import CreateRoom from '@/views/CreateRoom.vue'
import LoginPage from '@/views/LoginPage.vue'
import RegisterPage from '@/views/RegisterPage.vue'
import HomePage from '@/views/HomePage.vue'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [{
      path: "/",
      name: "index",
      component: HomePage
    },
    {
      path: "/login",
      name: "login-page",
      component: LoginPage
    },
    {
      path: "/register",
      name: "reg-page",
      component: RegisterPage
    },
    {
      path: '/create-room',
      name: 'create-room',
      component: CreateRoom,
      meta: { requiresAuth: true }
    },
    {
      path: '/room/:id',
      name: 'room',
      component: () => import('../views/CodeRoom.vue'),
      meta: { requiresAuth: true }
    },
  ],
})

router.beforeEach((to, from, next) => {
  const requiresAuth = to.matched.some(record => record.meta.requiresAuth)

  if (requiresAuth && !isLoggedIn()) {
    next({ name: 'login-page', query: { redirect: to.fullPath } })
  } else {
    next()
  }
})


export default router
