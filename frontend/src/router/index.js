import { createRouter, createWebHistory } from 'vue-router'
import Home from './Home.vue'
import Login from './Login.vue'
import Register from './Register.vue'
import CreateRoom from './CreateRoom.vue'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [{
      path: "/",
      name: "index",
      component: Home
    },
    {
      path: "/login",
      name: "login-page",
      component: Login
    },
    {
      path: "/register",
      name: "reg-page",
      component: Register
    },
    {
      path: '/room/:id',
      name: 'room',
      component: () => import('@/router/CodeRoom.vue')
    },
    { path: '/create-room', component: CreateRoom },
  ],
})

export default router
