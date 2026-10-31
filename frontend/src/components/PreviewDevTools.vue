<script setup>
import { computed, nextTick, ref, watch } from 'vue'

const props = defineProps({
  logs: {
    type: Array,
    default: () => []
  },
  network: {
    type: Array,
    default: () => []
  },
  dom: {
    type: Object,
    default: null
  },
  domLoading: {
    type: Boolean,
    default: false
  },
  locked: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits([
  'eval',
  'refresh-dom',
  'highlight',
  'clear-logs',
  'clear-network',
  'close'
])

const panel = defineModel('panel', { type: String, default: 'console' })

const panels = [
  { id: 'console', label: 'Консоль' },
  { id: 'elements', label: 'Элементы' },
  { id: 'network', label: 'Сеть' }
]

const input = ref('')
const inputHistory = ref([])
const consoleList = ref(null)
const collapsed = ref(new Set())
let historyIndex = 0

const errorCount = computed(
  () => props.logs.filter((log) => log.level === 'error').length
)

const rows = computed(() => {
  if (!props.dom) return []

  const result = []
  let counter = 0

  function walk(node, depth, parentKey) {
    if (!node) return

    const key = `${parentKey}/${counter}`
    counter += 1

    if (node.type === 'text') {
      result.push({ key, kind: 'text', depth, text: node.text })
      return
    }

    if (node.type === 'more') {
      result.push({ key, kind: 'more', depth })
      return
    }

    const children = Array.isArray(node.children) ? node.children : []
    const hasChildren = children.length > 0
    const isCollapsed = collapsed.value.has(key)

    result.push({
      key,
      kind: 'element',
      depth,
      tag: node.tag,
      attrs: node.attrs || [],
      path: node.path,
      hasChildren,
      collapsed: isCollapsed
    })

    if (hasChildren && !isCollapsed) {
      children.forEach((child) => walk(child, depth + 1, key))
    }
  }

  walk(props.dom, 0, 'root')
  return result
})

function selectPanel(id) {
  panel.value = id
  if (id === 'elements') emit('refresh-dom')
}

function toggleRow(row) {
  if (!row.hasChildren) return

  const next = new Set(collapsed.value)
  if (next.has(row.key)) next.delete(row.key)
  else next.add(row.key)

  collapsed.value = next
}

function clearCurrent() {
  if (panel.value === 'network') emit('clear-network')
  else emit('clear-logs')
}

function submitEval() {
  const code = input.value.trim()
  if (!code || props.locked) return

  emit('eval', code)

  const history = inputHistory.value.filter((item) => item !== code)
  history.push(code)
  inputHistory.value = history.slice(-50)
  historyIndex = inputHistory.value.length
  input.value = ''
}

function historyPrev() {
  if (!inputHistory.value.length) return
  if (historyIndex > 0) historyIndex -= 1
  input.value = inputHistory.value[historyIndex] || ''
}

function historyNext() {
  if (!inputHistory.value.length) return
  if (historyIndex < inputHistory.value.length - 1) historyIndex += 1
  else historyIndex = inputHistory.value.length
  input.value = inputHistory.value[historyIndex] || ''
}

function formatTime(time) {
  if (!time) return ''
  const date = new Date(time)
  return [date.getHours(), date.getMinutes(), date.getSeconds()]
    .map((value) => String(value).padStart(2, '0'))
    .join(':')
}

function levelLabel(level) {
  if (level === 'input') return '›'
  if (level === 'result') return '←'
  if (level === 'warn') return 'WARN'
  if (level === 'error') return 'ERR'
  if (level === 'info') return 'INFO'
  return 'LOG'
}

function statusClass(entry) {
  if (!entry) return ''
  if (entry.status === 0 || entry.ok === false) return 'is-error'
  if (entry.status >= 200 && entry.status < 300) return 'is-ok'
  if (entry.status >= 300 && entry.status < 400) return 'is-redirect'
  return 'is-warn'
}

watch(
  () => [panel.value, props.logs.length],
  () => {
    if (panel.value !== 'console') return
    nextTick(() => {
      const list = consoleList.value
      if (list) list.scrollTop = list.scrollHeight
    })
  }
)

// При обновлении дерева ключи строк меняются — сбрасываем свёрнутые узлы.
watch(
  () => props.dom,
  () => {
    collapsed.value = new Set()
  }
)
</script>

<template>
  <section class="devtools">
    <div class="devtools-bar">
      <div class="devtools-panels" role="tablist">
        <button
          v-for="item in panels"
          :key="item.id"
          type="button"
          role="tab"
          :aria-selected="panel === item.id"
          :class="['devtools-panel-btn', { active: panel === item.id }]"
          @click="selectPanel(item.id)"
        >
          {{ item.label }}
          <span
            v-if="item.id === 'console' && errorCount"
            class="devtools-badge"
          >
            {{ errorCount }}
          </span>
        </button>
      </div>

      <div class="devtools-actions">
        <button
          type="button"
          class="devtools-action"
          :disabled="panel === 'console' ? !logs.length : !network.length"
          @click="clearCurrent"
        >
          Очистить
        </button>
        <button
          type="button"
          class="devtools-action devtools-close"
          title="Скрыть панель"
          aria-label="Скрыть панель разработчика"
          @click="emit('close')"
        >
          ×
        </button>
      </div>
    </div>

    <div v-if="panel === 'console'" class="devtools-body console-panel">
      <div ref="consoleList" class="console-list">
        <p v-if="!logs.length" class="devtools-empty">
          Консоль пуста. Ошибки и вывод страницы появятся здесь.
        </p>
        <div
          v-for="log in logs"
          :key="log.id"
          :class="['console-row', `is-${log.level}`]"
        >
          <span class="console-time">{{ formatTime(log.time) }}</span>
          <span class="console-level">{{ levelLabel(log.level) }}</span>
          <span class="console-text">{{ log.text }}</span>
        </div>
      </div>

      <form v-if="!locked" class="console-input" @submit.prevent="submitEval">
        <span class="console-prompt" aria-hidden="true">›</span>
        <input
          v-model="input"
          class="console-field"
          placeholder="Выполнить JavaScript в превью…"
          spellcheck="false"
          autocomplete="off"
          aria-label="Выполнить JavaScript в превью"
          @keydown.up.prevent="historyPrev"
          @keydown.down.prevent="historyNext"
        />
      </form>
      <p v-else class="console-locked">
        В общем режиме консоль доступна только ведущему.
      </p>
    </div>

    <div v-else-if="panel === 'elements'" class="devtools-body elements-panel">
      <div class="elements-toolbar">
        <button
          type="button"
          class="devtools-action"
          :disabled="domLoading"
          @click="emit('refresh-dom')"
        >
          Обновить
        </button>
        <span v-if="domLoading" class="elements-hint">Загрузка…</span>
        <span v-else-if="!dom" class="elements-hint">
          Дерево появится, когда страница загрузится.
        </span>
        <span v-else class="elements-hint">
          Наведите на элемент, чтобы подсветить его на странице.
        </span>
      </div>

      <div class="elements-tree" @mouseleave="emit('highlight', null)">
        <div
          v-for="row in rows"
          :key="row.key"
          class="element-row"
          :class="[`is-${row.kind}`, { 'has-children': row.hasChildren }]"
          :style="{ paddingLeft: `${8 + row.depth * 14}px` }"
          @mouseenter="row.kind === 'element' && emit('highlight', row.path)"
          @click="row.kind === 'element' && toggleRow(row)"
        >
          <template v-if="row.kind === 'element'">
            <span class="tree-toggle" aria-hidden="true">
              {{ row.hasChildren ? (row.collapsed ? '▸' : '▾') : '' }}
            </span>
            <span class="tree-tag">&lt;{{ row.tag }}</span>
            <span
              v-for="[name, value] in row.attrs"
              :key="name"
              class="tree-attr"
            >
              <span class="tree-attr-name">{{ name }}</span
              >="<span class="tree-attr-value">{{ value }}</span>"
            </span>
            <span class="tree-tag">&gt;</span>
          </template>
          <template v-else-if="row.kind === 'text'">
            <span class="tree-text">“{{ row.text }}”</span>
          </template>
          <template v-else>
            <span class="tree-more">…</span>
          </template>
        </div>
      </div>
    </div>

    <div v-else class="devtools-body">
      <p v-if="!network.length" class="devtools-empty">
        Запросы fetch и XMLHttpRequest появятся здесь.
      </p>
      <div v-else class="network-list">
        <div
          v-for="entry in network"
          :key="entry.id"
          :class="['network-row', statusClass(entry)]"
        >
          <span class="network-method">{{ entry.method }}</span>
          <span class="network-url" :title="entry.url">{{ entry.url }}</span>
          <span class="network-status">
            {{ entry.status || 'ERR' }}
          </span>
          <span class="network-time">{{ entry.duration }} мс</span>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.devtools {
  flex: 0 0 auto;
  display: flex;
  flex-direction: column;
  height: clamp(130px, 42%, 280px);
  min-height: 0;
  border-top: 1px solid var(--border);
  background: var(--bg-raised);
  color: var(--text);
}

.devtools-bar {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 4px 6px;
  border-bottom: 1px solid var(--border);
}

.devtools-panels {
  display: flex;
  align-items: center;
  gap: 2px;
  min-width: 0;
  overflow-x: auto;
}

.devtools-panel-btn {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 4px 8px;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: var(--text-muted);
  font-size: 11.5px;
  font-weight: 600;
  white-space: nowrap;
  cursor: pointer;
  transition: background-color 0.16s ease, color 0.16s ease;
}

.devtools-panel-btn:hover {
  background: var(--surface-2);
  color: var(--text);
}

.devtools-panel-btn.active {
  background: var(--accent-soft);
  color: var(--accent-strong);
}

.devtools-badge {
  min-width: 15px;
  padding: 0 4px;
  border-radius: 999px;
  background: var(--danger);
  color: #fff;
  font-size: 9.5px;
  font-weight: 700;
  line-height: 15px;
  text-align: center;
}

.devtools-actions {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
}

.devtools-action {
  padding: 3px 6px;
  border: 1px solid transparent;
  border-radius: 5px;
  background: transparent;
  color: var(--text-dim);
  font-size: 10.5px;
  font-weight: 600;
  cursor: pointer;
  transition: background-color 0.16s ease, color 0.16s ease;
}

.devtools-action:hover:not(:disabled) {
  background: var(--surface-2);
  color: var(--text);
}

.devtools-action:disabled {
  opacity: 0.4;
  cursor: default;
}

.devtools-close {
  font-size: 15px;
  line-height: 1;
  padding: 2px 6px;
}

.devtools-body {
  flex: 1 1 auto;
  min-height: 0;
  overflow: auto;
  padding: 6px 8px;
  font-family: var(--font-mono);
  font-size: 11px;
  line-height: 1.5;
}

.console-panel {
  display: flex;
  flex-direction: column;
  padding: 0;
}

.console-list {
  flex: 1 1 auto;
  min-height: 0;
  overflow: auto;
  padding: 5px 8px;
}

.console-row {
  display: grid;
  grid-template-columns: auto auto 1fr;
  gap: 6px;
  padding: 2px 0;
  border-bottom: 1px solid color-mix(in srgb, var(--border) 45%, transparent);
}

.console-time {
  color: var(--text-dim);
  font-size: 9.5px;
  white-space: nowrap;
  padding-top: 1px;
}

.console-level {
  color: var(--text-dim);
  font-size: 9px;
  font-weight: 700;
  letter-spacing: 0.04em;
  white-space: nowrap;
  padding-top: 1px;
}

.console-text {
  min-width: 0;
  color: var(--text);
  white-space: pre-wrap;
  word-break: break-word;
}

.console-row.is-warn .console-level,
.console-row.is-warn .console-text {
  color: #e0b15f;
}

.console-row.is-error .console-level,
.console-row.is-error .console-text {
  color: var(--danger-text);
}

.console-row.is-input .console-text {
  color: var(--accent-strong);
}

.console-row.is-result .console-text {
  color: var(--text-muted);
}

.console-input {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 5px 8px;
  border-top: 1px solid var(--border);
  background: var(--surface);
}

.console-prompt {
  color: var(--accent);
  font-weight: 700;
}

.console-field {
  flex: 1;
  min-width: 0;
  padding: 3px 0;
  border: 0;
  background: transparent;
  color: var(--text);
  font-family: inherit;
  font-size: 11px;
  outline: none;
}

.console-field::placeholder {
  color: var(--placeholder);
}

.console-locked {
  flex-shrink: 0;
  margin: 0;
  padding: 6px 8px;
  border-top: 1px solid var(--border);
  color: var(--text-dim);
  font-size: 10.5px;
}

.devtools-empty {
  margin: 0;
  padding: 8px 2px;
  color: var(--text-dim);
  font-family: var(--font-sans);
  font-size: 11.5px;
}

.elements-panel {
  padding: 0;
  display: flex;
  flex-direction: column;
}

.elements-toolbar {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 3px 8px;
  border-bottom: 1px solid var(--border);
}

.elements-hint {
  color: var(--text-dim);
  font-family: var(--font-sans);
  font-size: 10px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.elements-tree {
  flex: 1 1 auto;
  min-height: 0;
  overflow: auto;
  padding: 4px 0 8px;
}

.element-row {
  display: flex;
  align-items: baseline;
  gap: 2px;
  padding-right: 8px;
  white-space: nowrap;
  cursor: default;
}

.element-row.has-children {
  cursor: pointer;
}

.element-row:hover {
  background: var(--accent-soft);
}

.tree-toggle {
  display: inline-block;
  width: 11px;
  color: var(--text-dim);
  font-size: 9px;
  text-align: center;
}

.tree-tag {
  color: var(--accent-strong);
}

.tree-attr {
  color: var(--text-dim);
}

.tree-attr-name {
  color: var(--text-muted);
}

.tree-attr-value {
  color: var(--success-text);
}

.tree-text {
  color: var(--text-muted);
  font-style: italic;
}

.tree-more {
  color: var(--text-dim);
}

.network-list {
  display: flex;
  flex-direction: column;
  gap: 1px;
}

.network-row {
  display: grid;
  grid-template-columns: 44px minmax(0, 1fr) 34px 52px;
  gap: 6px;
  align-items: center;
  padding: 2px 0;
  border-bottom: 1px solid color-mix(in srgb, var(--border) 45%, transparent);
}

.network-method {
  color: var(--text-muted);
  font-size: 9.5px;
  font-weight: 700;
}

.network-url {
  overflow: hidden;
  color: var(--text);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.network-status,
.network-time {
  color: var(--text-dim);
  font-size: 9.5px;
  text-align: right;
}

.network-row.is-ok .network-status {
  color: var(--success-text);
}

.network-row.is-error .network-status {
  color: var(--danger-text);
}

.network-row.is-warn .network-status {
  color: #e0b15f;
}
</style>
