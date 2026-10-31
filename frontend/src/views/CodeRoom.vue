<script setup>
import { ref, computed, onMounted, onUnmounted, nextTick, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import '@/monaco-workers'
import * as monaco from 'monaco-editor'
import { emmetHTML, emmetCSS, emmetJSX } from 'emmet-monaco-es'
import api, { getUser, isLoggedIn, ensureValidAccessToken } from '@/auth'
import AnnotationPopup from '@/components/AnnotationPopup.vue'
import FileActionDialog from '@/components/FileActionDialog.vue'
import ParticipantMenu from '@/components/ParticipantMenu.vue'
import PreviewBrowser from '@/components/PreviewBrowser.vue'
import { useTheme } from '@/theme'
import { getErrorMessages } from '@/utils/errors'
import { pickHtmlFile } from '@/utils/previewDocument.js'
import { setPageSeo } from '@/utils/seo'

const route = useRoute()
const router = useRouter()

const { resolvedTheme } = useTheme()

const UUID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

// В адресе может быть и UUID, и псевдоним комнаты.
const roomKey = String(route.params.id || '')
const roomId = ref(UUID_PATTERN.test(roomKey) ? roomKey : '')
const roomTitle = ref('')
const roomAlias = ref(UUID_PATTERN.test(roomKey) ? '' : roomKey)
const inviteCopied = ref(false)
let inviteTimer = null

const user = getUser()
const myUserId = ref(user?.id)
const myUsername = ref(user?.username || 'Гость')
const isHost = ref(false)
const hostId = ref(null)
const shortRoomId = computed(() => String(roomKey || '').slice(0, 8))

const roomLink = computed(() => {
  const key = roomAlias.value || roomId.value || roomKey
  return `${window.location.origin}/room/${key}`
})

setPageSeo({
  title: 'Комната — Peerlessons',
  description:
    'Приватная комната совместного редактирования кода в Peerlessons.',
  path: `/room/${roomKey}`,
  robots: 'noindex, nofollow',
  canonical: false,
})

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
const hasEditorSelection = ref(false)

const MAX_ROOM_FILES = 30
const FILE_NAME_RE = /^[A-Za-z0-9][A-Za-z0-9._-]*\.(html|css|js)$/i
const filesCount = computed(() => Object.keys(files.value).length)
// Вкладка, на которой сейчас редактор — нужна для режима слежения.
const editorTab = ref('index.html')
// Наблюдатель по умолчанию следует за редактором.
const followEditor = ref(true)
const canEdit = ref(false)
const currentEditorName = ref(null)
const currentEditorId = ref(null)
const participants = ref([])
const participantsVersion = ref(-1)
const connectionStatus = ref('connecting') // connecting | reconnecting | online | error
const connectError = ref('')
const raisedHands = ref([])

// ===== Пометки на коде =====
const annotations = ref([])
const annotationsLocked = ref(false)
// user_id, которым ведущий запретил создавать пометки.
const annotationBans = ref([])
const annotationDraft = ref(null)
const annotationText = ref('')
const annotationMessage = ref('')
const annotationPopup = ref(null)
const clearAnnotationsConfirm = ref(false)
let annotationMessageTimer = null
let clearAnnotationsTimer = null

// ===== Диалог создания/удаления файла =====
const fileDialog = ref(null)
const fileDialogError = ref('')
const fileDialogBusy = ref(false)
let pendingCreatedFile = ''

const ANNOTATION_POPUP_WIDTH = 300
const ANNOTATION_POPUP_HEIGHT = 340

const annotationDecorationHandles = new Map()
// Актуальные позиции пометок с учётом правок кода (id -> selection).
const annotationRanges = new Map()

const annotationInput = ref(null)

const hasRaisedHand = computed(() =>
  raisedHands.value.some(h => h.user_id === myUserId.value)
)

// Порядок поднятых рук = порядок поднятия; такие участники идут вверху списка.
const raisedHandOrder = computed(() => {
  const order = new Map()
  raisedHands.value.forEach((entry, index) => {
    order.set(entry.user_id, index)
  })
  return order
})

const sortedParticipants = computed(() => {
  const order = raisedHandOrder.value

  return [...participants.value].sort((a, b) => {
    const aOrder = order.get(a.user_id)
    const bOrder = order.get(b.user_id)

    if (aOrder !== undefined && bOrder !== undefined) return aOrder - bOrder
    if (aOrder !== undefined) return -1
    if (bOrder !== undefined) return 1
    return 0
  })
})

const canAnnotate = computed(() => {
  if (isHost.value) return true
  if (annotationsLocked.value) return false
  return !annotationBans.value.includes(myUserId.value)
})

const annotateTitle = computed(() => {
  if (!canAnnotate.value) return 'Ведущий ограничил создание пометок'
  if (!hasEditorSelection.value) return 'Сначала выделите фрагмент кода'
  return 'Оставить пометку на выделенном коде'
})

// Предпросмотр
const showPreview = ref(false)
const previewMode = ref('individual')
const previewShellUrl = `${import.meta.env.BASE_URL}preview.html`
const previewBrowser = ref(null)
// События общего превью, накопленные до монтирования мини-браузера.
let pendingPreviewEvents = []
// Страница, которую ведущий показывает в общем режиме (приходит с сервера).
const remotePreviewPage = ref(null)

const canRefreshPreview = computed(
  () => previewMode.value === 'individual' || isHost.value
)
const previewWidth = ref(400)
const isResizing = ref(false)
const editorArea = ref(null)
const MIN_PREVIEW_WIDTH = 250
const MIN_EDITOR_WIDTH = 320
let resizeStartX = 0
let resizeStartWidth = 0
let layoutFrame = null

// В общем режиме ведущий транслирует свои действия, остальные повторяют.
const previewInteractionMode = computed(() => {
  if (previewMode.value !== 'shared') return 'off'
  return isHost.value ? 'capture' : 'replay'
})

// Наблюдатели не могут уводить общий показ на другую страницу.
const previewReadonly = computed(
  () => previewMode.value === 'shared' && !isHost.value
)

const previewStartFile = computed(() => {
  if (previewMode.value === 'shared') {
    const page = remotePreviewPage.value
    if (page?.kind === 'file' && page.file) return page.file
    return pickHtmlFile(files.value, editorTab.value)
  }
  return pickHtmlFile(files.value, activeTab.value)
})

const previewStartPage = computed(() =>
  previewMode.value === 'shared' ? remotePreviewPage.value : null
)

// Удалённые курсоры
const remoteSelections = ref({})
const remoteCaretWidgets = new Map()
let decorationsCollection = null
let editor = null
let ws = null
let wsGeneration = 0
let reconnectTimer = null
let reconnectAttempt = 0
let shouldReconnect = true
let ignoreChanges = false

// ===== Утилиты =====
function monacoThemeId(value) {
  return value === 'light' ? 'peerless-light' : 'peerless-dark'
}

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

// Применяет изменения кода минимальной правкой, не сбрасывая скролл и модель.
function applyRemoteCode(nextValue) {
  if (!editor) return

  const model = editor.getModel()
  if (!model) return

  const currentValue = model.getValue()
  if (currentValue === nextValue) return

  let start = 0
  const maxStart = Math.min(currentValue.length, nextValue.length)

  while (start < maxStart && currentValue[start] === nextValue[start]) {
    start += 1
  }

  let endOld = currentValue.length
  let endNew = nextValue.length

  while (
    endOld > start &&
    endNew > start &&
    currentValue[endOld - 1] === nextValue[endNew - 1]
  ) {
    endOld -= 1
    endNew -= 1
  }

  const startPos = model.getPositionAt(start)
  const endPos = model.getPositionAt(endOld)

  ignoreChanges = true

  try {
    model.applyEdits([
      {
        range: new monaco.Range(
          startPos.lineNumber,
          startPos.column,
          endPos.lineNumber,
          endPos.column
        ),
        text: nextValue.slice(start, endNew),
        forceMoveMarkers: true
      }
    ])
  } finally {
    ignoreChanges = false
  }
}

// ===== Инициализация =====
onMounted(async () => {
  if (!isLoggedIn()) {
    router.push('/login')
    return
  }

  // В адресе может быть псевдоним — сначала узнаём UUID комнаты.
  if (!roomId.value) {
    try {
      const { data } = await api.get(
        `/rooms/by-alias/${encodeURIComponent(roomKey)}`
      )

      roomId.value = data.id
      roomTitle.value = data.title || ''
      roomAlias.value = data.alias || roomKey
    } catch (err) {
      shouldReconnect = false
      connectionStatus.value = 'error'
      connectError.value = getErrorMessages(err, 'Комната не найдена')[0]
      return
    }
  }

  await nextTick()
  window.addEventListener('resize', handleWindowResize)

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

    monaco.editor.defineTheme('peerless-light', {
      base: 'vs',
      inherit: true,
      rules: [
        { token: 'comment', foreground: '7d8697', fontStyle: 'italic' },
        { token: 'keyword', foreground: 'c44a17' },
        { token: 'string', foreground: '2f7d4f' },
        { token: 'number', foreground: '9a6700' },
        { token: 'tag', foreground: 'c44a17' },
        { token: 'attribute.name', foreground: '3a4150' },
        { token: 'attribute.value', foreground: '2f7d4f' }
      ],
      colors: {
        'editor.background': '#ffffff',
        'editor.foreground': '#1d2027',
        'editorLineNumber.foreground': '#b3bac6',
        'editorLineNumber.activeForeground': '#5b6474',
        'editor.lineHighlightBackground': '#f4f5f8',
        'editor.selectionBackground': '#de5a2245',
        'editor.inactiveSelectionBackground': '#de5a2220',
        'editorCursor.foreground': '#de5a22',
        'editorIndentGuide.background1': '#e6e9ef',
        'editorIndentGuide.activeBackground1': '#c8cfda',
        'editorWidget.background': '#ffffff',
        'editorWidget.border': '#dfe3ea',
        'editorSuggestWidget.background': '#ffffff',
        'editorSuggestWidget.border': '#dfe3ea',
        'editorSuggestWidget.selectedBackground': '#f0f2f6',
        'scrollbarSlider.background': '#c8cfda80',
        'scrollbarSlider.hoverBackground': '#b0b8c6',
        'scrollbarSlider.activeBackground': '#98a1b3'
      }
    })

    editor = monaco.editor.create(document.getElementById('editor'), {
        value: files.value[activeTab.value],
        language: getLang(activeTab.value),
        theme: monacoThemeId(resolvedTheme.value),
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
  refreshAnnotationDecorations()

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
    hasEditorSelection.value = Boolean(e.selection && !e.selection.isEmpty())

    if (!canEdit.value || !ws || ws.readyState !== WebSocket.OPEN) return
    const sel = e.selection
    send({
      type: 'cursor-update',
      selection: toRemoteSelection(sel),
      color: getUserColor(myUserId.value)
    })
  })

  // Клик по подсвеченному фрагменту открывает карточку пометки.
  editor.onMouseUp((event) => {
    const position = event.target.position
    if (!position) return

    const selection = editor.getSelection()
    if (selection && !selection.isEmpty()) return

    const annotation = annotationAt(position)
    if (annotation) {
      const mouseEvent = event.event?.browserEvent
      openAnnotationPopup(annotation, mouseEvent)
    }
  })

  await connectWS()
})

onUnmounted(() => {
  shouldReconnect = false
  wsGeneration += 1
  clearTimeout(reconnectTimer)
  clearTimeout(annotationMessageTimer)
  clearTimeout(clearAnnotationsTimer)
  closeAnnotationPopup()
  disposeAnnotationDecorations()

  stopResize()
  window.removeEventListener('resize', handleWindowResize)
  clearTimeout(inviteTimer)

  // ← НОВОЕ: очищаем свой курсор при уходе
  send({ type: 'cursor-clear' })
  for (const uid of [...remoteCaretWidgets.keys()]) {
    removeRemoteCaret(uid)
  }
  editor?.dispose()
  editor = null
  decorationsCollection = null
  ws?.close()
  ws = null
})

function getLang(name) {
  const lower = String(name || '').toLowerCase()
  if (lower.endsWith('.html') || lower.endsWith('.vue')) return 'html'
  if (lower.endsWith('.css')) return 'css'
  if (lower.endsWith('.js')) return 'javascript'
  if (lower.endsWith('.py')) return 'python'
  return 'plaintext'
}

function fileKind(name) {
  const lower = String(name || '').toLowerCase()
  if (lower.endsWith('.html') || lower.endsWith('.vue')) return 'html'
  if (lower.endsWith('.css')) return 'css'
  if (lower.endsWith('.js')) return 'js'
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

  // Декорации привязаны к модели — сбрасываем их до замены модели.
  disposeAnnotationDecorations()

  const lang = getLang(name)
    const oldModel = editor.getModel()
    const newModel = monaco.editor.createModel(
      files.value[name] || '',
      lang
    )
    editor.setModel(newModel)
  oldModel?.dispose()

  ignoreChanges = false

  hasEditorSelection.value = false

  if (canEdit.value) {
    editorTab.value = name
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

  updateRemoteDecorations()
}

// Ручной выбор вкладки: наблюдатель перестаёт следовать за редактором.
function selectTab(name) {
  if (name === activeTab.value) return

  if (!canEdit.value && followEditor.value) {
    followEditor.value = false
  }

  switchTab(name)
}

function toggleFollow() {
  followEditor.value = !followEditor.value

  if (followEditor.value && editorTab.value !== activeTab.value) {
    switchTab(editorTab.value)
  }
}

// Заменяет модель редактора без отправки code-update.
function loadTabIntoEditor(name) {
  if (!editor) return

  disposeAnnotationDecorations()

  const oldModel = editor.getModel()
  ignoreChanges = true

  try {
    const model = monaco.editor.createModel(
      files.value[name] || '',
      getLang(name)
    )
    editor.setModel(model)
  } finally {
    ignoreChanges = false
  }

  oldModel?.dispose()
  hasEditorSelection.value = false
  updateRemoteDecorations()
  refreshAnnotationDecorations()
}

// Применяет изменения состава файлов от сервера (создание/удаление).
function applyFilesUpdate(nextFiles, serverActiveTab) {
  if (!nextFiles || typeof nextFiles !== 'object') return

  const names = Object.keys(nextFiles)
  if (!names.length) return

  const has = (name) => Object.prototype.hasOwnProperty.call(nextFiles, name)
  const serverTab =
    typeof serverActiveTab === 'string' && has(serverActiveTab)
      ? serverActiveTab
      : ''
  const fallback =
    serverTab || (has('index.html') ? 'index.html' : names[0])

  let nextTab = activeTab.value
  if (!has(nextTab)) {
    nextTab = fallback
  } else if ((canEdit.value || followEditor.value) && serverTab) {
    nextTab = serverTab
  }

  files.value = { ...nextFiles }

  if (serverTab) editorTab.value = serverTab

  if (!editor) {
    activeTab.value = nextTab
  } else if (nextTab !== activeTab.value) {
    activeTab.value = nextTab
    loadTabIntoEditor(nextTab)
  } else if (canEdit.value) {
    // Не затираем неотправленные правки редактора.
    files.value[activeTab.value] = editor.getValue()
  } else {
    applyRemoteCode(files.value[activeTab.value] || '')

    const model = editor.getModel()
    const lang = getLang(activeTab.value)
    if (model && model.getLanguageId() !== lang) {
      monaco.editor.setModelLanguage(model, lang)
    }
  }

  // Пометки удалённых файлов больше некуда привязать.
  const present = new Set(names)
  if (annotations.value.some((annotation) => !present.has(annotation.file))) {
    annotations.value = annotations.value.filter((annotation) =>
      present.has(annotation.file)
    )
  }
  if (
    annotationPopup.value &&
    !present.has(annotationPopup.value.annotation.file)
  ) {
    closeAnnotationPopup()
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

// Изменения файлов мини-браузер пересобирает сам (с задержкой).

// Смена темы сайта переключает и оформление редактора.
watch(resolvedTheme, (value) => {
  if (editor) monaco.editor.setTheme(monacoThemeId(value))
})

watch(showPreview, (visible) => {
  if (visible) handleWindowResize()
})

// Пометки относятся к конкретному файлу — при смене вкладки
// пересобираем декорации с нуля.
watch(activeTab, () => {
  closeAnnotationPopup()
  cancelAnnotation()
  hasEditorSelection.value = false
  disposeAnnotationDecorations()
  refreshAnnotationDecorations()

  if (previewMode.value === 'individual') {
    previewBrowser.value?.openFile(activeTab.value)
  }
})

// В общем режиме переключение вкладки редактора меняет общий предпросмотр.
watch(editorTab, () => {
  if (previewMode.value === 'shared' && isHost.value) {
    previewBrowser.value?.openFile(editorTab.value)
  }
})

// Новые и удалённые пометки не должны сбрасывать позиции остальных.
watch(annotations, () => {
  refreshAnnotationDecorations()
})

// Если ведущий ограничил пометки — закрываем незавершённый черновик.
watch(canAnnotate, (allowed) => {
  if (!allowed) cancelAnnotation()
})

async function connectWS() {
  if (!shouldReconnect) return

  clearTimeout(reconnectTimer)

  const generation = ++wsGeneration
  // Новая сессия — версию сбрасываем: сервер мог перезапуститься.
  participantsVersion.value = -1
  connectionStatus.value = reconnectAttempt > 0 ? 'reconnecting' : 'connecting'
  connectError.value = ''

  const tokenReady = await ensureValidAccessToken()
  if (!tokenReady || generation !== wsGeneration || !shouldReconnect) {
    // Без токена реконнект бессмысленен: оверлей не должен крутиться вечно.
    if (!tokenReady) {
      shouldReconnect = false
      connectionStatus.value = 'error'
      connectError.value = 'Сессия истекла. Войдите заново.'
    }
    return
  }

  const protocol = location.protocol === 'https:' ? 'wss' : 'ws'
  const token = localStorage.getItem('token')
  const url = `${protocol}://${location.host}/ws/room/${roomId.value}`

  // Токен передаём через Sec-WebSocket-Protocol, а не в query,
  // чтобы он не попадал в access-логи nginx.
  const socket = token
    ? new WebSocket(url, [token])
    : new WebSocket(url)
  ws = socket

  socket.onopen = () => {
    if (generation !== wsGeneration) return
    console.log('WS подключён')
  }

  socket.onmessage = (e) => {
    if (generation !== wsGeneration) return

    const data = JSON.parse(e.data)

    // ========== ← НОВОЕ: полное состояние комнаты при подключении ==========
    if (data.type === 'room-state') {
      ignoreChanges = true

      try {
        if (data.title) roomTitle.value = data.title
        if (data.alias) roomAlias.value = data.alias

        files.value = data.files || files.value

        const nextTab = data.activeTab || activeTab.value
        const isEditor =
          Boolean(data.currentEditor) &&
          data.currentEditor.user_id === myUserId.value
        editorTab.value = nextTab
        // Редактор всегда открывает свой файл, наблюдатель — только в режиме слежения.
        if (isEditor || followEditor.value) {
          activeTab.value = nextTab
        }

        const wasMounted = Boolean(previewBrowser.value)

        showPreview.value = !!data.showPreview
        previewMode.value =
          data.previewMode === 'shared' ? 'shared' : 'individual'
        remotePreviewPage.value = data.previewPage || null
        pendingPreviewEvents = Array.isArray(data.previewEvents)
          ? [...data.previewEvents]
          : []
        if (data.showPreview) {
          nextTick(handleWindowResize)
          nextTick(() => {
            if (previewMode.value !== 'shared') return
            if (!wasMounted || !previewBrowser.value) return

            previewBrowser.value.applyRemotePage(remotePreviewPage.value)
            previewBrowser.value.reloadWithEvents(pendingPreviewEvents)
          })
        }

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

        // Участники — только если версия не старше уже применённой
        const version = data.participantsVersion ?? 0
        if (Array.isArray(data.participants) && version >= participantsVersion.value) {
          participants.value = data.participants
          participantsVersion.value = version
        }

        // Поднятые руки
        if (data.raisedHands) {
          raisedHands.value = data.raisedHands
        }

        // Пометки на коде и ограничения на их создание
        annotations.value = Array.isArray(data.annotations)
          ? data.annotations
          : []
        annotationsLocked.value = !!data.annotationsLocked
        annotationBans.value = Array.isArray(data.bannedAnnotationUserIds)
          ? data.bannedAnnotationUserIds
          : []

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

        // Курсоры применяем после установки модели и активной вкладки.
        updateRemoteDecorations()
      } catch (err) {
        // Ошибка в отрисовке состояния не должна означать «не подключились».
        console.error('Не удалось применить room-state:', err)
      } finally {
        ignoreChanges = false
        // Сокет уже открыт и состояние получено — оверлей убираем в любом
        // случае, иначе он останется навсегда при неожиданном исключении.
        connectionStatus.value = 'online'
        reconnectAttempt = 0
      }

      return
    }

    // Обычное обновление кода
    if (data.type === 'code-update') {
      files.value = data.files || files.value

      const prevActiveTab = activeTab.value
      const prevEditorTab = editorTab.value
      const nextTab = data.activeTab || editorTab.value
      editorTab.value = nextTab

      // Наблюдатель переключается за редактором только в режиме слежения.
      if (!canEdit.value && followEditor.value) {
        activeTab.value = nextTab
      }

      if (editor) {
        const newVal = files.value[activeTab.value] || ''
        applyRemoteCode(newVal)

        const model = editor.getModel()
        const lang = getLang(activeTab.value)
        if (model && model.getLanguageId() !== lang) {
          monaco.editor.setModelLanguage(model, lang)
        }
      }

      if (editorTab.value !== prevEditorTab) {
        // Редактор ушёл в другой файл — старые каретки к нему уже не относятся.
        remoteSelections.value = {}
        clearRemoteDecorations()
      } else if (activeTab.value !== prevActiveTab) {
        updateRemoteDecorations()
      }
    }

    if (data.type === 'editor-changed') {
      currentEditorName.value = data.username
      currentEditorId.value = data.user_id
      canEdit.value = data.user_id === myUserId.value
    }

    if (data.type === 'participants') {
      const version = typeof data.version === 'number' ? data.version : 0
      if (version >= participantsVersion.value) {
        participants.value = data.list || []
        participantsVersion.value = version
      }
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
      const wasMounted = Boolean(previewBrowser.value)

      showPreview.value = data.show
      remotePreviewPage.value = data.page || null

      if (data.show) {
        pendingPreviewEvents = Array.isArray(data.events)
          ? [...data.events]
          : []

        if (wasMounted) {
          previewBrowser.value.applyRemotePage(remotePreviewPage.value)
          previewBrowser.value.reloadWithEvents(pendingPreviewEvents)
        }

        nextTick(handleWindowResize)
      } else {
        pendingPreviewEvents = []
      }
    }

    if (data.type === 'preview-refresh') {
      pendingPreviewEvents = []
      previewBrowser.value?.refresh()
    }

    if (data.type === 'preview-mode') {
      previewMode.value = data.mode === 'shared' ? 'shared' : 'individual'
      remotePreviewPage.value =
        previewMode.value === 'shared' ? data.page || null : null

      if (showPreview.value) {
        previewBrowser.value?.applyRemotePage(remotePreviewPage.value)
      }
    }

    if (data.type === 'preview-navigate' && data.page) {
      if (previewMode.value === 'shared' && !isHost.value) {
        remotePreviewPage.value = data.page
        previewBrowser.value?.applyRemotePage(data.page)
      }
    }

    if (data.type === 'preview-interaction' && data.event) {
      if (previewMode.value === 'shared' && !isHost.value) {
        if (previewBrowser.value) {
          previewBrowser.value.replay(data.event)
        } else {
          pendingPreviewEvents.push(data.event)
          if (pendingPreviewEvents.length > 300) {
            pendingPreviewEvents.shift()
          }
        }
      }
    }

    if (data.type === 'files-update') {
      applyFilesUpdate(data.files, data.activeTab)
      if (fileDialog.value) closeFileDialog()

      if (pendingCreatedFile) {
        const created = pendingCreatedFile
        pendingCreatedFile = ''

        if (data.files && data.files[created]) {
          selectTab(created)
        }
      }
    }

    if (data.type === 'file-error') {
      pendingCreatedFile = ''
      if (fileDialog.value) {
        fileDialogError.value = data.reason || 'Не удалось изменить файлы.'
        fileDialogBusy.value = false
      }
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
      if (participantMenu.value?.participant.user_id === data.user_id) {
        closeParticipantMenu()
      }
      updateRemoteDecorations()
    }

    // ===== Пометки на коде =====
    if (data.type === 'annotation-added' && data.annotation) {
      const index = annotations.value.findIndex(
        (annotation) => annotation.id === data.annotation.id
      )

      if (index === -1) {
        annotations.value = [...annotations.value, data.annotation]
      } else {
        annotations.value = annotations.value.map((annotation) =>
          annotation.id === data.annotation.id ? data.annotation : annotation
        )
      }
    }

    if (data.type === 'annotation-removed') {
      annotations.value = annotations.value.filter(
        (annotation) => annotation.id !== data.id
      )
      if (annotationPopup.value?.annotation.id === data.id) {
        closeAnnotationPopup()
      }
    }

    if (data.type === 'annotations-cleared') {
      annotations.value = []
      closeAnnotationPopup()
    }

    if (data.type === 'annotation-ban') {
      const bans = new Set(annotationBans.value)
      if (data.banned) bans.add(data.user_id)
      else bans.delete(data.user_id)
      annotationBans.value = [...bans]
    }

    if (data.type === 'annotation-lock') {
      annotationsLocked.value = !!data.locked
    }

    if (data.type === 'annotation-denied') {
      showAnnotationMessage(data.reason || 'Не удалось оставить пометку.')
    }

    if (data.type === 'kicked') {
      // Ведущий исключил нас: реконнект не нужен, показываем причину.
      shouldReconnect = false
      connectError.value = data.reason || 'Вас исключили из комнаты.'
      connectionStatus.value = 'error'
      ws?.close()
      ws = null
      return
    }

    if (data.type === 'error') {
      console.error('Ошибка от сервера:', data.message)
    }
  }

  socket.onclose = (event) => {
    if (generation !== wsGeneration) return

    console.log('WS отключён', event.code, event.reason)
    remoteSelections.value = {}
    updateRemoteDecorations()
    ws = null

    if (!shouldReconnect) return

    // Постоянные ошибки: реконнект их не исправит, а вечный спиннер
    // скрывает причину.
    if (PERMANENT_CLOSE_CODES.has(event.code)) {
      shouldReconnect = false
      connectionStatus.value = 'error'
      connectError.value = describeClose(event)
      return
    }

    scheduleReconnect()
  }
}

// 4003 — пользователя исключил ведущий (RoomSession._handle_kick_user),
// 4401/4403/4404 отдаёт сервер (RoomSession._reject), 1008 — старый вариант.
const PERMANENT_CLOSE_CODES = new Set([4003, 4401, 4403, 4404, 1008])

function describeClose(event) {
  if (event.code === 4003) return 'Ведущий исключил вас из комнаты.'
  if (event.code === 4401) return 'Не удалось подтвердить сессию. Войдите заново.'
  if (event.code === 4403) return 'Подключение с этого адреса запрещено сервером.'
  if (event.code === 4404) return 'Комната не найдена или удалена.'
  return event.reason || 'Не удалось подключиться к комнате.'
}

// ===== Приглашение =====

async function copyInvite() {
  const title = roomTitle.value.trim()
  const text = title
    ? `Присоединяйтесь к комнате «${title}» на Peerlessons: ${roomLink.value}`
    : `Присоединяйтесь к комнате на Peerlessons: ${roomLink.value}`

  if (await writeToClipboard(text)) {
    inviteCopied.value = true
    clearTimeout(inviteTimer)
    inviteTimer = setTimeout(() => {
      inviteCopied.value = false
    }, 2000)
  }
}

async function writeToClipboard(text) {
  if (navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(text)
      return true
    } catch {
      // Ниже — запасной вариант для браузеров без Clipboard API.
    }
  }

  try {
    const area = document.createElement('textarea')
    area.value = text
    area.setAttribute('readonly', '')
    area.style.position = 'fixed'
    area.style.opacity = '0'
    document.body.appendChild(area)
    area.select()
    const copied = document.execCommand('copy')
    document.body.removeChild(area)
    return copied
  } catch {
    return false
  }
}

function scheduleReconnect() {
  if (!shouldReconnect) return

  reconnectAttempt += 1
  connectionStatus.value = 'reconnecting'

  const delay = Math.min(1000 * 2 ** Math.min(reconnectAttempt - 1, 4), 10_000)

  clearTimeout(reconnectTimer)
  reconnectTimer = setTimeout(() => {
    connectWS().catch(() => scheduleReconnect())
  }, delay)
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

function clearRemoteDecorations() {
  decorationsCollection?.set([])
  for (const uid of [...remoteCaretWidgets.keys()]) removeRemoteCaret(uid)
}

function updateRemoteDecorations() {
  if (!editor || !decorationsCollection) return

  // Курсор относится к конкретному файлу. Если открыт другой файл,
  // показывать чужие каретки и выделения нельзя — они будут не на месте.
  if (editorTab.value !== activeTab.value) {
    clearRemoteDecorations()
    return
  }

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

// ===== Пометки на коде =====

function ensureAnnotationStyle(userId, color) {
  const id = `annotation-style-${userId}`
  if (document.getElementById(id)) return
  const style = document.createElement('style')
  style.id = id
  style.textContent = `
    .annotation-mark-${userId} {
      background-color: ${color}26 !important;
      border-bottom: 2px solid ${color} !important;
    }
  `
  document.head.appendChild(style)
}

function buildAnnotationDecoration(annotation) {
  const color = getUserColor(annotation.user_id)
  ensureAnnotationStyle(annotation.user_id, color)

  const selection = annotationRange(annotation)
  return {
    range: new monaco.Range(
      selection.startLineNumber,
      selection.startColumn,
      selection.endLineNumber,
      selection.endColumn
    ),
    options: {
      inlineClassName: `annotation-mark-${annotation.user_id}`,
      hoverMessage: {
        value: `**${annotation.username}**\n\n${annotation.text}`
      },
      stickiness:
        monaco.editor.TrackedRangeStickiness.NeverGrowsWhenTypingAtEdges
    }
  }
}

// Актуальный диапазон пометки: Monaco сдвигает декорации при правках,
// поэтому координаты, сохранённые при создании, могут устареть.
function annotationRange(annotation) {
  return annotationRanges.get(annotation.id) || annotation.selection
}

function rememberAnnotationRange(id) {
  const handle = annotationDecorationHandles.get(id)
  const range = handle?.getRange(0)
  if (!range) return

  annotationRanges.set(id, {
    startLineNumber: range.startLineNumber,
    startColumn: range.startColumn,
    endLineNumber: range.endLineNumber,
    endColumn: range.endColumn
  })
}

// Каждая пометка живёт в своей коллекции декораций: так Monaco сам
// сдвигает её при редактировании и новые пометки не сбрасывают старые.
function refreshAnnotationDecorations() {
  if (!editor) return

  const knownIds = new Set(annotations.value.map((annotation) => annotation.id))
  for (const id of annotationRanges.keys()) {
    if (!knownIds.has(id)) annotationRanges.delete(id)
  }

  const visible = annotations.value.filter(
    (annotation) => annotation.file === activeTab.value
  )
  const visibleIds = new Set(visible.map((annotation) => annotation.id))

  for (const [id, handle] of annotationDecorationHandles) {
    if (visibleIds.has(id)) continue
    rememberAnnotationRange(id)
    handle.clear()
    annotationDecorationHandles.delete(id)
  }

  for (const annotation of visible) {
    if (annotationDecorationHandles.has(annotation.id)) continue

    const handle = editor.createDecorationsCollection([
      buildAnnotationDecoration(annotation)
    ])
    annotationDecorationHandles.set(annotation.id, handle)
  }
}

function disposeAnnotationDecorations() {
  for (const [id, handle] of annotationDecorationHandles) {
    rememberAnnotationRange(id)
    handle.clear()
  }
  annotationDecorationHandles.clear()
}

function selectionSize(selection) {
  return (
    (selection.endLineNumber - selection.startLineNumber) * 1000 +
    (selection.endColumn - selection.startColumn)
  )
}

function annotationAt(position) {
  let match = null
  let matchSize = Infinity

  // Ориентируемся на текущее положение декораций: при правках кода
  // Monaco сдвигает их, а сохранённые в пометке координаты уже старые.
  for (const [id, handle] of annotationDecorationHandles) {
    const range = handle.getRange(0)
    if (!range || !range.containsPosition(position)) continue

    const annotation = annotations.value.find((item) => item.id === id)
    if (!annotation) continue

    const size = selectionSize({
      startLineNumber: range.startLineNumber,
      startColumn: range.startColumn,
      endLineNumber: range.endLineNumber,
      endColumn: range.endColumn
    })

    if (size < matchSize) {
      match = annotation
      matchSize = size
    }
  }

  return match
}

function openAnnotationPopup(annotation, mouseEvent) {
  const x = mouseEvent?.clientX ?? window.innerWidth / 2
  const y = mouseEvent?.clientY ?? window.innerHeight / 2

  const left = Math.max(
    8,
    Math.min(x, window.innerWidth - ANNOTATION_POPUP_WIDTH - 8)
  )
  const below = y + 14
  const top =
    below + ANNOTATION_POPUP_HEIGHT <= window.innerHeight - 8
      ? below
      : Math.max(8, y - ANNOTATION_POPUP_HEIGHT - 14)

  const range = annotationDecorationHandles.get(annotation.id)?.getRange(0)

  annotationPopup.value = {
    annotation,
    top,
    left,
    lineStart: range?.startLineNumber,
    lineEnd: range?.endLineNumber
  }
}

function closeAnnotationPopup() {
  annotationPopup.value = null
}

// ===== Resizer =====
function getMaxPreviewWidth() {
  const areaWidth = editorArea.value?.clientWidth || window.innerWidth
  return Math.max(MIN_PREVIEW_WIDTH, areaWidth - MIN_EDITOR_WIDTH - 6)
}

function scheduleEditorLayout() {
  if (layoutFrame !== null) return

  layoutFrame = requestAnimationFrame(() => {
    layoutFrame = null
    editor?.layout()
  })
}

function startResize(e) {
  if (e.button !== 0 || isResizing.value) return

  isResizing.value = true
  resizeStartX = e.clientX
  resizeStartWidth = previewWidth.value

  document.body.style.cursor = 'col-resize'
  document.body.style.userSelect = 'none'

  window.addEventListener('mousemove', onResize)
  window.addEventListener('mouseup', stopResize)
  window.addEventListener('blur', stopResize)
  document.documentElement.addEventListener('mouseleave', stopResize)

  e.preventDefault()
}

function onResize(e) {
  if (!isResizing.value) return

  const delta = resizeStartX - e.clientX
  const maxWidth = getMaxPreviewWidth()
  const nextWidth = Math.min(
    Math.max(resizeStartWidth + delta, MIN_PREVIEW_WIDTH),
    maxWidth
  )

  if (nextWidth !== previewWidth.value) {
    previewWidth.value = nextWidth
    scheduleEditorLayout()
  }
}

function stopResize() {
  if (!isResizing.value) return

  isResizing.value = false
  document.body.style.cursor = ''
  document.body.style.userSelect = ''

  window.removeEventListener('mousemove', onResize)
  window.removeEventListener('mouseup', stopResize)
  window.removeEventListener('blur', stopResize)
  document.documentElement.removeEventListener('mouseleave', stopResize)

  if (layoutFrame !== null) {
    cancelAnimationFrame(layoutFrame)
    layoutFrame = null
  }

  editor?.layout()
}

function handleWindowResize() {
  if (window.innerWidth <= 900) return

  const maxWidth = getMaxPreviewWidth()

  if (previewWidth.value > maxWidth) {
    previewWidth.value = maxWidth
    editor?.layout()
  }
}

// ===== Действия =====
function togglePreview() {
  // Видимость результата синхронизируется сервером для всех участников.
  const show = !showPreview.value
  const message = { type: 'preview-toggle', show }

  // При открытии сообщаем, какую страницу показываем. Это нужно
  // поздно подключившимся участникам общего режима.
  if (show) {
    const page =
      previewStartPage.value ||
      (previewStartFile.value
        ? { kind: 'file', file: previewStartFile.value }
        : null)
    if (page) message.page = page
  }

  send(message)
}

function refreshPreview() {
  if (!canRefreshPreview.value) return

  previewBrowser.value?.refresh()

  if (previewMode.value === 'shared') {
    send({ type: 'preview-refresh' })
  }
}

function togglePreviewMode() {
  if (!isHost.value) return

  const mode = previewMode.value === 'shared' ? 'individual' : 'shared'
  const message = { type: 'preview-mode', mode }

  if (mode === 'shared') {
    const page =
      previewBrowser.value?.getActivePage?.() ||
      previewStartPage.value ||
      (previewStartFile.value
        ? { kind: 'file', file: previewStartFile.value }
        : null)
    if (page) message.page = page
  }

  send(message)
}

function onPreviewInteraction(detail) {
  if (!detail) return
  send({ type: 'preview-interaction', event: detail })
}

function onPreviewNavigate(page) {
  if (!isHost.value || !page) return

  remotePreviewPage.value = page
  send({ type: 'preview-navigate', page })
}

function onPreviewOpenFile(file) {
  if (!file) return
  selectTab(file)
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

// ===== Меню действий ведущего =====
const participantMenu = ref(null)

const PARTICIPANT_MENU_WIDTH = 220
const PARTICIPANT_MENU_HEIGHT = 150

function openParticipantMenu(event, participant) {
  if (
    participantMenu.value?.participant.user_id === participant.user_id
  ) {
    closeParticipantMenu()
    return
  }

  const rect = event.currentTarget.getBoundingClientRect()
  const left = Math.max(
    8,
    Math.min(
      rect.right - PARTICIPANT_MENU_WIDTH,
      window.innerWidth - PARTICIPANT_MENU_WIDTH - 8
    )
  )
  const below = rect.bottom + 6
  const top =
    below + PARTICIPANT_MENU_HEIGHT <= window.innerHeight - 8
      ? below
      : Math.max(8, rect.top - PARTICIPANT_MENU_HEIGHT - 6)

  participantMenu.value = { participant, top, left }
}

function closeParticipantMenu() {
  participantMenu.value = null
}

function grantEditFromMenu() {
  const participant = participantMenu.value?.participant
  closeParticipantMenu()
  if (participant) grantEdit(participant.user_id)
}

function revokeEditFromMenu() {
  closeParticipantMenu()
  revokeEdit()
}

function kickUserFromMenu() {
  const participant = participantMenu.value?.participant
  closeParticipantMenu()

  if (!participant || !isHost.value) return
  if (participant.user_id === myUserId.value) return

  send({ type: 'kick-user', user_id: participant.user_id })
}

// ===== Создание и удаление файлов =====

function openFileDialogAt(event, dialog) {
  const rect = event.currentTarget.getBoundingClientRect()
  const width = 260
  const height = dialog.mode === 'create' ? 220 : 170

  const left = Math.max(
    8,
    Math.min(rect.left, window.innerWidth - width - 8)
  )
  const below = rect.bottom + 6
  const top =
    below + height <= window.innerHeight - 8
      ? below
      : Math.max(8, rect.top - height - 6)

  fileDialog.value = { ...dialog, top, left }
  fileDialogError.value = ''
  fileDialogBusy.value = false
}

function openCreateFileDialog(event) {
  if (!isHost.value) return
  if (filesCount.value >= MAX_ROOM_FILES) return

  openFileDialogAt(event, { mode: 'create', fileName: '' })
}

function openDeleteFileDialog(event, name) {
  if (!isHost.value) return
  if (filesCount.value <= 1) return

  openFileDialogAt(event, { mode: 'delete', fileName: name })
}

function closeFileDialog() {
  fileDialog.value = null
  fileDialogError.value = ''
  fileDialogBusy.value = false
}

function validateNewFileName(name) {
  if (!name) return 'Введите имя файла'
  if (name.length > 64) return 'Слишком длинное имя файла'
  if (!FILE_NAME_RE.test(name)) {
    return 'Только латиница, цифры, точка, дефис и подчёркивание; расширение .html, .css или .js'
  }
  if (filesCount.value >= MAX_ROOM_FILES) return 'Достигнут лимит файлов'

  const lower = name.toLowerCase()
  if (Object.keys(files.value).some((file) => file.toLowerCase() === lower)) {
    return 'Файл с таким именем уже существует'
  }

  return ''
}

function submitFileDialog(value) {
  const dialog = fileDialog.value
  if (!dialog || fileDialogBusy.value) return

  if (dialog.mode === 'delete') {
    fileDialogBusy.value = true
    send({ type: 'file-delete', name: dialog.fileName })
    return
  }

  const name = String(value || '').trim()
  const error = validateNewFileName(name)

  if (error) {
    fileDialogError.value = error
    return
  }

  fileDialogBusy.value = true
  pendingCreatedFile = name
  send({ type: 'file-create', name })
}

// ===== Создание и модерация пометок =====

function showAnnotationMessage(message) {
  annotationMessage.value = message
  clearTimeout(annotationMessageTimer)
  annotationMessageTimer = setTimeout(() => {
    annotationMessage.value = ''
  }, 4000)
}

function startAnnotation() {
  if (!editor || !canAnnotate.value) return

  const model = editor.getModel()
  const selection = editor.getSelection()

  if (!model || !selection || selection.isEmpty()) {
    showAnnotationMessage('Сначала выделите фрагмент кода.')
    return
  }

  annotationDraft.value = {
    file: activeTab.value,
    selection: {
      startLineNumber: selection.startLineNumber,
      startColumn: selection.startColumn,
      endLineNumber: selection.endLineNumber,
      endColumn: selection.endColumn
    },
    excerpt: model.getValueInRange(selection).slice(0, 200)
  }
  annotationText.value = ''

  nextTick(() => annotationInput.value?.focus())
}

function cancelAnnotation() {
  annotationDraft.value = null
  annotationText.value = ''
}

function submitAnnotation() {
  const draft = annotationDraft.value
  const text = annotationText.value.trim()

  if (!draft || !text || !canAnnotate.value) return

  if (!ws || ws.readyState !== WebSocket.OPEN) {
    showAnnotationMessage('Нет соединения с комнатой. Попробуйте ещё раз.')
    return
  }

  send({
    type: 'annotation-add',
    file: draft.file,
    selection: draft.selection,
    text
  })

  annotationDraft.value = null
  annotationText.value = ''
}

function revealAnnotation(annotation) {
  if (annotation.file !== activeTab.value) {
    selectTab(annotation.file)
  }

  nextTick(() => {
    if (!editor) return

    const selection = annotationRange(annotation)
    const range = new monaco.Range(
      selection.startLineNumber,
      selection.startColumn,
      selection.endLineNumber,
      selection.endColumn
    )

    editor.revealRangeInCenter(range)
    editor.setSelection(range)
    editor.focus()
  })
}

function removeAnnotation(id) {
  if (!isHost.value || !id) return
  send({ type: 'annotation-remove', id })
}

function removeAnnotationFromPopup() {
  const annotation = annotationPopup.value?.annotation
  closeAnnotationPopup()
  if (annotation) removeAnnotation(annotation.id)
}

function clearAllAnnotations() {
  if (!isHost.value || !annotations.value.length) return

  if (!clearAnnotationsConfirm.value) {
    clearAnnotationsConfirm.value = true
    clearTimeout(clearAnnotationsTimer)
    clearAnnotationsTimer = setTimeout(() => {
      clearAnnotationsConfirm.value = false
    }, 4000)
    return
  }

  clearAnnotationsConfirm.value = false
  clearTimeout(clearAnnotationsTimer)
  send({ type: 'annotation-clear' })
}

function toggleAnnotationsLock() {
  if (!isHost.value) return
  send({ type: 'annotation-lock', locked: !annotationsLocked.value })
}

function toggleAnnotationBanFromMenu() {
  const participant = participantMenu.value?.participant
  closeParticipantMenu()

  if (!participant || !isHost.value) return
  if (participant.user_id === myUserId.value) return

  send({
    type: 'annotation-ban',
    user_id: participant.user_id,
    banned: !annotationBans.value.includes(participant.user_id)
  })
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
          <span class="room-title">{{ roomTitle || 'Комната' }}</span>
          <span class="room-id">{{ roomAlias || shortRoomId }}</span>
        </div>
      </div>

      <div class="room-header-right">
        <div class="room-status">
          <span class="status-dot" :class="{ edit: canEdit }"></span>
          <span v-if="currentEditorName" class="status-text">
            Редактирует <b>{{ currentEditorName }}</b>
          </span>
          <span v-else class="status-text">Режим просмотра</span>
          <span v-if="canEdit" class="badge badge-accent">Вы редактируете</span>
        </div>

        <button
          v-if="isHost"
          type="button"
          class="btn btn-secondary btn-sm invite-btn"
          @click="copyInvite"
        >
          {{ inviteCopied ? 'Скопировано' : 'Пригласить' }}
        </button>
      </div>
    </header>

    <div class="workspace">
      <section class="editor-panel">
        <div class="editor-toolbar">
          <div class="tabs-wrap">
            <div class="tabs">
              <div
                v-for="(_, name) in files"
                :key="name"
                class="tab-group"
              >
                <button
                  type="button"
                  :class="['tab', { active: name === activeTab }]"
                  @click="selectTab(name)"
                >
                  <span class="tab-dot" :class="fileKind(name)"></span>
                  {{ name }}
                </button>
                <button
                  v-if="isHost && name === activeTab && filesCount > 1"
                  type="button"
                  class="tab-remove"
                  data-file-dialog-trigger
                  :aria-label="`Удалить файл ${name}`"
                  title="Удалить файл"
                  @click.stop="openDeleteFileDialog($event, name)"
                >
                  ×
                </button>
              </div>
            </div>

            <button
              v-if="isHost"
              type="button"
              class="tab-add"
              data-file-dialog-trigger
              title="Создать файл"
              :disabled="filesCount >= MAX_ROOM_FILES"
              @click="openCreateFileDialog"
            >
              +
            </button>
          </div>

          <div class="toolbar-actions">
            <button
              type="button"
              class="btn btn-ghost btn-sm annotate-btn"
              :disabled="!canAnnotate || !hasEditorSelection"
              :title="annotateTitle"
              @click="startAnnotation"
            >
              <svg
                viewBox="0 0 24 24"
                width="15"
                height="15"
                fill="none"
                stroke="currentColor"
                stroke-width="1.8"
                stroke-linecap="round"
                stroke-linejoin="round"
                aria-hidden="true"
              >
                <path d="M12 20h9" />
                <path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4Z" />
              </svg>
              Пометка
            </button>
            <button
              v-if="!canEdit"
              type="button"
              class="btn btn-ghost btn-sm follow-toggle"
              :class="{ 'is-on': followEditor }"
              :aria-pressed="followEditor"
              :title="
                followEditor
                  ? 'Вкладки автоматически переключаются за редактором'
                  : 'Вы переключаете вкладки самостоятельно'
              "
              @click="toggleFollow"
            >
              <span class="follow-switch" aria-hidden="true"></span>
              Слежение
            </button>
            <button
              v-if="canEdit || isHost"
              class="btn btn-secondary btn-sm"
              @click="togglePreview"
            >
              {{ showPreview ? 'Скрыть результат' : 'Запустить код' }}
            </button>
            <button
              v-if="showPreview && canRefreshPreview"
              class="btn btn-ghost btn-sm"
              @click="refreshPreview"
              title="Обновить предпросмотр"
            >
              Обновить
            </button>
          </div>
        </div>

        <div ref="editorArea" class="editor-area">
          <div id="editor" class="editor"></div>

          <div v-if="showPreview" class="resizer" @mousedown="startResize"></div>

          <div v-if="showPreview" class="preview-container" :style="{ width: previewWidth + 'px' }">
            <div class="preview-header">
              <span class="preview-title">
                <span class="preview-dot"></span>
                Результат
                <span
                  v-if="previewMode === 'shared'"
                  class="preview-mode-tag"
                >
                  {{ isHost ? 'общий' : 'показ ведущего' }}
                </span>
              </span>
              <div class="preview-header-actions">
                <button
                  v-if="isHost"
                  type="button"
                  class="preview-mode-btn"
                  :class="{ 'is-on': previewMode === 'shared' }"
                  :title="
                    previewMode === 'shared'
                      ? 'Все видят действия ведущего. Переключить на отдельный результат'
                      : 'У каждого свой результат. Переключить на общий показ'
                  "
                  @click="togglePreviewMode"
                >
                  {{ previewMode === 'shared' ? 'Общий' : 'Личный' }}
                </button>
                <button
                  v-if="canEdit || isHost"
                  class="icon-btn"
                  @click="togglePreview"
                  title="Закрыть"
                >
                  ×
                </button>
              </div>
            </div>
            <!-- Мини-браузер: вкладки, адресная строка и панель разработчика.
                 Пользовательский код по-прежнему живёт в sandbox без
                 allow-same-origin и не может добраться до приложения. -->
            <PreviewBrowser
              ref="previewBrowser"
              :files="files"
              :shell-url="previewShellUrl"
              :start-file="previewStartFile"
              :start-page="previewStartPage"
              :interaction-mode="previewInteractionMode"
              :readonly="previewReadonly"
              :shared="previewMode === 'shared'"
              :initial-events="pendingPreviewEvents"
              @interaction="onPreviewInteraction"
              @navigate="onPreviewNavigate"
              @open-file="onPreviewOpenFile"
            />
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
            <li
              v-for="p in sortedParticipants"
              :key="p.user_id"
              class="participant"
            >
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
                v-if="raisedHandOrder.has(p.user_id)"
                class="participant-hand"
                title="Поднял руку"
              >
                <svg
                  viewBox="0 0 24 24"
                  width="14"
                  height="14"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="1.8"
                  stroke-linecap="round"
                  stroke-linejoin="round"
                  aria-hidden="true"
                >
                  <path d="M8 13V4.5a1.5 1.5 0 0 1 3 0V12" />
                  <path d="M11 11.5v-8a1.5 1.5 0 0 1 3 0V12" />
                  <path d="M14 11.5v-6a1.5 1.5 0 0 1 3 0V12" />
                  <path
                    d="M17 11.5a1.5 1.5 0 0 1 3 0V15a6 6 0 0 1-6 6h-1.5a6.5 6.5 0 0 1-5.2-2.6L4 14.5a1.6 1.6 0 0 1 2.5-2L9 15"
                  />
                </svg>
              </span>
              <span
                v-if="p.user_id === currentEditorId"
                class="editing-dot"
                title="Редактирует сейчас"
              ></span>
              <span v-if="p.user_id === hostId" class="tag">хост</span>
              <button
                v-if="isHost && p.user_id !== myUserId"
                type="button"
                class="participant-more"
                data-participant-menu-trigger
                :aria-label="`Действия участника ${p.username}`"
                aria-haspopup="menu"
                :aria-expanded="
                  participantMenu?.participant.user_id === p.user_id
                "
                @click.stop="openParticipantMenu($event, p)"
              >
                <svg
                  viewBox="0 0 24 24"
                  width="16"
                  height="16"
                  fill="currentColor"
                  aria-hidden="true"
                >
                  <circle cx="5" cy="12" r="1.7" />
                  <circle cx="12" cy="12" r="1.7" />
                  <circle cx="19" cy="12" r="1.7" />
                </svg>
              </button>
            </li>
          </ul>
        </section>

        <section class="side-card">
          <h3 class="side-title">
            Пометки
            <span class="count">{{ annotations.length }}</span>
          </h3>

          <div v-if="isHost" class="annotation-moderation">
            <button
              type="button"
              class="btn btn-ghost btn-xs"
              :class="{ 'is-on': annotationsLocked }"
              :title="
                annotationsLocked
                  ? 'Создавать пометки может только ведущий'
                  : 'Создавать пометки могут все участники'
              "
              @click="toggleAnnotationsLock"
            >
              {{ annotationsLocked ? 'Только хост' : 'Могут все' }}
            </button>
            <button
              v-if="annotations.length"
              type="button"
              class="btn btn-ghost btn-xs annotation-clear-btn"
              :class="{ 'is-confirming': clearAnnotationsConfirm }"
              @click="clearAllAnnotations"
            >
              {{ clearAnnotationsConfirm ? 'Точно очистить?' : 'Очистить все' }}
            </button>
          </div>

          <p v-if="annotationMessage" class="field-error annotation-message">
            {{ annotationMessage }}
          </p>

          <form
            v-if="annotationDraft"
            class="annotation-compose"
            @submit.prevent="submitAnnotation"
          >
            <p class="annotation-compose-excerpt">
              {{ annotationDraft.excerpt || '…' }}
            </p>
            <div class="field">
              <label class="label" for="annotation-text">
                Вопрос или описание
              </label>
              <textarea
                id="annotation-text"
                ref="annotationInput"
                v-model="annotationText"
                class="input annotation-textarea"
                rows="3"
                maxlength="600"
                placeholder="Что нужно объяснить в этом фрагменте?"
                @keydown.esc.prevent="cancelAnnotation"
                @keydown.ctrl.enter.prevent="submitAnnotation"
                @keydown.meta.enter.prevent="submitAnnotation"
              ></textarea>
            </div>
            <div class="annotation-compose-actions">
              <button
                type="submit"
                class="btn btn-primary btn-xs"
                :disabled="!annotationText.trim()"
              >
                Оставить
              </button>
              <button
                type="button"
                class="btn btn-ghost btn-xs"
                @click="cancelAnnotation"
              >
                Отмена
              </button>
            </div>
          </form>

          <p v-else-if="!annotations.length" class="side-empty">
            {{
              canAnnotate
                ? 'Выделите код и нажмите «Пометка», чтобы задать вопрос.'
                : 'Создание пометок ограничено ведущим.'
            }}
          </p>

          <ul v-if="annotations.length" class="annotation-list">
            <li v-for="a in annotations" :key="a.id" class="annotation-row">
              <button
                type="button"
                class="annotation-row-main"
                @click="revealAnnotation(a)"
              >
                <span class="annotation-row-meta">
                  <span
                    class="annotation-author"
                    :style="{ color: getUserColor(a.user_id) }"
                  >
                    {{ a.username }}
                  </span>
                  <span class="annotation-file">{{ a.file }}</span>
                </span>
                <span class="annotation-row-text">{{ a.text }}</span>
              </button>
              <button
                v-if="isHost"
                type="button"
                class="annotation-row-delete"
                title="Удалить пометку"
                aria-label="Удалить пометку"
                @click="removeAnnotation(a.id)"
              >
                ×
              </button>
            </li>
          </ul>
        </section>

        <div class="side-actions">
          <button v-if="isHost && !canEdit" @click="revokeEdit" class="btn btn-primary">Вернуть права</button>
          <button v-if="!isHost && hasRaisedHand" @click="lowerHand" class="btn btn-secondary">Опустить руку</button>
          <button v-if="!isHost && !hasRaisedHand && !canEdit" @click="raiseHand" class="btn btn-secondary">Поднять руку</button>
          <button v-if="!isHost && canEdit" @click="revokeEdit" class="btn btn-danger">Завершить редактирование</button>
        </div>
      </aside>
    </div>

    <div v-if="isResizing" class="resize-shield" aria-hidden="true"></div>

    <ParticipantMenu
      v-if="participantMenu"
      :participant="participantMenu.participant"
      :is-current-editor="
        participantMenu.participant.user_id === currentEditorId
      "
      :position="{ top: participantMenu.top, left: participantMenu.left }"
      :annotations-banned="
        annotationBans.includes(participantMenu.participant.user_id)
      "
      @grant="grantEditFromMenu"
      @revoke="revokeEditFromMenu"
      @kick="kickUserFromMenu"
      @toggle-ban="toggleAnnotationBanFromMenu"
      @close="closeParticipantMenu"
    />

    <FileActionDialog
      v-if="fileDialog"
      :mode="fileDialog.mode"
      :file-name="fileDialog.fileName"
      :error="fileDialogError"
      :busy="fileDialogBusy"
      :position="{ top: fileDialog.top, left: fileDialog.left }"
      @submit="submitFileDialog"
      @close="closeFileDialog"
    />

    <AnnotationPopup
      v-if="annotationPopup"
      :annotation="annotationPopup.annotation"
      :color="getUserColor(annotationPopup.annotation.user_id)"
      :is-host="isHost"
      :line-start="annotationPopup.lineStart"
      :line-end="annotationPopup.lineEnd"
      :position="{ top: annotationPopup.top, left: annotationPopup.left }"
      @close="closeAnnotationPopup"
      @remove="removeAnnotationFromPopup"
    />

    <div
      v-if="connectionStatus !== 'online'"
      class="room-overlay"
      role="status"
      aria-live="polite"
    >
      <div class="room-overlay-card">
        <span v-if="connectionStatus !== 'error'" class="spinner" aria-hidden="true"></span>
        <p class="room-overlay-text">
          {{ connectionStatus === 'reconnecting'
            ? 'Соединение потеряно. Переподключаемся…'
            : connectionStatus === 'error'
              ? connectError
              : 'Подключаемся к комнате…' }}
        </p>
        <RouterLink
          v-if="connectionStatus === 'error'"
          to="/"
          class="btn btn-ghost btn-sm"
        >
          На главную
        </RouterLink>
      </div>
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
  max-width: 320px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.room-id {
  color: var(--text-dim);
  font-family: var(--font-mono);
  font-size: 12px;
  max-width: 320px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.room-header-right {
  display: flex;
  align-items: center;
  gap: 14px;
  min-width: 0;
}

.invite-btn {
  flex: none;
  white-space: nowrap;
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
  background: var(--editor-bg);
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

.tabs-wrap {
  display: flex;
  flex: 1;
  align-items: center;
  gap: 6px;
  min-width: 0;
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

.tab-group {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  flex: none;
}

.tab-remove {
  flex: none;
  width: 20px;
  height: 26px;
  display: grid;
  place-items: center;
  padding: 0;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: var(--text-dim);
  font-size: 15px;
  line-height: 1;
  cursor: pointer;
  transition: background-color 0.16s ease, color 0.16s ease;
}

.tab-remove:hover {
  background: var(--danger-soft);
  color: var(--danger-text-hover);
}

.tab-add {
  flex: none;
  width: 28px;
  height: 30px;
  display: grid;
  place-items: center;
  padding: 0;
  border: 1px dashed var(--border-strong);
  border-radius: 7px;
  background: transparent;
  color: var(--text-muted);
  font-size: 17px;
  line-height: 1;
  cursor: pointer;
  transition: border-color 0.16s ease, color 0.16s ease,
    background-color 0.16s ease;
}

.tab-add:hover:not(:disabled) {
  border-color: var(--accent);
  background: var(--accent-soft);
  color: var(--accent);
}

.tab-add:disabled {
  opacity: 0.4;
  cursor: not-allowed;
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

.follow-toggle {
  flex: none;
  gap: 9px;
}

.follow-switch {
  position: relative;
  width: 26px;
  height: 15px;
  flex: none;
  border: 1px solid var(--border-strong);
  border-radius: 999px;
  background: var(--surface-3);
  transition: background-color 0.16s ease, border-color 0.16s ease;
}

.follow-switch::after {
  content: '';
  position: absolute;
  top: 50%;
  left: 2px;
  width: 9px;
  height: 9px;
  border-radius: 50%;
  background: var(--text-dim);
  transform: translateY(-50%);
  transition: transform 0.16s ease, background-color 0.16s ease;
}

.btn.follow-toggle.is-on,
.btn.follow-toggle.is-on:hover {
  background: var(--accent-soft);
  border-color: var(--accent-border);
  color: var(--accent);
}

.btn.follow-toggle.is-on .follow-switch {
  background: var(--accent);
  border-color: var(--accent);
}

.btn.follow-toggle.is-on .follow-switch::after {
  background: #fff;
  transform: translate(11px, -50%);
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
  min-height: 0;
  overflow: hidden;
  background: var(--bg-raised);
  border-left: 1px solid var(--border);
}

.preview-header {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  background: var(--surface);
  border-bottom: 1px solid var(--border);
  color: var(--text);
}

.preview-title {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-size: 12.5px;
  font-weight: 600;
}

.preview-header-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.preview-mode-tag {
  padding: 2px 6px;
  border-radius: 5px;
  background: var(--surface-3);
  color: var(--text-muted);
  font-size: 10.5px;
  font-weight: 600;
  letter-spacing: 0.02em;
}

.preview-mode-btn {
  padding: 3px 8px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: transparent;
  color: var(--text-muted);
  font-size: 11.5px;
  font-weight: 600;
  line-height: 1.2;
  white-space: nowrap;
  cursor: pointer;
  transition: background-color 0.16s ease, border-color 0.16s ease,
    color 0.16s ease;
}

.preview-mode-btn:hover {
  background: var(--surface-2);
  border-color: var(--border-strong);
  color: var(--text);
}

.preview-mode-btn.is-on {
  background: var(--accent-soft);
  border-color: var(--accent-border);
  color: var(--accent-strong);
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
  border: 1px solid var(--border);
  border-radius: 7px;
  background: transparent;
  color: var(--text-muted);
  font-size: 17px;
  line-height: 1;
  cursor: pointer;
  transition: background-color 0.16s ease, color 0.16s ease, border-color 0.16s ease;
}

.icon-btn:hover {
  background: var(--surface-2);
  border-color: var(--border-strong);
  color: var(--text);
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

.participant-hand {
  flex: none;
  width: 22px;
  height: 22px;
  display: grid;
  place-items: center;
  border: 1px solid var(--accent-border);
  border-radius: 7px;
  background: var(--accent-soft);
  color: var(--accent);
}

.participant-more {
  flex: none;
  width: 26px;
  height: 26px;
  display: grid;
  place-items: center;
  padding: 0;
  border: 1px solid transparent;
  border-radius: 7px;
  background: transparent;
  color: var(--text-dim);
  cursor: pointer;
  transition: background-color 0.16s ease, border-color 0.16s ease,
    color 0.16s ease;
}

.participant-more:hover,
.participant-more[aria-expanded='true'] {
  background: var(--surface-2);
  border-color: var(--border);
  color: var(--text);
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
  border: 1px solid var(--accent-border);
  border-radius: 5px;
  background: var(--accent-soft);
  color: var(--accent);
  font-size: 10.5px;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

.side-actions {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.side-actions .btn {
  width: 100%;
}

/* ===== Пометки на коде ===== */
.annotation-moderation {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 10px;
}

.annotation-moderation .btn.is-on,
.annotation-moderation .btn.is-on:hover {
  background: var(--accent-soft);
  border-color: var(--accent-border);
  color: var(--accent);
}

.annotation-moderation .annotation-clear-btn.is-confirming,
.annotation-moderation .annotation-clear-btn.is-confirming:hover {
  background: var(--danger-soft);
  border-color: rgba(229, 83, 61, 0.4);
  color: var(--danger-text-hover);
}

.annotation-message {
  margin: 0 0 10px;
}

.annotation-compose {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 12px;
}

.annotation-compose-excerpt {
  margin: 0;
  padding: 8px 10px;
  max-height: 96px;
  overflow: auto;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--bg-raised);
  color: var(--text-muted);
  font-family: var(--font-mono);
  font-size: 11.5px;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.annotation-textarea {
  min-height: 68px;
  padding: 9px 11px;
  font-size: 13px;
  resize: vertical;
}

.annotation-compose-actions {
  display: flex;
  gap: 8px;
}

.side-empty {
  margin: 0;
  color: var(--text-dim);
  font-size: 13px;
  line-height: 1.5;
}

.annotation-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.annotation-row {
  display: flex;
  align-items: flex-start;
  gap: 4px;
}

.annotation-row-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 3px;
  padding: 8px 9px;
  border: 1px solid var(--border);
  border-radius: 9px;
  background: var(--bg-raised);
  color: var(--text);
  text-align: left;
  cursor: pointer;
  transition: border-color 0.16s ease, background-color 0.16s ease;
}

.annotation-row-main:hover {
  border-color: var(--border-strong);
  background: var(--surface-2);
}

.annotation-row-meta {
  display: flex;
  align-items: baseline;
  gap: 8px;
  min-width: 0;
}

.annotation-author {
  overflow: hidden;
  font-size: 12px;
  font-weight: 700;
  white-space: nowrap;
  text-overflow: ellipsis;
}

.annotation-file {
  margin-left: auto;
  flex: none;
  color: var(--text-dim);
  font-family: var(--font-mono);
  font-size: 10.5px;
}

.annotation-row-text {
  display: -webkit-box;
  overflow: hidden;
  color: var(--text-muted);
  font-size: 12.5px;
  line-height: 1.45;
  overflow-wrap: anywhere;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 3;
}

.annotation-row-delete {
  flex: none;
  width: 24px;
  height: 24px;
  display: grid;
  place-items: center;
  padding: 0;
  border: 1px solid transparent;
  border-radius: 7px;
  background: transparent;
  color: var(--text-dim);
  font-size: 16px;
  line-height: 1;
  cursor: pointer;
  transition: background-color 0.16s ease, border-color 0.16s ease,
    color 0.16s ease;
}

.annotation-row-delete:hover {
  background: var(--danger-soft);
  border-color: rgba(229, 83, 61, 0.35);
  color: var(--danger-text-hover);
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

.resize-shield {
  position: fixed;
  inset: 0;
  z-index: 40;
  cursor: col-resize;
}

.room-overlay {
  position: fixed;
  inset: 0;
  z-index: 50;
  display: grid;
  place-items: center;
  background: var(--overlay);
}

.room-overlay-card {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 16px 20px;
  border: 1px solid var(--border);
  border-radius: 12px;
  background: var(--surface);
  box-shadow: var(--shadow);
}

.room-overlay-card .spinner {
  color: var(--accent);
}

.room-overlay-text {
  color: var(--text-muted);
  font-size: 14px;
}
</style>
