<script setup>
import {
  computed,
  onBeforeUnmount,
  onMounted,
  reactive,
  ref,
  watch
} from 'vue'
import PreviewDevTools from './PreviewDevTools.vue'
import {
  buildPreviewDocument,
  externalTitle,
  isHtmlFile,
  isSafeExternalUrl,
  pickHtmlFile,
  resolvePreviewReference
} from '../utils/previewDocument.js'

const props = defineProps({
  files: {
    type: Object,
    required: true
  },
  shellUrl: {
    type: String,
    required: true
  },
  startFile: {
    type: String,
    default: ''
  },
  startPage: {
    type: Object,
    default: null
  },
  interactionMode: {
    type: String,
    default: 'off'
  },
  readonly: {
    type: Boolean,
    default: false
  },
  shared: {
    type: Boolean,
    default: false
  },
  initialEvents: {
    type: Array,
    default: () => []
  }
})

const emit = defineEmits(['interaction', 'navigate', 'open-file'])

const REBUILD_DELAY = 600
const MAX_LOGS = 400
const MAX_NETWORK = 200

const tabs = ref([])
const activeTabId = ref('')
const frames = new Map()
const frameSetters = new Map()
const devtoolsOpen = ref(false)
const devtoolsPanel = ref('console')
const addressValue = ref('')
const addressFocused = ref(false)

let tabCounter = 0
let entryCounter = 0
let evalCounter = 0
let rebuildTimer = null
let domTimer = null

const activeTab = computed(
  () => tabs.value.find((tab) => tab.id === activeTabId.value) || null
)

const htmlFiles = computed(() =>
  Object.keys(props.files || {}).filter((name) => isHtmlFile(name))
)

const canAddTab = computed(() => !props.readonly && !props.shared)
const canCloseTab = computed(() => !props.readonly && tabs.value.length > 1)

const canGoBack = computed(
  () => Boolean(activeTab.value && activeTab.value.historyIndex > 0)
)

const canGoForward = computed(() => {
  const tab = activeTab.value
  return Boolean(
    tab &&
      tab.historyIndex >= 0 &&
      tab.historyIndex < tab.history.length - 1
  )
})

function hasFile(name) {
  return Boolean(
    name && Object.prototype.hasOwnProperty.call(props.files || {}, name)
  )
}

function frameSrc(tab) {
  const separator = props.shellUrl.includes('?') ? '&' : '?'
  return `${props.shellUrl}${separator}tab=${encodeURIComponent(tab.id)}`
}

function frameRef(tab) {
  let setter = frameSetters.get(tab.id)
  if (!setter) {
    setter = (element) => setTabFrame(tab.id, element)
    frameSetters.set(tab.id, setter)
  }
  return setter
}

function setTabFrame(id, element) {
  if (element) frames.set(id, element)
  else frames.delete(id)
}

function applyTarget(tab, target) {
  const kind = target?.kind || 'start'

  if (kind === 'file') {
    tab.kind = 'file'
    tab.file = target.file || ''
    tab.hash = target.hash || ''
    tab.url = `/${tab.file}${tab.hash || ''}`
    tab.title = target.title || tab.file
    tab.reason = ''
    return
  }

  if (kind === 'external') {
    tab.kind = 'external'
    tab.file = ''
    tab.hash = ''
    tab.url = target.url || ''
    tab.title = target.title || externalTitle(target.url)
    tab.reason = ''
    return
  }

  if (kind === 'asset') {
    tab.kind = 'asset'
    tab.file = target.file || ''
    tab.hash = ''
    tab.url = tab.file ? `/${tab.file}` : ''
    tab.title = tab.file || 'Файл'
    tab.reason = target.reason || ''
    return
  }

  if (kind === 'error') {
    tab.kind = 'error'
    tab.file = ''
    tab.hash = ''
    tab.url = target.url || ''
    tab.title = target.title || 'Не найдено'
    tab.reason = target.reason || 'Страница не найдена.'
    return
  }

  tab.kind = 'start'
  tab.file = ''
  tab.hash = ''
  tab.url = ''
  tab.title = 'Новая вкладка'
  tab.reason = ''
}

function historyEntry(tab) {
  return {
    kind: tab.kind,
    file: tab.file,
    url: tab.url,
    title: tab.title,
    pageTitle: tab.pageTitle,
    hash: tab.hash,
    reason: tab.reason
  }
}

function recordHistory(tab, push) {
  const entry = historyEntry(tab)
  if (push || tab.historyIndex < 0) {
    tab.history = tab.history.slice(0, tab.historyIndex + 1)
    tab.history.push(entry)
    tab.historyIndex = tab.history.length - 1
    return
  }
  tab.history[tab.historyIndex] = entry
}

function createTab(target = {}, options = {}) {
  const { activate = true, push = true } = options
  tabCounter += 1

  const tab = reactive({
    id: `pt${Date.now().toString(36)}${tabCounter}`,
    kind: 'start',
    file: '',
    url: '',
    title: 'Новая вкладка',
    pageTitle: '',
    hash: '',
    reason: '',
    history: [],
    historyIndex: -1,
    logs: [],
    network: [],
    dom: null,
    domLoading: false,
    docId: 0,
    html: '',
    ready: false,
    pendingEvents: [],
    unreadErrors: 0
  })

  tabs.value.push(tab)
  applyTarget(tab, target)
  recordHistory(tab, push)

  if (activate) activeTabId.value = tab.id

  if (tab.kind === 'file') buildTab(tab)

  syncAddress()
  return tab
}

function buildTab(tab) {
  if (!tab || tab.kind !== 'file') return

  tab.docId += 1
  tab.html = buildPreviewDocument(props.files, tab.file, {
    tabId: tab.id,
    docId: tab.docId,
    interactionMode: props.interactionMode,
    initialHash: tab.hash
  })
  tab.ready = false
  tab.dom = null
  postTabHtml(tab)
}

function postTabHtml(tab) {
  const frame = frames.get(tab.id)
  if (!frame?.contentWindow) return

  tab.ready = false
  frame.contentWindow.postMessage(
    { type: 'preview-html', html: tab.html },
    '*'
  )
}

function onShellReady(tabId) {
  const tab = tabs.value.find((item) => item.id === tabId)
  if (!tab || tab.kind !== 'file') return

  if (!tab.html) buildTab(tab)
  else postTabHtml(tab)
}

function isActive(tab) {
  return Boolean(tab && tab.id === activeTabId.value)
}

function emitNavigation(tab) {
  if (!tab || !props.shared || props.readonly) return
  if (props.interactionMode !== 'capture') return

  if (tab.kind === 'file') {
    emit('navigate', { kind: 'file', file: tab.file })
    return
  }

  if (tab.kind === 'external' && isSafeExternalUrl(tab.url)) {
    emit('navigate', { kind: 'external', url: tab.url })
  }
}

function navigateTab(tab, target, options = {}) {
  if (!tab || !target) return

  const { push = true, emitNav = true, clearLogs = true } = options

  applyTarget(tab, target)

  if (clearLogs) {
    tab.logs = []
    tab.network = []
    tab.unreadErrors = 0
  }

  tab.pageTitle = ''
  tab.ready = false
  tab.dom = null
  tab.pendingEvents = []

  recordHistory(tab, push)
  syncAddress()

  if (tab.kind === 'file') buildTab(tab)

  if (emitNav && isActive(tab)) emitNavigation(tab)
}

function activateTab(id) {
  if (props.readonly || !id || id === activeTabId.value) return

  const tab = tabs.value.find((item) => item.id === id)
  if (!tab) return

  activeTabId.value = id
  syncAddress(true)

  if (tab.kind === 'file' && !tab.html) buildTab(tab)

  emitNavigation(tab)
}

function closeTab(id) {
  if (props.readonly) return

  const index = tabs.value.findIndex((tab) => tab.id === id)
  if (index < 0) return

  const wasActive = tabs.value[index].id === activeTabId.value

  tabs.value.splice(index, 1)
  frames.delete(id)
  frameSetters.delete(id)

  if (!tabs.value.length) {
    createTab({ kind: 'start' })
    return
  }

  if (wasActive) {
    const next = tabs.value[Math.min(index, tabs.value.length - 1)]
    activeTabId.value = next.id
    syncAddress(true)
    emitNavigation(next)
  }
}

function addStartTab() {
  if (props.readonly) return
  createTab({ kind: 'start' }, { activate: true })
}

function travel(delta) {
  const tab = activeTab.value
  if (!tab || props.readonly) return

  const nextIndex = tab.historyIndex + delta
  if (nextIndex < 0 || nextIndex >= tab.history.length) return

  tab.historyIndex = nextIndex
  const entry = tab.history[nextIndex]

  applyTarget(tab, entry)
  tab.pageTitle = entry.pageTitle || ''
  tab.ready = false
  tab.dom = null
  tab.pendingEvents = []
  tab.logs = []
  tab.network = []
  tab.unreadErrors = 0

  syncAddress(true)

  if (tab.kind === 'file') buildTab(tab)

  emitNavigation(tab)
}

function reload() {
  const tab = activeTab.value
  if (!tab) return

  if (tab.kind === 'file') {
    tab.logs = []
    tab.network = []
    tab.unreadErrors = 0
    tab.pageTitle = ''
    buildTab(tab)
    return
  }

  if (tab.kind === 'start' || tab.kind === 'error' || tab.kind === 'asset') {
    tab.logs = []
    tab.network = []
    tab.unreadErrors = 0
  }
}

function syncAddress(force = false) {
  if (addressFocused.value && !force) return
  const tab = activeTab.value
  addressValue.value = tab ? tab.url : ''
}

function onAddressBlur() {
  addressFocused.value = false
  syncAddress(true)
}

function resolveAddress(value) {
  if (/^https?:\/\//i.test(value)) {
    return isSafeExternalUrl(value)
      ? { kind: 'external', url: value }
      : { kind: 'error', title: value, url: value, reason: 'Некорректный адрес.' }
  }

  const resolved = resolvePreviewReference(props.files, value)
  if (resolved.kind === 'file') {
    return resolved.isHtml
      ? { kind: 'file', file: resolved.file, hash: resolved.hash }
      : {
          kind: 'asset',
          file: resolved.file,
          reason: 'Это не HTML-страница. Откройте файл в редакторе.'
        }
  }

  if (resolved.kind === 'external') {
    return { kind: 'external', url: resolved.url }
  }

  if (resolved.kind === 'hash') return resolved

  if (resolved.kind === 'missing') {
    return {
      kind: 'error',
      title: resolved.path,
      url: `/${resolved.path}`,
      reason: `Файл «${resolved.path}» не найден в комнате.`
    }
  }

  return null
}

function submitAddress() {
  if (props.readonly) return

  const tab = activeTab.value
  if (!tab) return

  const value = addressValue.value.trim()

  if (!value || value === 'peerlessons://newtab') {
    // В общем режиме нельзя увести всех на локальную стартовую страницу.
    if (props.shared) return
    navigateTab(tab, { kind: 'start' }, { emitNav: false })
    return
  }

  const target = resolveAddress(value)
  if (!target) return

  if (target.kind === 'hash') {
    sendCommand(tab, { type: 'hash', hash: target.hash })
    return
  }

  navigateTab(tab, target, { emitNav: true })
}

function isNewTabTarget(target) {
  const value = String(target || '').toLowerCase()
  if (value === '_blank') return true
  return Boolean(
    value &&
      value !== '_self' &&
      value !== '_top' &&
      value !== '_parent'
  )
}

function openTarget(tab, target, newTab) {
  if (newTab) {
    const created = createTab(target, { activate: true })
    emitNavigation(created)
    return
  }

  navigateTab(tab, target, { emitNav: true })
}

function handleRuntimeNavigation(tab, data) {
  const resolved = resolvePreviewReference(props.files, data.href)
  if (!resolved || resolved.kind === 'ignore') return

  if (resolved.kind === 'self') {
    navigateTab(tab, { kind: 'file', file: tab.file, hash: tab.hash }, { emitNav: true })
    return
  }

  if (resolved.kind === 'hash') {
    sendCommand(tab, { type: 'hash', hash: resolved.hash })
    return
  }

  let target
  if (resolved.kind === 'file') {
    target = resolved.isHtml
      ? { kind: 'file', file: resolved.file, hash: resolved.hash }
      : {
          kind: 'asset',
          file: resolved.file,
          reason: 'Это не HTML-страница. Откройте файл в редакторе.'
        }
  } else if (resolved.kind === 'external') {
    target = { kind: 'external', url: resolved.url }
  } else {
    target = {
      kind: 'error',
      title: resolved.path,
      url: `/${resolved.path}`,
      reason: `Файл «${resolved.path}» не найден в комнате.`
    }
  }

  openTarget(tab, target, data.newTab || isNewTabTarget(data.target))
}

function openTargetInActive(target) {
  const tab = activeTab.value
  if (!tab || props.readonly) return
  navigateTab(tab, target, { emitNav: true })
}

function openExternal(url) {
  if (!isSafeExternalUrl(url)) return
  window.open(url, '_blank', 'noopener,noreferrer')
}

function displayTitle(tab) {
  if (!tab) return ''

  if (tab.kind === 'file') return tab.pageTitle || tab.file
  if (tab.kind === 'start') return 'Новая вкладка'
  if (tab.kind === 'asset') return tab.file || 'Файл'
  if (tab.kind === 'error') return tab.title || 'Не найдено'
  return tab.title || externalTitle(tab.url)
}

function tabTitle(tab) {
  if (!tab) return ''
  return tab.url ? `${displayTitle(tab)} — ${tab.url}` : displayTitle(tab)
}

function pushLog(tab, level, text) {
  const allowed = ['log', 'info', 'warn', 'error', 'input', 'result']
  const kind = allowed.includes(level) ? level : 'log'
  const value = String(text == null ? '' : text)

  entryCounter += 1
  tab.logs.push({
    id: entryCounter,
    level: kind,
    text: value.slice(0, 6000),
    time: Date.now()
  })

  if (tab.logs.length > MAX_LOGS) {
    tab.logs.splice(0, tab.logs.length - MAX_LOGS)
  }

  if (kind === 'error') tab.unreadErrors += 1
}

function pushNetwork(tab, entry) {
  if (!entry) return

  entryCounter += 1
  tab.network.push({
    id: entryCounter,
    method: String(entry.method || 'GET').slice(0, 12),
    url: String(entry.url || '').slice(0, 2048),
    status: Number(entry.status) || 0,
    ok: Boolean(entry.ok),
    duration: Math.max(0, Math.round(Number(entry.duration) || 0)),
    error: entry.error ? String(entry.error).slice(0, 300) : ''
  })

  if (tab.network.length > MAX_NETWORK) {
    tab.network.splice(0, tab.network.length - MAX_NETWORK)
  }
}

function sendReplay(tab, event) {
  const frame = frames.get(tab.id)
  if (!frame?.contentWindow) return
  frame.contentWindow.postMessage({ type: 'preview-event', event }, '*')
}

function flushPending(tab) {
  if (!tab.pendingEvents.length) return
  const events = tab.pendingEvents.splice(0)
  for (const detail of events) sendReplay(tab, detail)
}

function replay(event) {
  const tab = activeTab.value
  if (!tab || tab.kind !== 'file' || !event) return

  if (tab.ready) {
    sendReplay(tab, event)
    return
  }

  tab.pendingEvents.push(event)
  if (tab.pendingEvents.length > 300) tab.pendingEvents.shift()
}

// Пересобирает активную страницу с чистого листа и проигрывает журнал
// взаимодействий — используется при переподключении к комнате.
function reloadWithEvents(events) {
  const tab = activeTab.value
  if (!tab) return

  if (tab.kind === 'file') {
    tab.logs = []
    tab.network = []
    tab.unreadErrors = 0
    tab.pageTitle = ''
    tab.pendingEvents = []
    buildTab(tab)
  }

  for (const event of Array.isArray(events) ? events : []) replay(event)
}

function sendCommand(tab, command) {
  if (!tab || tab.kind !== 'file') return false

  const frame = frames.get(tab.id)
  if (!frame?.contentWindow) return false

  frame.contentWindow.postMessage(
    { type: 'preview-command', command },
    '*'
  )
  return true
}

function onMessage(event) {
  const data = event.data
  if (!data || typeof data !== 'object') return

  // Сигнал оболочки конкретной вкладки.
  if (data.type === 'preview-ready') {
    let tabId = typeof data.tab === 'string' ? data.tab : ''

    // Запасной путь: если оболочка не смогла прочитать свой query,
    // определяем вкладку по окну-источнику.
    if (!tabId) {
      for (const [id, frame] of frames.entries()) {
        if (frame.contentWindow === event.source) {
          tabId = id
          break
        }
      }
    }

    if (tabId) onShellReady(tabId)
    return
  }

  if (data.source !== 'peerlessons-preview') return

  const tab = tabs.value.find((item) => item.id === data.tab)
  if (!tab) return

  if (data.doc !== undefined && Number(data.doc) !== tab.docId) return

  if (data.action === 'ready') {
    if (typeof data.title === 'string' && data.title) {
      tab.pageTitle = data.title
    }
    tab.ready = true
    flushPending(tab)
    return
  }

  if (data.action === 'title') {
    if (typeof data.title === 'string') tab.pageTitle = data.title
    return
  }

  if (data.action === 'console') {
    pushLog(tab, data.level, data.text)
    return
  }

  if (data.action === 'network') {
    pushNetwork(tab, data.entry)
    return
  }

  if (data.action === 'eval-result') {
    pushLog(tab, data.ok ? 'result' : 'error', data.text)
    return
  }

  if (data.action === 'dom') {
    tab.dom = data.root || null
    tab.domLoading = false
    if (domTimer) {
      clearTimeout(domTimer)
      domTimer = null
    }
    return
  }

  if (data.action === 'navigate') {
    handleRuntimeNavigation(tab, data)
    return
  }

  if (data.action === 'interaction') {
    if (props.shared && props.interactionMode === 'capture' && data.event) {
      emit('interaction', data.event)
    }
  }
}

function rebuildOpenPages() {
  for (const tab of tabs.value) {
    if (tab.kind !== 'file') continue

    if (!hasFile(tab.file)) {
      if (isActive(tab)) {
        const fallback = pickHtmlFile(props.files)
        if (fallback) {
          navigateTab(tab, { kind: 'file', file: fallback }, {
            emitNav: false,
            push: false,
            clearLogs: false
          })
          continue
        }
      }

      const missing = tab.file
      applyTarget(tab, {
        kind: 'error',
        title: missing || 'Не найдено',
        url: `/${missing}`,
        reason: `Файл «${missing}» больше не существует.`
      })
      tab.pageTitle = ''
      tab.ready = false
      tab.pendingEvents = []
      tab.dom = null
      continue
    }

    tab.pendingEvents = []
    buildTab(tab)
  }
}

function scheduleRebuild() {
  if (rebuildTimer) clearTimeout(rebuildTimer)
  rebuildTimer = setTimeout(() => {
    rebuildTimer = null
    rebuildOpenPages()
  }, REBUILD_DELAY)
}

function evalInActive(code) {
  const tab = activeTab.value
  if (!tab || !code || props.readonly) return

  if (tab.kind !== 'file') {
    pushLog(tab, 'warn', 'Консоль доступна только для HTML-страниц.')
    return
  }

  pushLog(tab, 'input', code)

  if (!tab.ready) {
    pushLog(tab, 'warn', 'Страница ещё загружается — попробуйте ещё раз.')
    return
  }

  evalCounter += 1
  sendCommand(tab, {
    type: 'eval',
    code,
    requestId: `ev-${evalCounter}`
  })
}

function requestDom() {
  const tab = activeTab.value
  if (!tab || tab.kind !== 'file') return

  if (!tab.ready) {
    tab.dom = null
    tab.domLoading = false
    return
  }

  tab.domLoading = true
  sendCommand(tab, { type: 'dom', requestId: `dom-${Date.now()}` })

  if (domTimer) clearTimeout(domTimer)
  domTimer = setTimeout(() => {
    domTimer = null
    tab.domLoading = false
  }, 1500)
}

function highlightNode(path) {
  const tab = activeTab.value
  if (!tab || tab.kind !== 'file' || !tab.ready) return
  sendCommand(tab, { type: 'highlight', path: path || '' })
}

function clearLogs() {
  const tab = activeTab.value
  if (!tab) return
  tab.logs = []
  tab.unreadErrors = 0
}

function clearNetwork() {
  const tab = activeTab.value
  if (tab) tab.network = []
}

function toggleDevtools() {
  devtoolsOpen.value = !devtoolsOpen.value

  if (devtoolsOpen.value) {
    if (activeTab.value) activeTab.value.unreadErrors = 0
    if (devtoolsPanel.value === 'elements') requestDom()
  }
}

function normalizeStartPage(page, startFile) {
  if (page) {
    if (page.kind === 'file' && isHtmlFile(page.file) && hasFile(page.file)) {
      return { kind: 'file', file: page.file }
    }

    if (page.kind === 'external' && isSafeExternalUrl(page.url)) {
      return {
        kind: 'external',
        url: page.url,
        title: externalTitle(page.url)
      }
    }
  }

  const file = pickHtmlFile(props.files, startFile)
  return file ? { kind: 'file', file } : { kind: 'start' }
}

function applyRemotePage(page) {
  if (!page) return

  const tab = activeTab.value
  if (!tab) return

  if (page.kind === 'file' && isHtmlFile(page.file) && hasFile(page.file)) {
    if (tab.kind === 'file' && tab.file === page.file) return
    navigateTab(tab, { kind: 'file', file: page.file }, {
      emitNav: false,
      push: false
    })
    return
  }

  if (page.kind === 'external' && isSafeExternalUrl(page.url)) {
    if (tab.kind === 'external' && tab.url === page.url) return
    navigateTab(tab, { kind: 'external', url: page.url }, {
      emitNav: false,
      push: false
    })
  }
}

function openFile(file, options = {}) {
  if (!file || !isHtmlFile(file) || !hasFile(file)) return

  const tab = activeTab.value
  if (!tab) return
  if (tab.kind === 'file' && tab.file === file) return

  navigateTab(tab, { kind: 'file', file }, {
    emitNav: options.emit !== false,
    push: options.push !== false
  })
}

watch(
  () => props.files,
  () => scheduleRebuild(),
  { deep: true }
)

watch(
  () => props.interactionMode,
  () => rebuildOpenPages()
)

watch(activeTabId, () => {
  syncAddress(true)

  if (devtoolsOpen.value) {
    if (activeTab.value) activeTab.value.unreadErrors = 0
    if (devtoolsPanel.value === 'elements') requestDom()
  }
})

watch(
  () => activeTab.value?.url,
  () => syncAddress()
)

onMounted(() => {
  window.addEventListener('message', onMessage)

  const page = normalizeStartPage(props.startPage, props.startFile)
  const tab = createTab(page, { activate: true })

  tab.pendingEvents = Array.isArray(props.initialEvents)
    ? [...props.initialEvents]
    : []

  syncAddress(true)
})

onBeforeUnmount(() => {
  window.removeEventListener('message', onMessage)
  if (rebuildTimer) clearTimeout(rebuildTimer)
  if (domTimer) clearTimeout(domTimer)
  frames.clear()
  frameSetters.clear()
})

defineExpose({
  refresh: reload,
  replay,
  applyRemotePage,
  openFile,
  reloadWithEvents,
  getActiveFile: () =>
    activeTab.value?.kind === 'file' ? activeTab.value.file : '',
  getActivePage: () => {
    const tab = activeTab.value
    if (!tab) return null
    if (tab.kind === 'file' && tab.file) {
      return { kind: 'file', file: tab.file }
    }
    if (tab.kind === 'external' && isSafeExternalUrl(tab.url)) {
      return { kind: 'external', url: tab.url }
    }
    return null
  }
})
</script>

<template>
  <div class="mini-browser" :class="{ 'is-readonly': readonly }">
    <div class="mini-tabs" role="tablist" aria-label="Страницы превью">
      <div v-for="tab in tabs" :key="tab.id" class="mini-tab-slot">
        <button
          type="button"
          role="tab"
          :aria-selected="tab.id === activeTabId"
          :class="[
            'mini-tab',
            `is-${tab.kind}`,
            { active: tab.id === activeTabId }
          ]"
          :title="tabTitle(tab)"
          @click="activateTab(tab.id)"
        >
          <span class="mini-favicon" aria-hidden="true"></span>
          <span class="mini-tab-title">{{ displayTitle(tab) }}</span>
        </button>
        <button
          v-if="canCloseTab"
          type="button"
          class="mini-tab-close"
          :aria-label="`Закрыть ${displayTitle(tab)}`"
          title="Закрыть вкладку"
          @click.stop="closeTab(tab.id)"
        >
          ×
        </button>
      </div>

      <button
        v-if="canAddTab"
        type="button"
        class="mini-tab-add"
        title="Новая вкладка"
        aria-label="Новая вкладка"
        @click="addStartTab"
      >
        +
      </button>
    </div>

    <div class="mini-address">
      <button
        type="button"
        class="mini-nav-btn"
        :disabled="readonly || !canGoBack"
        title="Назад"
        aria-label="Назад"
        @click="travel(-1)"
      >
        ←
      </button>
      <button
        type="button"
        class="mini-nav-btn"
        :disabled="readonly || !canGoForward"
        title="Вперёд"
        aria-label="Вперёд"
        @click="travel(1)"
      >
        →
      </button>
      <button
        type="button"
        class="mini-nav-btn"
        :disabled="readonly"
        title="Обновить"
        aria-label="Обновить"
        @click="reload"
      >
        ⟳
      </button>

      <form class="mini-url" @submit.prevent="submitAddress">
        <span
          class="mini-url-icon"
          :class="{ external: activeTab?.kind === 'external' }"
          aria-hidden="true"
        ></span>
        <input
          v-model="addressValue"
          class="mini-url-input"
          :readonly="readonly"
          spellcheck="false"
          autocomplete="off"
          aria-label="Адрес страницы"
          placeholder="/index.html"
          @focus="addressFocused = true"
          @blur="onAddressBlur"
        />
      </form>

      <button
        type="button"
        class="mini-tool-btn"
        :class="{ active: devtoolsOpen }"
        :title="
          devtoolsOpen
            ? 'Скрыть панель разработчика'
            : 'Панель разработчика: консоль, элементы, сеть'
        "
        aria-label="Панель разработчика"
        @click="toggleDevtools"
      >
        <svg
          viewBox="0 0 24 24"
          width="13"
          height="13"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
          stroke-linecap="round"
          stroke-linejoin="round"
          aria-hidden="true"
        >
          <path d="m4 17 6-6-6-6" />
          <path d="M12 19h8" />
        </svg>
        <span
          v-if="activeTab?.unreadErrors"
          class="mini-error-badge"
        >
          {{ activeTab.unreadErrors }}
        </span>
      </button>
    </div>

    <div class="mini-stage">
      <div
        v-for="tab in tabs"
        v-show="tab.id === activeTabId"
        :key="tab.id"
        class="mini-page"
      >
        <iframe
          v-if="tab.kind === 'file'"
          :ref="frameRef(tab)"
          :src="frameSrc(tab)"
          class="mini-frame"
          sandbox="allow-scripts allow-modals allow-forms"
          referrerpolicy="no-referrer"
          :tabindex="readonly ? -1 : 0"
          :title="`Превью ${tab.file}`"
        ></iframe>

        <div v-else-if="tab.kind === 'start'" class="mini-start">
          <p class="mini-start-title">Новая вкладка</p>

          <template v-if="htmlFiles.length">
            <p class="mini-start-hint">
              Откройте HTML-страницу комнаты:
            </p>
            <div class="mini-start-grid">
              <button
                v-for="file in htmlFiles"
                :key="file"
                type="button"
                class="mini-start-card"
                @click="openTargetInActive({ kind: 'file', file })"
              >
                <span class="mini-start-card-icon" aria-hidden="true"></span>
                <span class="mini-start-card-name">{{ file }}</span>
              </button>
            </div>
          </template>

          <p v-else class="mini-start-hint">
            В комнате пока нет HTML-файлов.
          </p>
        </div>

        <div v-else-if="tab.kind === 'external'" class="mini-panel">
          <div class="mini-panel-card">
            <p class="mini-panel-kicker">Внешняя ссылка</p>
            <p class="mini-panel-url">{{ tab.url }}</p>
            <p class="mini-panel-note">
              Сторонние сайты обычно запрещают встраивание в iframe.
              Откройте адрес в отдельной вкладке браузера.
            </p>
            <button
              type="button"
              class="btn btn-secondary btn-sm"
              @click="openExternal(tab.url)"
            >
              Открыть сайт
            </button>
          </div>
        </div>

        <div v-else-if="tab.kind === 'asset'" class="mini-panel">
          <div class="mini-panel-card">
            <p class="mini-panel-kicker">Файл комнаты</p>
            <p class="mini-panel-url">{{ tab.file }}</p>
            <p class="mini-panel-note">
              Это не HTML-страница, поэтому она не отображается
              в превью.
            </p>
            <button
              type="button"
              class="btn btn-secondary btn-sm"
              @click="emit('open-file', tab.file)"
            >
              Открыть в редакторе
            </button>
          </div>
        </div>

        <div v-else class="mini-panel">
          <div class="mini-panel-card">
            <p class="mini-panel-kicker">Не удалось открыть страницу</p>
            <p class="mini-panel-note">{{ tab.reason }}</p>
            <button
              v-if="tab.url && htmlFiles.length"
              type="button"
              class="btn btn-ghost btn-sm"
              @click="openTargetInActive({ kind: 'file', file: pickHtmlFile(props.files) })"
            >
              На главную
            </button>
          </div>
        </div>
      </div>

      <div
        v-if="readonly && activeTab?.kind === 'file'"
        class="mini-shield"
        aria-hidden="true"
      ></div>
    </div>

    <PreviewDevTools
      v-if="devtoolsOpen"
      v-model:panel="devtoolsPanel"
      :logs="activeTab?.logs || []"
      :network="activeTab?.network || []"
      :dom="activeTab?.dom || null"
      :dom-loading="activeTab?.domLoading || false"
      :locked="readonly"
      @eval="evalInActive"
      @refresh-dom="requestDom"
      @highlight="highlightNode"
      @clear-logs="clearLogs"
      @clear-network="clearNetwork"
      @close="devtoolsOpen = false"
    />
  </div>
</template>

<style scoped>
.mini-browser {
  flex: 1 1 auto;
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
  background: var(--bg-raised);
}

/* ===== Вкладки ===== */

.mini-tabs {
  flex-shrink: 0;
  display: flex;
  align-items: flex-end;
  gap: 3px;
  padding: 6px 6px 0;
  overflow-x: auto;
  overflow-y: hidden;
  background: var(--bg-raised);
  border-bottom: 1px solid var(--border);
  scrollbar-width: thin;
}

.mini-tab-slot {
  display: flex;
  align-items: center;
  min-width: 0;
}

.mini-tab {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
  max-width: 160px;
  padding: 5px 8px;
  border: 1px solid var(--border);
  border-bottom: 0;
  border-radius: 7px 7px 0 0;
  background: var(--surface);
  color: var(--text-muted);
  font-size: 11.5px;
  font-weight: 500;
  white-space: nowrap;
  cursor: pointer;
  transition: background-color 0.16s ease, color 0.16s ease,
    border-color 0.16s ease;
}

.mini-tab:hover {
  background: var(--surface-2);
  color: var(--text);
}

.mini-tab.active {
  background: var(--surface-2);
  border-color: var(--border-strong);
  color: var(--text);
  box-shadow: inset 0 2px 0 var(--accent);
}

.mini-tab-title {
  overflow: hidden;
  text-overflow: ellipsis;
}

.mini-favicon {
  flex-shrink: 0;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--text-dim);
}

.mini-tab.is-file .mini-favicon {
  background: var(--accent);
}

.mini-tab.is-external .mini-favicon {
  background: #6aa8ff;
}

.mini-tab.is-error .mini-favicon {
  background: var(--danger);
}

.mini-tab.is-asset .mini-favicon {
  background: var(--success);
}

.mini-tab-close {
  flex-shrink: 0;
  width: 18px;
  height: 18px;
  display: grid;
  place-items: center;
  margin-left: 1px;
  padding: 0;
  border: 0;
  border-radius: 4px;
  background: transparent;
  color: var(--text-dim);
  font-size: 13px;
  line-height: 1;
  cursor: pointer;
}

.mini-tab-close:hover {
  background: var(--danger-soft);
  color: var(--danger-text);
}

.mini-tab-add {
  flex-shrink: 0;
  width: 22px;
  height: 22px;
  display: grid;
  place-items: center;
  margin: 0 2px 3px;
  padding: 0;
  border: 1px solid transparent;
  border-radius: 6px;
  background: transparent;
  color: var(--text-dim);
  font-size: 16px;
  line-height: 1;
  cursor: pointer;
  transition: background-color 0.16s ease, color 0.16s ease;
}

.mini-tab-add:hover {
  background: var(--surface-2);
  color: var(--text);
}

/* ===== Адресная строка ===== */

.mini-address {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 3px;
  padding: 5px 6px;
  background: var(--bg-raised);
  border-bottom: 1px solid var(--border);
}

.mini-nav-btn {
  flex-shrink: 0;
  width: 24px;
  height: 24px;
  display: grid;
  place-items: center;
  padding: 0;
  border: 0;
  border-radius: 5px;
  background: transparent;
  color: var(--text-muted);
  font-size: 13px;
  line-height: 1;
  cursor: pointer;
  transition: background-color 0.16s ease, color 0.16s ease;
}

.mini-nav-btn:hover:not(:disabled) {
  background: var(--surface-2);
  color: var(--text);
}

.mini-nav-btn:disabled {
  opacity: 0.35;
  cursor: default;
}

.mini-url {
  flex: 1 1 auto;
  display: flex;
  align-items: center;
  gap: 5px;
  min-width: 0;
  margin: 0 3px;
  padding: 0 6px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--surface);
}

.mini-url:focus-within {
  border-color: var(--accent-border);
  background: var(--input-focus-bg);
}

.mini-url-icon {
  flex-shrink: 0;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--accent);
}

.mini-url-icon.external {
  background: #6aa8ff;
}

.mini-url-input {
  flex: 1 1 auto;
  min-width: 0;
  padding: 4px 0;
  border: 0;
  background: transparent;
  color: var(--text);
  font-family: var(--font-mono);
  font-size: 11px;
  outline: none;
}

.mini-url-input::placeholder {
  color: var(--placeholder);
}

.mini-url-input:read-only {
  color: var(--text-muted);
  cursor: default;
}

.mini-tool-btn {
  position: relative;
  flex-shrink: 0;
  width: 26px;
  height: 24px;
  display: grid;
  place-items: center;
  padding: 0;
  border: 1px solid transparent;
  border-radius: 6px;
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
  transition: background-color 0.16s ease, color 0.16s ease,
    border-color 0.16s ease;
}

.mini-tool-btn:hover {
  background: var(--surface-2);
  color: var(--text);
}

.mini-tool-btn.active {
  background: var(--accent-soft);
  border-color: var(--accent-border);
  color: var(--accent-strong);
}

.mini-error-badge {
  position: absolute;
  top: -4px;
  right: -4px;
  min-width: 14px;
  padding: 0 3px;
  border-radius: 999px;
  background: var(--danger);
  color: #fff;
  font-size: 8.5px;
  font-weight: 700;
  line-height: 14px;
  text-align: center;
}

/* ===== Сцена ===== */

.mini-stage {
  position: relative;
  flex: 1 1 auto;
  min-height: 0;
  background: #fff;
}

.mini-page {
  position: absolute;
  inset: 0;
  display: flex;
}

.mini-frame {
  width: 100%;
  height: 100%;
  border: 0;
  background: #fff;
}

.mini-shield {
  position: absolute;
  inset: 0;
  z-index: 2;
  cursor: default;
}

/* ===== Служебные страницы ===== */

.mini-start,
.mini-panel {
  flex: 1;
  overflow: auto;
  padding: 22px;
  background: var(--bg-raised);
  color: var(--text);
  font-family: var(--font-sans);
}

.mini-start-title {
  margin: 0 0 14px;
  color: var(--text);
  font-size: 16px;
  font-weight: 700;
  letter-spacing: -0.01em;
}

.mini-start-hint {
  margin: 0 0 12px;
  color: var(--text-muted);
  font-size: 12.5px;
}

.mini-start-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
  gap: 8px;
}

.mini-start-card {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 11px 12px;
  border: 1px solid var(--border);
  border-radius: 9px;
  background: var(--surface);
  color: var(--text);
  font-size: 12.5px;
  font-weight: 600;
  text-align: left;
  cursor: pointer;
  transition: border-color 0.16s ease, background-color 0.16s ease,
    transform 0.12s ease;
}

.mini-start-card:hover {
  border-color: var(--accent-border);
  background: var(--surface-2);
  transform: translateY(-1px);
}

.mini-start-card-icon {
  flex-shrink: 0;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--accent);
}

.mini-start-card-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.mini-panel {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 18px;
}

.mini-panel-card {
  width: 100%;
  max-width: 320px;
  padding: 16px;
  border: 1px solid var(--border);
  border-radius: 12px;
  background: var(--surface);
}

.mini-panel-kicker {
  margin: 0 0 8px;
  color: var(--accent-strong);
  font-size: 10.5px;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

.mini-panel-url {
  margin: 0 0 8px;
  overflow-wrap: anywhere;
  color: var(--text);
  font-family: var(--font-mono);
  font-size: 12px;
}

.mini-panel-note {
  margin: 0 0 14px;
  color: var(--text-muted);
  font-size: 12.5px;
  line-height: 1.5;
}

/* В общем режиме наблюдатели не могут управлять превью. */
.mini-browser.is-readonly .mini-tab,
.mini-browser.is-readonly .mini-nav-btn,
.mini-browser.is-readonly .mini-tab-add {
  cursor: default;
}
</style>
