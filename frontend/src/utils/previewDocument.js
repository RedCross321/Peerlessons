import { buildPreviewRuntime } from './previewRuntime.js'

const HTML_EXTENSIONS = /\.html?$/i
const CSS_EXTENSION = /\.css$/i
const JS_EXTENSION = /\.js$/i

export function isHtmlFile(name) {
  return HTML_EXTENSIONS.test(String(name || ''))
}

export function externalTitle(url) {
  try {
    return new URL(url).host || String(url)
  } catch {
    return String(url)
  }
}

export function pickHtmlFile(files, preferred) {
  const names = Object.keys(files || {})

  if (preferred && isHtmlFile(preferred) && names.includes(preferred)) {
    return preferred
  }

  if (names.includes('index.html')) return 'index.html'

  return names.find((name) => isHtmlFile(name)) || ''
}

export function isSafeExternalUrl(url) {
  const value = String(url || '').trim()
  if (!value || !/^https?:\/\//i.test(value)) return false

  try {
    const parsed = new URL(value)
    return parsed.protocol === 'http:' || parsed.protocol === 'https:'
  } catch {
    return false
  }
}

function safeDecode(value) {
  try {
    return decodeURIComponent(value)
  } catch {
    return value
  }
}

function normalizePath(path) {
  const stack = []

  for (const segment of String(path || '').split('/')) {
    if (!segment || segment === '.') continue
    if (segment === '..') {
      stack.pop()
      continue
    }
    stack.push(segment)
  }

  return stack.join('/')
}

function lookupFile(files, path) {
  if (!path) return ''
  if (Object.prototype.hasOwnProperty.call(files, path)) return path

  const lower = path.toLowerCase()
  const exact = Object.keys(files).find((name) => name.toLowerCase() === lower)
  if (exact) return exact

  const base = path.split('/').pop()
  if (base && base !== path) {
    const baseLower = base.toLowerCase()
    return (
      Object.keys(files).find((name) => name.toLowerCase() === baseLower) || ''
    )
  }

  return ''
}

function externalReference(url) {
  return isSafeExternalUrl(url)
    ? { kind: 'external', url }
    : { kind: 'ignore' }
}

/**
 * Разрешает ссылку из пользовательской страницы относительно файла комнаты.
 *
 * Возвращает один из вариантов:
 *   { kind: 'self' }                       — пустая ссылка;
 *   { kind: 'ignore' }                     — javascript:, data:, mailto: и т.п.;
 *   { kind: 'hash', hash }                 — якорь внутри текущей страницы;
 *   { kind: 'file', file, isHtml, ... }    — файл комнаты;
 *   { kind: 'external', url }              — внешний http(s)-адрес;
 *   { kind: 'missing', path, ... }         — файла в комнате нет.
 */
export function resolvePreviewReference(files, reference) {
  const raw = String(reference == null ? '' : reference).trim()
  if (!raw) return { kind: 'self' }

  const schemeMatch = /^([a-z][a-z0-9+.-]*):/i.exec(raw)
  if (schemeMatch) {
    const scheme = schemeMatch[1].toLowerCase()

    if (scheme === 'http' || scheme === 'https') {
      return externalReference(raw)
    }

    // Скриптовые и служебные схемы в превью не выполняем.
    return { kind: 'ignore' }
  }

  if (raw.startsWith('//')) return externalReference(`https:${raw}`)

  if (raw.startsWith('#')) return { kind: 'hash', hash: raw }

  const hashIndex = raw.indexOf('#')
  const hash = hashIndex >= 0 ? raw.slice(hashIndex) : ''
  const withoutHash = hashIndex >= 0 ? raw.slice(0, hashIndex) : raw
  const queryIndex = withoutHash.indexOf('?')
  const pathPart =
    queryIndex >= 0 ? withoutHash.slice(0, queryIndex) : withoutHash
  const query = queryIndex >= 0 ? withoutHash.slice(queryIndex + 1) : ''

  const normalized = normalizePath(safeDecode(pathPart))
  if (!normalized) {
    return hash ? { kind: 'hash', hash } : { kind: 'self' }
  }

  const file = lookupFile(files, normalized)
  if (file) {
    return {
      kind: 'file',
      file,
      hash,
      query,
      isHtml: isHtmlFile(file)
    }
  }

  return { kind: 'missing', path: normalized, hash, query }
}

function escapeAttribute(value) {
  return String(value)
    .replace(/&/g, '&amp;')
    .replace(/"/g, '&quot;')
    .replace(/</g, '&lt;')
}

function escapeScriptContent(code) {
  // Литерал </script> внутри пользовательского JS закрыл бы тег раньше времени.
  return String(code).replace(/<\/(script)/gi, '<\\/$1')
}

function escapeStyleContent(code) {
  // Тот же приём для CSS: </style> в содержимом закрыл бы тег.
  return String(code).replace(/<\/(style)/gi, '<\\/$1')
}

function inlineStyles(html, files) {
  return html.replace(/<link\b[^>]*>/gi, (tag) => {
    const href = /\bhref\s*=\s*(["'])(.*?)\1/i.exec(tag)
    if (!href) return tag

    const resolved = resolvePreviewReference(files, href[2])
    if (resolved.kind !== 'file' || !CSS_EXTENSION.test(resolved.file)) {
      return tag
    }

    const media = /\bmedia\s*=\s*(["'])(.*?)\1/i.exec(tag)
    const mediaAttr = media ? ` media="${escapeAttribute(media[2])}"` : ''

    return `<style${mediaAttr}>\n${escapeStyleContent(files[resolved.file] || '')}\n</style>`
  })
}

function inlineScripts(html, files) {
  return html.replace(/<script\b([^>]*)>\s*<\/script>/gi, (tag, attrs) => {
    const src = /\bsrc\s*=\s*(["'])(.*?)\1/i.exec(attrs)
    if (!src) return tag

    const resolved = resolvePreviewReference(files, src[2])
    if (resolved.kind !== 'file' || !JS_EXTENSION.test(resolved.file)) {
      return tag
    }

    const cleanAttrs = attrs
      .replace(/\bsrc\s*=\s*(["'])[^"']*\1/gi, '')
      .trim()
    const content = escapeScriptContent(files[resolved.file] || '')

    return `<script${cleanAttrs ? ` ${cleanAttrs}` : ''}>\n${content}\n</script>`
  })
}

function injectRuntime(html, options) {
  const runtime = buildPreviewRuntime({
    tabId: options.tabId,
    docId: options.docId,
    interactionMode: options.interactionMode,
    initialHash: options.initialHash
  })

  const head = /<head\b[^>]*>/i.exec(html)
  if (head) {
    const at = head.index + head[0].length
    return `${html.slice(0, at)}\n${runtime}${html.slice(at)}`
  }

  const htmlTag = /<html\b[^>]*>/i.exec(html)
  if (htmlTag) {
    const at = htmlTag.index + htmlTag[0].length
    return `${html.slice(0, at)}\n${runtime}${html.slice(at)}`
  }

  const doctype = /<!doctype[^>]*>/i.exec(html)
  if (doctype) {
    const at = doctype.index + doctype[0].length
    return `${html.slice(0, at)}\n${runtime}${html.slice(at)}`
  }

  return runtime + html
}

/**
 * Собирает готовый документ для страницы комнаты: подставляет локальные
 * CSS/JS и добавляет runtime, который связывает страницу с мини-браузером.
 */
export function buildPreviewDocument(files, file, options = {}) {
  if (!file || !Object.prototype.hasOwnProperty.call(files, file)) {
    return (
      '<!DOCTYPE html><html><head><meta charset="utf-8"></head>' +
      '<body style="margin:0;padding:24px;font-family:sans-serif;color:#667">' +
      'Страница не найдена.</body></html>'
    )
  }

  if (!isHtmlFile(file)) {
    return (
      '<!DOCTYPE html><html><head><meta charset="utf-8"></head>' +
      '<body style="margin:0;padding:24px;font-family:sans-serif;color:#667">' +
      'Это не HTML-страница.</body></html>'
    )
  }

  let html = String(files[file] || '')

  html = inlineStyles(html, files)
  html = inlineScripts(html, files)

  return injectRuntime(html, options)
}
