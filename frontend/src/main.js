import { createApp } from 'vue'
import { createPinia } from 'pinia'

import './assets/main.css'
import './theme'
import App from './App.vue'
import router from './router'
import { initAuthRefresh } from './auth'
import { initFrontendSentry } from './observability'

const app = createApp(App)

app.use(createPinia())
app.use(router)

initAuthRefresh()
initFrontendSentry(app, router)

app.mount('#app')
