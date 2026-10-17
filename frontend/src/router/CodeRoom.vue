<script setup>
import { ref, onMounted, onUnmounted, nextTick, watch } from 'vue'
import { useRoute } from 'vue-router'
import * as monaco from 'monaco-editor'
import { getUser } from '@/auth'

const route = useRoute()
const roomId = route.params.id

const user = getUser()
const myUserId = ref(user?.id)
const isHost = ref(false)  // определим после загрузки комнаты

const files = ref({
  'index.html': '',
  'style.css': '',
  'main.js': ''
})
const activeTab = ref('index.html')
const canEdit = ref(false)
const currentEditorName = ref(null)
const participants = ref([])
const raisedHands = ref([])   // кто поднял руку

let editor = null
let ws = null
let ignoreChanges = false

// ===== Monaco =====
onMounted(async () => {
  await nextTick()
  editor = monaco.editor.create(document.getElementById('editor'), {
    value: '',
    language: 'html',
    theme: 'vs-dark',
    readOnly: true,
    automaticLayout: true,
    minimap: { enabled: false },
    fontSize: 14,
    tabSize: 2
  })

  editor.onDidChangeModelContent(() => {
    if (ignoreChanges || !canEdit.value) return
    files.value[activeTab.value] = editor.getValue()
    send({
      type: 'code-update',
      files: files.value,
      activeTab: activeTab.value
    })
  })

  connectWS()
})

onUnmounted(() => {
  editor?.dispose()
  ws?.close()
})

function getLang(name) {
  if (name.endsWith('.html') || name.endsWith('.vue')) return 'html'
  if (name.endsWith('.css')) return 'css'
  if (name.endsWith('.js')) return 'javascript'
  if (name.endsWith('.py')) return 'python'
  return 'plaintext'
}

function switchTab(name) {
  if (canEdit.value && editor) {
    files.value[activeTab.value] = editor.getValue()
  }
  activeTab.value = name
  ignoreChanges = true
  editor.setValue(files.value[name] || '')
  monaco.editor.setModelLanguage(editor.getModel(), getLang(name))
  ignoreChanges = false

  if (canEdit.value) {
    send({ type: 'code-update', files: files.value, activeTab: name })
  }
}

watch(canEdit, (val) => {
  editor?.updateOptions({ readOnly: !val })
})

// ===== WebSocket =====
function connectWS() {
  const protocol = location.protocol === 'https:' ? 'wss' : 'ws'
  const token = localStorage.getItem('token')
  const url = `${protocol}://${location.host}/ws/room/${roomId}?token=${token}`
  ws = new WebSocket(url)

  ws.onopen = () => console.log('WS connected')

  ws.onmessage = (e) => {
    const data = JSON.parse(e.data)

    if (data.type === 'code-update') {
      ignoreChanges = true
      files.value = data.files || files.value
      activeTab.value = data.activeTab || activeTab.value
      if (editor) {
        const newVal = files.value[activeTab.value] || ''
        if (editor.getValue() !== newVal) {
          editor.setValue(newVal)
        }
        monaco.editor.setModelLanguage(editor.getModel(), getLang(activeTab.value))
      }
      ignoreChanges = false
    }

    if (data.type === 'editor-changed') {
      currentEditorName.value = data.username
      canEdit.value = data.user_id === myUserId.value
    }

    if (data.type === 'participants') {
      participants.value = data.list || []
    }

    if (data.type === 'hand-raised') {
      if (!raisedHands.value.find(h => h.user_id === data.user_id)) {
        raisedHands.value.push({ user_id: data.user_id, username: data.username })
      }
    }
  }
}

function send(data) {
  if (ws?.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify(data))
  }
}

// ===== Действия =====
function raiseHand() {
  send({ type: 'raise-hand' })
}

function grantEdit(userId) {
  send({ type: 'grant-edit', user_id: userId })
  raisedHands.value = raisedHands.value.filter(h => h.user_id !== userId)
}

function revokeEdit() {
  send({ type: 'revoke-edit' })
}
</script>

<template>
  <div class="layout">
    <!-- Toolbar -->
    <div class="toolbar">
      <div class="tabs">
        <button
          v-for="(_, name) in files"
          :key="name"
          :class="['tab', { active: name === activeTab }]"
          @click="switchTab(name)"
        >
          {{ name }}
        </button>
      </div>
      <div class="info">
        <span v-if="currentEditorName">Редактирует: <b>{{ currentEditorName }}</b></span>
        <span v-else>Режим просмотра</span>
        <span v-if="canEdit" class="badge">Вы редактируете</span>
      </div>
    </div>

    <!-- Editor + Sidebar -->
    <div class="main">
      <div id="editor" class="editor"></div>

      <div class="sidebar">
        <h3>Участники</h3>
        <ul>
          <li v-for="p in participants" :key="p.user_id">
            {{ p.username }}
            <span v-if="p.user_id === myUserId"> (вы)</span>
          </li>
        </ul>

        <div v-if="raisedHands.length" class="hands">
          <h4>Подняли руку</h4>
          <div v-for="h in raisedHands" :key="h.user_id" class="hand-item">
            {{ h.username }}
            <button v-if="isHost" @click="grantEdit(h.user_id)">Дать права</button>
          </div>
        </div>

        <div class="actions">
          <button v-if="!canEdit && !isHost" @click="raiseHand" class="btn">
            Поднять руку
          </button>
          <button v-if="isHost" @click="revokeEdit" class="btn danger">
            Забрать права себе
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.layout {
  height: 100vh;
  display: flex;
  flex-direction: column;
  background: #1e1e1e;
  color: #ddd;
}
.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 12px;
  background: #252526;
  border-bottom: 1px solid #333;
}
.tabs { display: flex; gap: 4px; }
.tab {
  background: #2d2d2d;
  border: none;
  color: #aaa;
  padding: 6px 12px;
  border-radius: 4px 4px 0 0;
  cursor: pointer;
}
.tab.active {
  background: #1e1e1e;
  color: #fff;
  border-bottom: 2px solid #0e639c;
}
.info { font-size: 14px; }
.badge {
  margin-left: 12px;
  background: #0e639c;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 12px;
}
.main {
  flex: 1;
  display: flex;
  overflow: hidden;
}
.editor { flex: 1; }
.sidebar {
  width: 260px;
  background: #252526;
  border-left: 1px solid #333;
  padding: 16px;
  overflow-y: auto;
}
.sidebar ul { list-style: none; padding: 0; }
.sidebar li { padding: 6px 0; border-bottom: 1px solid #333; }
.hands { margin-top: 20px; }
.hand-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin: 8px 0;
}
.actions { margin-top: 24px; }
.btn {
  width: 100%;
  padding: 10px;
  border: none;
  border-radius: 6px;
  background: #0e639c;
  color: white;
  cursor: pointer;
  margin-bottom: 8px;
}
.btn.danger { background: #a1260d; }
</style>
