<script setup>
import { ref, onMounted, onUnmounted, nextTick, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import * as monaco from 'monaco-editor'
import { emmetHTML, emmetCSS, emmetJSX } from 'emmet-monaco-es'
import { getUser, isLoggedIn } from '@/auth'

const route = useRoute()
const router = useRouter()
const roomId = route.params.id
const user = getUser()
const myUserId = ref(user?.id)
const myUsername = ref(user?.username || 'Гость')
const isHost = ref(false)

const files = ref({
  'index.html': `<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <title>Моя страница</title>
  <link rel="stylesheet" href="style.css">
</head>
<body>
  <h1>Привет, мир!</h1>
  <script src="main.js"><\/script>
</body>
</html>`,
  'style.css': `body {
  background: #1e1e1e;
  color: #fff;
  font-family: sans-serif;
  padding: 20px;
}`,
  'main.js': `console.log("Код запущен!");
document.querySelector("h1").addEventListener("click", () => {
  alert("Привет!");
});`
})

const activeTab = ref('index.html')
const canEdit = ref(false)
const currentEditorName = ref(null)
const participants = ref([])
const raisedHands = ref([])

// Предпросмотр
const showPreview = ref(false)
const previewKey = ref(0)
const previewWidth = ref(400)
const isResizing = ref(false)

// Удалённые курсоры
const remoteSelections = ref({})
let decorationsCollection = null
let editor = null
let ws = null
let ignoreChanges = false

// ===== Утилиты =====
function getUserColor(userId) {
  const colors = ['#e06c75', '#98c379', '#e5c07b', '#61afef', '#c678dd', '#56b6c2', '#d19a66', '#56b6c2']
  let hash = 0
  const str = String(userId)
  for (let i = 0; i < str.length; i++) {
    hash = str.charCodeAt(i) + ((hash << 5) - hash)
  }
  return colors[Math.abs(hash) % colors.length]
}

// ← НОВОЕ: динамические стили для разных цветов курсоров
function ensureRemoteStyle(userId, color) {
  const id = `remote-style-${userId}`
  if (document.getElementById(id)) return
  const style = document.createElement('style')
  style.id = id
  style.textContent = `
    .remote-selection-${userId} {
      background-color: ${color}40 !important;
    }
    .remote-selection-${userId}-inline {
      border-left: 2px solid ${color} !important;
      border-right: 2px solid ${color} !important;
    }
  `
  document.head.appendChild(style)
}

function generatePreviewContent() {
  let html = files.value['index.html'] || ''
  const css = files.value['style.css'] || ''
  const js = files.value['main.js'] || ''

  html = html.replace(
    /<link\s+rel=["']stylesheet["']\s+href=["']style\.css["']\s*\/?>/gi,
    `<style>\n${css}\n</style>`
  )
  html = html.replace(
    /<script\s+src=["']main\.js["']\s*><\/script>/gi,
    `<script>\n${js}\n<\/script>`
  )
  return html
}

// ===== Инициализация =====
onMounted(async () => {
  if (!isLoggedIn()) {
    router.push('/login')
    return
  }

  await nextTick()

  try {
      emmetHTML(monaco, ['html'])
      emmetCSS(monaco, ['css'])
      emmetJSX(monaco, ['javascript'])
    } catch (e) {
      console.warn('Emmet init failed:', e)
  }

  try {
      // JS / TS
      if (monaco.languages?.typescript?.javascriptDefaults) {
        monaco.languages.typescript.javascriptDefaults.setCompilerOptions({
          target: monaco.languages.typescript.ScriptTarget.ESNext,
          allowNonTsExtensions: true,
          moduleResolution: monaco.languages.typescript.ModuleResolutionKind.NodeJs,
          module: monaco.languages.typescript.ModuleKind.ESNext,
          noEmit: true,
          esModuleInterop: true,
          allowJs: true,
          checkJs: false,
        })
        monaco.languages.typescript.javascriptDefaults.setDiagnosticsOptions({
          noSemanticValidation: true,   // меньше шума в простом JS
          noSyntaxValidation: false,
        })
      }

      // HTML
      if (monaco.languages?.html?.htmlDefaults) {
        monaco.languages.html.htmlDefaults.setOptions({
          format: { tabSize: 2, insertSpaces: true },
          suggest: { html5: true },
        })
      }

      // CSS
      if (monaco.languages?.css?.cssDefaults) {
        monaco.languages.css.cssDefaults.setOptions({
          validate: true,
        })
      }
    } catch (e) {
      console.warn('Language services init failed:', e)
    }

    editor = monaco.editor.create(document.getElementById('editor'), {
        value: files.value[activeTab.value],
        language: getLang(activeTab.value),
        theme: 'vs-dark',
        readOnly: true,
        automaticLayout: true,
        minimap: { enabled: false },
        fontSize: 14,
        tabSize: 2,
        insertSpaces: true,

        quickSuggestions: {
          other: true,
          comments: false,
          strings: true,
        },
        suggestOnTriggerCharacters: true,
        acceptSuggestionOnEnter: 'on',
        tabCompletion: 'on',
        wordBasedSuggestions: 'currentDocument',
        snippetSuggestions: 'top',
        suggest: {
          preview: true,
          showInlineDetails: true,
          snippetsPreventQuickSuggestions: false,
        },
        parameterHints: { enabled: true },
        autoClosingBrackets: 'always',
        autoClosingQuotes: 'always',
        formatOnPaste: true,
        formatOnType: false,
      })

  decorationsCollection = editor.createDecorationsCollection()

  // Изменения кода
  editor.onDidChangeModelContent(() => {
    if (ignoreChanges || !canEdit.value) return
    files.value[activeTab.value] = editor.getValue()
    send({
      type: 'code-update',
      files: files.value,
      activeTab: activeTab.value
    })
  })

  // Курсор / выделение
  editor.onDidChangeCursorSelection((e) => {
    if (!canEdit.value || !ws || ws.readyState !== WebSocket.OPEN) return
    const sel = e.selection
    send({
      type: 'cursor-update',
      selection: {
        startLineNumber: sel.startLineNumber,
        startColumn: sel.startColumn,
        endLineNumber: sel.endLineNumber,
        endColumn: sel.endColumn
      },
      color: getUserColor(myUserId.value)
    })
  })

  connectWS()
})

onUnmounted(() => {
  // ← НОВОЕ: очищаем свой курсор при уходе
  send({ type: 'cursor-clear' })
  editor?.dispose()
  ws?.close()
  document.removeEventListener('mousemove', onResize)
  document.removeEventListener('mouseup', stopResize)
})

function getLang(name) {
  if (name.endsWith('.html') || name.endsWith('.vue')) return 'html'
  if (name.endsWith('.css')) return 'css'
  if (name.endsWith('.js')) return 'javascript'
  if (name.endsWith('.py')) return 'python'
  return 'plaintext'
}

function switchTab(name) {
  if (!editor) return

  if (canEdit.value && editor) {
    files.value[activeTab.value] = editor.getValue()
  }

  // ← НОВОЕ: при смене вкладки очищаем свой курсор у других
  if (canEdit.value) {
    send({ type: 'cursor-clear' })
  }

  activeTab.value = name
  ignoreChanges = true

  const lang = getLang(name)
    const oldModel = editor.getModel()
    const newModel = monaco.editor.createModel(
      files.value[name] || '',
      lang
    )
    editor.setModel(newModel)
  oldModel?.dispose()

  ignoreChanges = false

  if (canEdit.value) {
    send({ type: 'code-update', files: files.value, activeTab: name })

    // ← НОВОЕ: сразу отправляем новый курсор на новой вкладке
    nextTick(() => {
      const sel = editor.getSelection()
      if (sel) {
        send({
          type: 'cursor-update',
          selection: {
            startLineNumber: sel.startLineNumber,
            startColumn: sel.startColumn,
            endLineNumber: sel.endLineNumber,
            endColumn: sel.endColumn
          },
          color: getUserColor(myUserId.value)
        })
      }
    })
  }
}

// ← ИЗМЕНЕНО: при получении/потере прав сразу шлём курсор или очищаем
watch(canEdit, (val) => {
  editor?.updateOptions({ readOnly: !val })

  if (val && editor) {
    // Получили права → сразу сообщаем свой курсор
    nextTick(() => {
      const sel = editor.getSelection()
      if (sel) {
        send({
          type: 'cursor-update',
          selection: {
            startLineNumber: sel.startLineNumber,
            startColumn: sel.startColumn,
            endLineNumber: sel.endLineNumber,
            endColumn: sel.endColumn
          },
          color: getUserColor(myUserId.value)
        })
      }
    })
  } else {
    // Потеряли права → очищаем курсор у всех
    send({ type: 'cursor-clear' })
  }
})

function connectWS() {
  const protocol = location.protocol === 'https:' ? 'wss' : 'ws'
  const token = localStorage.getItem('token')
  const url = `${protocol}://${location.host}/ws/room/${roomId}?token=${token}`

  ws = new WebSocket(url)

  ws.onopen = () => console.log('WS подключён')

  ws.onmessage = (e) => {
    const data = JSON.parse(e.data)

    // ========== ← НОВОЕ: полное состояние комнаты при подключении ==========
    if (data.type === 'room-state') {
      ignoreChanges = true

      files.value = data.files || files.value
      activeTab.value = data.activeTab || activeTab.value
      showPreview.value = !!data.showPreview
      if (data.showPreview) previewKey.value++

      // Кто сейчас редактирует
      if (data.currentEditor) {
        currentEditorName.value = data.currentEditor.username
        canEdit.value = data.currentEditor.user_id === myUserId.value
      } else {
        currentEditorName.value = null
        canEdit.value = false
      }

      // Хост
      isHost.value = data.hostId === myUserId.value || data.isHost === true

      // Участники
      if (data.participants) {
        participants.value = data.participants
      }

      // Поднятые руки
      if (data.raisedHands) {
        raisedHands.value = data.raisedHands
      }

      // Текущие курсоры всех пользователей
      if (data.cursors) {
        remoteSelections.value = {}
        for (const [uid, cursor] of Object.entries(data.cursors)) {
          if (uid === String(myUserId.value)) continue
          remoteSelections.value[uid] = {
            username: cursor.username,
            selection: cursor.selection,
            color: cursor.color || getUserColor(uid)
          }
          ensureRemoteStyle(uid, remoteSelections.value[uid].color)
        }
        updateRemoteDecorations()
      }

      if (editor) {
        const newVal = files.value[activeTab.value] || ''
        const lang = getLang(activeTab.value)
        const model = editor.getModel()

        if (model) {
          // Меняем язык, если нужно
          if (model.getLanguageId() !== lang) {
            monaco.editor.setModelLanguage(model, lang)
          }
          // Меняем текст только если реально отличается
          if (model.getValue() !== newVal) {
            model.setValue(newVal)
          }
        }
      }

      ignoreChanges = false
      return
    }

    // Обычное обновление кода
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

    // ← НОВОЕ: сервер может присылать isHost
    if (data.type === 'host-info') {
      isHost.value = data.hostId === myUserId.value
    }

    if (data.type === 'hand-raised') {
      if (!raisedHands.value.find(h => h.user_id === data.user_id)) {
        raisedHands.value.push({ user_id: data.user_id, username: data.username })
      }
    }

    // ← ИЗМЕНЕНО: предпросмотр синхронизируется у всех
    if (data.type === 'preview-toggle') {
      showPreview.value = data.show
      if (data.show) previewKey.value++
    }

    if (data.type === 'preview-refresh') {
      previewKey.value++
    }

    // Курсор другого пользователя
    if (data.type === 'cursor-update' && data.user_id !== myUserId.value) {
      const color = data.color || getUserColor(data.user_id)
      remoteSelections.value[data.user_id] = {
        username: data.username,
        selection: data.selection,
        color
      }
      ensureRemoteStyle(data.user_id, color)
      updateRemoteDecorations()
    }

    // Очистка курсора
    if (data.type === 'cursor-clear' && data.user_id !== myUserId.value) {
      delete remoteSelections.value[data.user_id]
      updateRemoteDecorations()
    }

    // ← НОВОЕ: пользователь вышел — чистим его курсор и руку
    if (data.type === 'user-left') {
      delete remoteSelections.value[data.user_id]
      raisedHands.value = raisedHands.value.filter(h => h.user_id !== data.user_id)
      updateRemoteDecorations()
    }

    if (data.type === 'error') {
      console.error('Ошибка от сервера:', data.message)
    }
  }

  ws.onclose = () => {
    console.log('WS отключён')
    remoteSelections.value = {}
    updateRemoteDecorations()
  }
}

function send(data) {
  if (ws?.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify(data))
  }
}

// ===== Декорации курсоров =====
function updateRemoteDecorations() {
  if (!editor || !decorationsCollection) return

  const newDecorations = []

  for (const [uid, info] of Object.entries(remoteSelections.value)) {
    if (!info.selection) continue

    newDecorations.push({
      range: new monaco.Range(
        info.selection.startLineNumber,
        info.selection.startColumn,
        info.selection.endLineNumber,
        info.selection.endColumn
      ),
      options: {
        className: `remote-selection-${uid}`,
        inlineClassName: `remote-selection-${uid}-inline`,
        hoverMessage: { value: `**${info.username}**` },
        stickiness: monaco.editor.TrackedRangeStickiness.NeverGrowsWhenTypingAtEdges
      }
    })
  }

  decorationsCollection.set(newDecorations)
}

// ===== Resizer =====
function startResize(e) {
  isResizing.value = true
  document.body.style.cursor = 'col-resize'
  document.body.style.userSelect = 'none'
  document.addEventListener('mousemove', onResize)
  document.addEventListener('mouseup', stopResize)
  e.preventDefault()
}

function onResize(e) {
  if (!isResizing.value) return
  const newWidth = window.innerWidth - e.clientX - 260
  if (newWidth >= 250 && newWidth <= window.innerWidth - 500) {
    previewWidth.value = newWidth
  }
}

function stopResize() {
  isResizing.value = false
  document.body.style.cursor = ''
  document.body.style.userSelect = ''
  document.removeEventListener('mousemove', onResize)
  document.removeEventListener('mouseup', stopResize)
  if (editor) editor.layout()
}

// ===== Действия =====
function togglePreview() {
  showPreview.value = !showPreview.value
  send({ type: 'preview-toggle', show: showPreview.value })
  if (showPreview.value) previewKey.value++
}

function refreshPreview() {
  previewKey.value++
  send({ type: 'preview-refresh' })
}

function raiseHand() {
  send({ type: 'raise-hand', user_id: myUserId.value, username: myUsername.value })
}

function grantEdit(userId) {
  send({ type: 'grant-edit', user_id: userId })
  raisedHands.value = raisedHands.value.filter(h => h.user_id !== userId)
}

function revokeEdit() {
  send({ type: 'revoke-edit', user_id: myUserId.value })
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

      <div class="actions-toolbar">
        <button v-if="canEdit" class="btn-preview" @click="togglePreview">
          {{ showPreview ? 'Скрыть предпросмотр' : '👁 Запустить код' }}
        </button>
        <button v-if="showPreview" class="btn-refresh" @click="refreshPreview" title="Обновить предпросмотр">
          🔄 Обновить
        </button>

        <div class="info">
          <span v-if="currentEditorName">Редактирует: <b>{{ currentEditorName }}</b></span>
          <span v-else>Режим просмотра</span>
          <span v-if="canEdit" class="badge">Вы редактируете</span>
        </div>
      </div>
    </div>

    <!-- Main -->
    <div class="main">
      <div id="editor" class="editor"></div>

      <div v-if="showPreview" class="resizer" @mousedown="startResize"></div>

      <div v-if="showPreview" class="preview-container" :style="{ width: previewWidth + 'px' }">
        <div class="preview-header">
          <span>Результат</span>
          <button class="btn-close-preview" @click="togglePreview">×</button>
        </div>
        <iframe
          :key="previewKey"
          :srcdoc="generatePreviewContent()"
          sandbox="allow-scripts allow-modals allow-forms allow-same-origin"
          class="preview-frame"
          title="Code Preview"
        ></iframe>
      </div>

      <!-- Sidebar -->
      <div class="sidebar">
        <h3>Участники ({{ participants.length }})</h3>
        <ul>
          <li v-for="p in participants" :key="p.user_id">
            {{ p.username }}
            <span v-if="p.user_id === myUserId"> (вы)</span>
            <span v-if="p.isHost" class="host-badge">хост</span>
          </li>
        </ul>

        <div v-if="raisedHands.length" class="hands">
          <h4>Подняли руку ✋</h4>
          <div v-for="h in raisedHands" :key="h.user_id" class="hand-item">
            <span>{{ h.username }}</span>
            <button
              v-if="isHost"
              @click="grantEdit(h.user_id)"
              class="btn btn-sm btn-success"
            >
              Дать права
            </button>
          </div>
        </div>

        <div class="actions">
          <button v-if="!canEdit" @click="raiseHand" class="btn">Поднять руку</button>
          <button v-if="canEdit" @click="revokeEdit" class="btn danger">Завершить редактирование</button>
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
  overflow: hidden;
}

.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 12px;
  background: #252526;
  border-bottom: 1px solid #333;
  flex-shrink: 0;
}

.tabs { display: flex; gap: 4px; }

.tab {
  background: #2d2d2d;
  border: none;
  color: #aaa;
  padding: 6px 12px;
  border-radius: 4px 4px 0 0;
  cursor: pointer;
  transition: background 0.2s;
}
.tab:hover { background: #3e3e42; }
.tab.active {
  background: #1e1e1e;
  color: #fff;
  border-bottom: 2px solid #0e639c;
}

.actions-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
}

.btn-preview {
  background: #28a745;
  color: white;
  border: none;
  padding: 6px 16px;
  border-radius: 4px;
  cursor: pointer;
  font-weight: 600;
  transition: background 0.2s;
}
.btn-preview:hover { background: #218838; }

.btn-refresh {
  background: #17a2b8;
  color: white;
  border: none;
  padding: 6px 12px;
  border-radius: 4px;
  cursor: pointer;
  font-size: 14px;
  transition: background 0.2s;
}
.btn-refresh:hover { background: #138496; }

.info { font-size: 14px; display: flex; align-items: center; gap: 12px; }

.badge {
  background: #0e639c;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 12px;
}

.host-badge {
  background: #e5c07b;
  color: #1e1e1e;
  font-size: 11px;
  padding: 1px 6px;
  border-radius: 3px;
  margin-left: 6px;
}

.main {
  flex: 1;
  display: flex;
  overflow: hidden;
  position: relative;
}

.editor {
  flex: 1;
  min-width: 300px;
}

.resizer {
  width: 8px;
  background: #1e1e1e;
  border-left: 1px solid #333;
  border-right: 1px solid #333;
  cursor: col-resize;
  transition: background 0.2s;
  flex-shrink: 0;
  z-index: 10;
}
.resizer:hover, .resizer:active {
  background: #0e639c;
}

.preview-container {
  background: #ffffff;
  display: flex;
  flex-direction: column;
  border-right: 1px solid #333;
  flex-shrink: 0;
}

.preview-header {
  background: #f0f0f0;
  color: #333;
  padding: 8px 12px;
  font-size: 13px;
  font-weight: bold;
  border-bottom: 1px solid #ccc;
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-shrink: 0;
}

.btn-close-preview {
  background: #dc3545;
  color: white;
  border: none;
  width: 24px;
  height: 24px;
  border-radius: 4px;
  cursor: pointer;
  font-size: 16px;
  line-height: 1;
  display: flex;
  align-items: center;
  justify-content: center;
}
.btn-close-preview:hover { background: #c82333; }

.preview-frame {
  width: 100%;
  height: 100%;
  border: none;
  background: white;
}

.sidebar {
  width: 260px;
  min-width: 260px;
  background: #252526;
  border-left: 1px solid #333;
  padding: 16px;
  overflow-y: auto;
  flex-shrink: 0;
}

.sidebar ul { list-style: none; padding: 0; margin-top: 12px; }
.sidebar li { padding: 6px 0; border-bottom: 1px solid #333; }

.hands { margin-top: 20px; }
.hand-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin: 8px 0;
  font-size: 14px;
}

.actions { margin-top: 24px; display: flex; flex-direction: column; gap: 8px; }

.btn {
  width: 100%;
  padding: 10px;
  border: none;
  border-radius: 6px;
  background: #0e639c;
  color: white;
  cursor: pointer;
  font-weight: 500;
}
.btn:hover { background: #1177bb; }
.btn.danger { background: #a1260d; }
.btn.danger:hover { background: #c7361a; }
.btn.btn-sm { padding: 4px 10px; font-size: 12px; width: auto; }
.btn-success { background: #28a745; }
.btn-success:hover { background: #218838; }
</style>
