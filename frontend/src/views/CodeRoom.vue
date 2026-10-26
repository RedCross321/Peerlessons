<script setup>
import { ref, computed, onMounted, onUnmounted, nextTick, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import '@/monaco-workers'
import * as monaco from 'monaco-editor'
import { emmetHTML, emmetCSS, emmetJSX } from 'emmet-monaco-es'
import { getUser, isLoggedIn, ensureValidAccessToken } from '@/auth'

const route = useRoute()
const router = useRouter()
const roomId = route.params.id
const user = getUser()
const myUserId = ref(user?.id)
const myUsername = ref(user?.username || 'Гость')
const isHost = ref(false)
const hostId = ref(null)
const shortRoomId = computed(() => String(roomId || '').slice(0, 8))

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
const currentEditorId = ref(null)
const participants = ref([])
const raisedHands = ref([])

const hasRaisedHand = computed(() =>
  raisedHands.value.some(h => h.user_id === myUserId.value)
)

// Предпросмотр
const showPreview = ref(false)
const previewKey = ref(0)
const previewWidth = ref(400)
const isResizing = ref(false)

// Удалённые курсоры
const remoteSelections = ref({})
const remoteCaretWidgets = new Map()
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

// Сериализует выделение и активную позицию курсора для рассылки другим участникам.
function toRemoteSelection(sel) {
  return {
    startLineNumber: sel.startLineNumber,
    startColumn: sel.startColumn,
    endLineNumber: sel.endLineNumber,
    endColumn: sel.endColumn,
    // Активная граница выделения — именно там рисуется каретка.
    cursorLineNumber: sel.positionLineNumber,
    cursorColumn: sel.positionColumn
  }
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

    monaco.editor.defineTheme('peerless-dark', {
      base: 'vs-dark',
      inherit: true,
      rules: [
        { token: 'comment', foreground: '6d7789', fontStyle: 'italic' },
        { token: 'keyword', foreground: 'ff9163' },
        { token: 'string', foreground: 'a9c9a4' },
        { token: 'number', foreground: 'e8c07d' },
        { token: 'tag', foreground: 'ff7a45' },
        { token: 'attribute.name', foreground: 'cdd4e0' },
        { token: 'attribute.value', foreground: 'a9c9a4' }
      ],
      colors: {
        'editor.background': '#0f1219',
        'editor.foreground': '#e9edf4',
        'editorLineNumber.foreground': '#39404f',
        'editorLineNumber.activeForeground': '#9aa4b6',
        'editor.lineHighlightBackground': '#151a24',
        'editor.selectionBackground': '#ff7a4538',
        'editor.inactiveSelectionBackground': '#ff7a451c',
        'editorCursor.foreground': '#ff7a45',
        'editorIndentGuide.background1': '#1c2230',
        'editorIndentGuide.activeBackground1': '#2c3546',
        'editorWidget.background': '#121620',
        'editorWidget.border': '#222a39',
        'editorSuggestWidget.background': '#121620',
        'editorSuggestWidget.border': '#222a39',
        'editorSuggestWidget.selectedBackground': '#1d2432',
        'scrollbarSlider.background': '#2a324280',
        'scrollbarSlider.hoverBackground': '#39435a',
        'scrollbarSlider.activeBackground': '#4a5570'
      }
    })

    editor = monaco.editor.create(document.getElementById('editor'), {
        value: files.value[activeTab.value],
        language: getLang(activeTab.value),
        theme: 'peerless-dark',
        readOnly: true,
        automaticLayout: true,
        minimap: { enabled: false },
        fontSize: 14,
        lineHeight: 22,
        fontFamily: "'JetBrains Mono', 'Fira Code', ui-monospace, SFMono-Regular, Menlo, monospace",
        padding: { top: 14, bottom: 14 },
        cursorBlinking: 'smooth',
        smoothScrolling: true,
        renderLineHighlight: 'line',
        scrollbar: { verticalScrollbarSize: 10, horizontalScrollbarSize: 10 },
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

  // Пересчитываем метрики после загрузки веб-шрифта: иначе Monaco
  // может остаться на системном фолбэке.
  document.fonts?.ready.then(() => monaco.editor.remeasureFonts())

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
      selection: toRemoteSelection(sel),
      color: getUserColor(myUserId.value)
    })
  })

  const tokenReady = await ensureValidAccessToken()
  if (!tokenReady) return

  connectWS()
})

onUnmounted(() => {
  // ← НОВОЕ: очищаем свой курсор при уходе
  send({ type: 'cursor-clear' })
  for (const uid of [...remoteCaretWidgets.keys()]) {
    removeRemoteCaret(uid)
  }
  editor?.dispose()
  editor = null
  decorationsCollection = null
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

function fileKind(name) {
  if (name.endsWith('.html') || name.endsWith('.vue')) return 'html'
  if (name.endsWith('.css')) return 'css'
  if (name.endsWith('.js')) return 'js'
  return 'other'
}

function initials(name) {
  const parts = String(name || '').trim().split(/[\s_]+/).filter(Boolean)
  if (!parts.length) return '?'
  return parts.slice(0, 2).map(part => part[0].toUpperCase()).join('')
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
          selection: toRemoteSelection(sel),
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
          selection: toRemoteSelection(sel),
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
      currentEditorId.value = data.currentEditor?.user_id ?? null
      if (data.currentEditor) {
        currentEditorName.value = data.currentEditor.username
        canEdit.value = data.currentEditor.user_id === myUserId.value
      } else {
        currentEditorName.value = null
        canEdit.value = false
      }

      // Хост
      isHost.value = data.hostId === myUserId.value || data.isHost === true
      hostId.value = data.hostId ?? null

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
      currentEditorId.value = data.user_id
      canEdit.value = data.user_id === myUserId.value
    }

    if (data.type === 'participants') {
      participants.value = data.list || []
    }

    // ← НОВОЕ: сервер может присылать isHost
    if (data.type === 'host-info') {
      isHost.value = data.hostId === myUserId.value
      hostId.value = data.hostId ?? null
    }

    if (data.type === 'hand-raised') {
      if (!raisedHands.value.find(h => h.user_id === data.user_id)) {
        raisedHands.value.push({ user_id: data.user_id, username: data.username })
      }
    }

    if (data.type === 'hand-lowered') {
      raisedHands.value = raisedHands.value.filter(h => h.user_id !== data.user_id)
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
function getRemoteCursorPosition(selection) {
  return {
    lineNumber: selection.cursorLineNumber ?? selection.endLineNumber,
    column: selection.cursorColumn ?? selection.endColumn
  }
}

function ensureRemoteCaret(uid, username, color, position) {
  let entry = remoteCaretWidgets.get(uid)

  if (!entry) {
    const node = document.createElement('div')
    node.className = 'remote-caret'
    node.style.width = '2px'
    node.style.pointerEvents = 'none'
    node.style.zIndex = '10'
    node.style.borderRadius = '1px'

    const widget = {
      getId: () => `remote-caret-${uid}`,
      getDomNode: () => node,
      getPosition: () => {
        if (!entry.position) return null
        return {
          position: entry.position,
          preference: [monaco.editor.ContentWidgetPositionPreference.EXACT]
        }
      }
    }

    entry = { node, widget, position: null }
    remoteCaretWidgets.set(uid, entry)
    editor.addContentWidget(widget)
  }

  const lineHeight =
    editor.getOption(monaco.editor.EditorOption.lineHeight) || 18

  entry.position = position
  entry.node.style.height = `${lineHeight}px`
  entry.node.style.background = color
  entry.node.title = `${username}`

  editor.layoutContentWidget(entry.widget)
}

function removeRemoteCaret(uid) {
  const entry = remoteCaretWidgets.get(uid)
  if (!entry) return
  if (editor) editor.removeContentWidget(entry.widget)
  remoteCaretWidgets.delete(uid)
}

function updateRemoteDecorations() {
  if (!editor || !decorationsCollection) return

  const newDecorations = []
  const withCursor = new Set()

  for (const [uid, info] of Object.entries(remoteSelections.value)) {
    if (!info.selection) continue

    const sel = info.selection
    withCursor.add(uid)

    // Подсветка нужна только для непустого выделения.
    if (
      sel.startLineNumber !== sel.endLineNumber ||
      sel.startColumn !== sel.endColumn
    ) {
      newDecorations.push({
        range: new monaco.Range(
          sel.startLineNumber,
          sel.startColumn,
          sel.endLineNumber,
          sel.endColumn
        ),
        options: {
          className: `remote-selection-${uid}`,
          inlineClassName: `remote-selection-${uid}-inline`,
          hoverMessage: { value: `**${info.username}**` },
          stickiness: monaco.editor.TrackedRangeStickiness.NeverGrowsWhenTypingAtEdges
        }
      })
    }

    // Каретка видна всегда, даже когда выделения нет.
    ensureRemoteCaret(
      uid,
      info.username,
      info.color,
      getRemoteCursorPosition(sel)
    )
  }

  // Убираем каретки пользователей, чей курсор больше не актуален.
  for (const uid of [...remoteCaretWidgets.keys()]) {
    if (!withCursor.has(uid)) removeRemoteCaret(uid)
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
  const newWidth = window.innerWidth - e.clientX - 300
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

function lowerHand() {
  send({ type: 'lower-hand' })
  raisedHands.value = raisedHands.value.filter(h => h.user_id !== myUserId.value)
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
  <div class="room">
    <header class="room-header">
      <div class="room-identity">
        <RouterLink to="/" class="brand brand--compact">
          <span class="brand-mark">/</span>
          <span class="brand-name">Peerlessons</span>
        </RouterLink>
        <span class="room-sep"></span>
        <div class="room-meta">
          <span class="room-title">Комната</span>
          <span class="room-id">{{ shortRoomId }}</span>
        </div>
      </div>

      <div class="room-status">
        <span class="status-dot" :class="{ edit: canEdit }"></span>
        <span v-if="currentEditorName" class="status-text">
          Редактирует <b>{{ currentEditorName }}</b>
        </span>
        <span v-else class="status-text">Режим просмотра</span>
        <span v-if="canEdit" class="badge badge-accent">Вы редактируете</span>
      </div>
    </header>

    <div class="workspace">
      <section class="editor-panel">
        <div class="editor-toolbar">
          <div class="tabs">
            <button
              v-for="(_, name) in files"
              :key="name"
              :class="['tab', { active: name === activeTab }]"
              @click="switchTab(name)"
            >
              <span class="tab-dot" :class="fileKind(name)"></span>
              {{ name }}
            </button>
          </div>

          <div class="toolbar-actions">
            <button v-if="canEdit" class="btn btn-secondary btn-sm" @click="togglePreview">
              {{ showPreview ? 'Скрыть результат' : 'Запустить код' }}
            </button>
            <button
              v-if="showPreview"
              class="btn btn-ghost btn-sm"
              @click="refreshPreview"
              title="Обновить предпросмотр"
            >
              Обновить
            </button>
          </div>
        </div>

        <div class="editor-area">
          <div id="editor" class="editor"></div>

          <div v-if="showPreview" class="resizer" @mousedown="startResize"></div>

          <div v-if="showPreview" class="preview-container" :style="{ width: previewWidth + 'px' }">
            <div class="preview-header">
              <span class="preview-title"><span class="preview-dot"></span> Результат</span>
              <button v-if="canEdit" class="icon-btn" @click="togglePreview" title="Закрыть">×</button>
            </div>
            <iframe
              :key="previewKey"
              :srcdoc="generatePreviewContent()"
              sandbox="allow-scripts allow-modals allow-forms allow-same-origin"
              class="preview-frame"
              title="Code Preview"
            ></iframe>
          </div>
        </div>
      </section>

      <aside class="sidebar">
        <section class="side-card">
          <h3 class="side-title">
            Участники
            <span class="count">{{ participants.length }}</span>
          </h3>
          <ul class="participant-list">
            <li v-for="p in participants" :key="p.user_id" class="participant">
              <span
                class="avatar"
                :style="{ color: getUserColor(p.user_id), background: getUserColor(p.user_id) + '1f' }"
              >
                {{ initials(p.username) }}
              </span>
              <span class="participant-name">
                {{ p.username }}<span v-if="p.user_id === myUserId" class="you">вы</span>
              </span>
              <span
                v-if="p.user_id === currentEditorId"
                class="editing-dot"
                title="Редактирует сейчас"
              ></span>
              <span v-if="p.user_id === hostId" class="tag">хост</span>
            </li>
          </ul>
        </section>

        <section v-if="raisedHands.length" class="side-card">
          <h3 class="side-title">
            Подняли руку
            <span class="count">{{ raisedHands.length }}</span>
          </h3>
          <div class="hand-list">
            <div v-for="h in raisedHands" :key="h.user_id" class="hand-item">
              <span class="hand-name">{{ h.username }}</span>
              <button
                v-if="isHost"
                @click="grantEdit(h.user_id)"
                class="btn btn-primary btn-xs"
              >
                Дать права
              </button>
            </div>
          </div>
        </section>

        <div class="side-actions">
          <button v-if="isHost && !canEdit" @click="revokeEdit" class="btn btn-primary">Вернуть права</button>
          <button v-if="!isHost && hasRaisedHand" @click="lowerHand" class="btn btn-secondary">Опустить руку</button>
          <button v-if="!isHost && !hasRaisedHand && !canEdit" @click="raiseHand" class="btn btn-secondary">Поднять руку</button>
          <button v-if="!isHost && canEdit" @click="revokeEdit" class="btn btn-danger">Завершить редактирование</button>
        </div>
      </aside>
    </div>
  </div>
</template>

<style scoped>
.room {
  height: 100vh;
  display: flex;
  flex-direction: column;
  background: var(--bg);
  color: var(--text);
  overflow: hidden;
}

.room-header {
  height: 64px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 0 20px;
  background: var(--bg-raised);
  border-bottom: 1px solid var(--border);
}

.room-identity {
  display: flex;
  align-items: center;
  gap: 14px;
  min-width: 0;
}

.room-sep {
  width: 1px;
  height: 24px;
  background: var(--border);
}

.room-meta {
  display: flex;
  flex-direction: column;
  line-height: 1.15;
}

.room-title {
  color: var(--text-muted);
  font-size: 12px;
  font-weight: 600;
}

.room-id {
  color: var(--text-dim);
  font-family: var(--font-mono);
  font-size: 12px;
}

.room-status {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.status-dot {
  width: 7px;
  height: 7px;
  flex: none;
  border-radius: 50%;
  background: var(--text-dim);
}

.status-dot.edit {
  background: var(--accent);
  box-shadow: 0 0 0 4px var(--accent-soft);
}

.status-text {
  overflow: hidden;
  color: var(--text-muted);
  font-size: 13px;
  white-space: nowrap;
  text-overflow: ellipsis;
}

.status-text b {
  color: var(--text);
  font-weight: 600;
}

.workspace {
  flex: 1;
  display: flex;
  min-height: 0;
}

.editor-panel {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  background: #0f1219;
}

.editor-toolbar {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 14px;
  background: var(--bg-raised);
  border-bottom: 1px solid var(--border);
}

.tabs {
  display: flex;
  flex: 1;
  gap: 6px;
  min-width: 0;
  overflow-x: auto;
  scrollbar-width: none;
}

.tabs::-webkit-scrollbar {
  display: none;
}

.tab {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 7px 11px;
  border: 1px solid transparent;
  border-radius: 7px;
  background: transparent;
  color: var(--text-muted);
  font-size: 13px;
  font-weight: 500;
  white-space: nowrap;
  cursor: pointer;
  transition: background-color 0.16s ease, border-color 0.16s ease, color 0.16s ease;
}

.tab:hover {
  background: var(--surface);
  color: var(--text);
}

.tab.active {
  background: var(--surface-2);
  border-color: var(--border-strong);
  color: var(--text);
}

.tab-dot {
  width: 7px;
  height: 7px;
  flex: none;
  border-radius: 50%;
  background: var(--text-dim);
}

.tab-dot.html {
  background: #e8734a;
}

.tab-dot.css {
  background: #5b8def;
}

.tab-dot.js {
  background: #e5c07b;
}

.toolbar-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.editor-area {
  flex: 1;
  display: flex;
  min-height: 0;
  position: relative;
}

.editor {
  flex: 1;
  min-width: 0;
}

.resizer {
  width: 6px;
  flex-shrink: 0;
  z-index: 10;
  background: var(--bg-raised);
  border-left: 1px solid var(--border);
  border-right: 1px solid var(--border);
  cursor: col-resize;
  transition: background-color 0.16s ease;
}

.resizer:hover,
.resizer:active {
  background: var(--accent);
}

.preview-container {
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  min-width: 250px;
  background: #fff;
  border-left: 1px solid var(--border);
}

.preview-header {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  background: #f4f5f7;
  border-bottom: 1px solid #dfe2e8;
  color: #3a4150;
}

.preview-title {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-size: 12.5px;
  font-weight: 600;
}

.preview-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #4caf72;
}

.icon-btn {
  width: 26px;
  height: 26px;
  display: grid;
  place-items: center;
  padding: 0;
  border: 1px solid #d7dbe3;
  border-radius: 7px;
  background: transparent;
  color: #4a5160;
  font-size: 17px;
  line-height: 1;
  cursor: pointer;
  transition: background-color 0.16s ease, color 0.16s ease, border-color 0.16s ease;
}

.icon-btn:hover {
  background: #e7e9ee;
  border-color: #c3c8d2;
  color: #191c23;
}

.preview-frame {
  width: 100%;
  height: 100%;
  border: 0;
  background: #fff;
}

.sidebar {
  width: 288px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 16px;
  overflow-y: auto;
  background: var(--bg-raised);
  border-left: 1px solid var(--border);
}

.side-card {
  padding: 14px;
  border: 1px solid var(--border);
  border-radius: 12px;
  background: var(--surface);
}

.side-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
  color: var(--text-dim);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.count {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 20px;
  height: 20px;
  padding: 0 6px;
  border: 1px solid var(--border);
  border-radius: 999px;
  background: var(--surface-2);
  color: var(--text-muted);
  font-size: 11px;
  letter-spacing: 0;
}

.participant-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.participant {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 6px;
  border-radius: 8px;
}

.participant:hover {
  background: var(--surface-2);
}

.avatar {
  width: 30px;
  height: 30px;
  flex: none;
  display: grid;
  place-items: center;
  border-radius: 9px;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.02em;
}

.participant-name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  color: var(--text);
  font-size: 13.5px;
  white-space: nowrap;
  text-overflow: ellipsis;
}

.editing-dot {
  width: 6px;
  height: 6px;
  flex: none;
  border-radius: 50%;
  background: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-soft);
}

.you {
  margin-left: 6px;
  color: var(--text-dim);
  font-size: 11px;
}

.tag {
  padding: 2px 6px;
  border: 1px solid rgba(255, 122, 69, 0.3);
  border-radius: 5px;
  background: var(--accent-soft);
  color: var(--accent);
  font-size: 10.5px;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

.hand-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.hand-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  font-size: 13.5px;
}

.hand-name {
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}

.side-actions {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.side-actions .btn {
  width: 100%;
}

@media (max-width: 900px) {
  .room {
    height: auto;
    min-height: 100vh;
    overflow: visible;
  }

  .workspace {
    flex-direction: column;
  }

  .editor-panel {
    min-height: 60vh;
  }

  .editor-area {
    flex-direction: column;
    min-height: 70vh;
  }

  .preview-container {
    width: 100% !important;
    min-height: 45vh;
    border-left: 0;
    border-top: 1px solid var(--border);
  }

  .resizer {
    display: none;
  }

  .sidebar {
    width: auto;
    border-left: 0;
    border-top: 1px solid var(--border);
  }

  .room-header {
    height: auto;
    padding: 12px 16px;
    flex-wrap: wrap;
  }

  .room-status {
    width: 100%;
  }
}
</style>
