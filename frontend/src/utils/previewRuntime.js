/* eslint-disable no-empty -- runtime намеренно проглатывает ошибки доступа */
/* oxlint-disable no-unused-vars, no-eval -- runtime исполняет код в sandbox */
/*
 * Runtime, который выполняется внутри пользовательской страницы (в sandbox).
 * Он не имеет доступа к приложению: всё общение идёт через postMessage.
 *
 * Функция специально написана самодостаточной: она сериализуется через
 * Function.prototype.toString() и вставляется в документ комнаты.
 */
function previewRuntime(config) {
  var settings = config || {}
  var TAB = String(settings.tab || '')
  var DOC = Number(settings.doc || 0)
  var MODE =
    settings.mode === 'capture' || settings.mode === 'replay'
      ? settings.mode
      : 'off'
  var INITIAL_HASH = String(settings.hash || '')
  var MAX_TEXT = 4000

  function post(payload) {
    if (!payload || typeof payload !== 'object') return
    payload.source = 'peerlessons-preview'
    payload.tab = TAB
    payload.doc = DOC
    try {
      var top = window.top || window.parent
      top.postMessage(payload, '*')
    } catch (error) {
      /* приложение недоступно */
    }
  }

  function toDisplay(value, depth) {
    var level = depth || 0

    if (value === null) return 'null'
    if (value === undefined) return 'undefined'

    var type = typeof value

    if (type === 'string') {
      return level === 0 ? value : JSON.stringify(value)
    }
    if (type === 'number' || type === 'boolean' || type === 'bigint') {
      return String(value)
    }
    if (type === 'symbol') return value.toString()
    if (type === 'function') {
      var fnName = ''
      try {
        fnName = value.name || ''
      } catch (error) {}
      return 'ƒ ' + (fnName || 'anonymous') + '()'
    }
    if (type !== 'object') return String(value)

    if (value instanceof Error) {
      var stack = ''
      try {
        stack = value.stack ? String(value.stack) : ''
      } catch (error) {}
      if (stack) return stack.slice(0, MAX_TEXT)
      return String(value.name || 'Error') + ': ' + String(value.message || '')
    }

    if (typeof Node !== 'undefined' && value instanceof Node) {
      try {
        if (value.nodeType === 1) {
          var tag = String(value.tagName || '').toLowerCase()
          var nodeId = value.id ? '#' + value.id : ''
          var classes =
            typeof value.className === 'string' && value.className.trim()
              ? '.' + value.className.trim().split(/\s+/).join('.')
              : ''
          return '<' + tag + nodeId + classes + '>'
        }
        return String(value.nodeValue || value.nodeName || 'Node')
      } catch (error) {
        return '[Node]'
      }
    }

    if (level >= 3) return Array.isArray(value) ? '[…]' : '{…}'

    try {
      var seen = []
      var json = JSON.stringify(
        value,
        function (key, item) {
          if (typeof item === 'object' && item !== null) {
            if (seen.indexOf(item) !== -1) return '[Circular]'
            seen.push(item)
          }
          if (typeof item === 'bigint') return item.toString()
          if (typeof item === 'function') {
            return 'ƒ ' + (item.name || 'anonymous') + '()'
          }
          return item
        },
        2
      )

      if (json === undefined) return String(value)
      return json.length > MAX_TEXT ? json.slice(0, MAX_TEXT) + '…' : json
    } catch (error) {
      try {
        return String(value)
      } catch (error2) {
        return '[object]'
      }
    }
  }

  function formatArgs(args) {
    var parts = []
    for (var i = 0; i < args.length; i += 1) {
      parts.push(toDisplay(args[i], 0))
    }
    var text = parts.join(' ')
    return text.length > MAX_TEXT ? text.slice(0, MAX_TEXT) + '…' : text
  }

  /* ---------- консоль и ошибки ---------- */

  try {
    var levels = ['log', 'info', 'warn', 'error', 'debug']
    for (var l = 0; l < levels.length; l += 1) {
      ;(function (level) {
        var original = console[level]
        if (typeof original !== 'function') return

        console[level] = function () {
          var args = Array.prototype.slice.call(arguments)
          try {
            post({
              action: 'console',
              level: level === 'debug' ? 'log' : level,
              text: formatArgs(args)
            })
          } catch (error) {}
          return original.apply(console, args)
        }
      })(levels[l])
    }
  } catch (error) {}

  window.addEventListener('error', function (event) {
    // Ошибки загрузки ресурсов (картинки, шрифты) приходят без message/error —
    // в консоли превью они только создают шум.
    if (!event.message && !event.error) return

    var text = event.message || 'Ошибка выполнения'
    if (event.filename) {
      text += ' (' + event.filename + ':' + (event.lineno || 0) + ':' + (event.colno || 0) + ')'
    }
    if (event.error && event.error.stack) {
      text += '\n' + String(event.error.stack)
    }
    post({ action: 'console', level: 'error', text: text.slice(0, MAX_TEXT) })
  })

  window.addEventListener('unhandledrejection', function (event) {
    post({
      action: 'console',
      level: 'error',
      text: ('Unhandled rejection: ' + toDisplay(event.reason, 0)).slice(0, MAX_TEXT)
    })
  })

  /* ---------- сеть ---------- */

  try {
    var nativeFetch = window.fetch
    if (typeof nativeFetch === 'function') {
      window.fetch = function (input, init) {
        var url = ''
        try {
          url =
            typeof input === 'string'
              ? input
              : (input && input.url) || String(input)
        } catch (error) {}
        var method = (init && init.method) || (input && input.method) || 'GET'
        var started = Date.now()

        var request = nativeFetch.apply(this, arguments)
        if (request && typeof request.then === 'function') {
          request.then(
            function (response) {
              post({
                action: 'network',
                entry: {
                  kind: 'fetch',
                  method: String(method).toUpperCase(),
                  url: String(url).slice(0, 2048),
                  status: response.status,
                  ok: response.ok,
                  duration: Date.now() - started
                }
              })
              return response
            },
            function (error) {
              post({
                action: 'network',
                entry: {
                  kind: 'fetch',
                  method: String(method).toUpperCase(),
                  url: String(url).slice(0, 2048),
                  status: 0,
                  ok: false,
                  duration: Date.now() - started,
                  error: String((error && error.message) || error).slice(0, 300)
                }
              })
              throw error
            }
          )
        }

        return request
      }
    }
  } catch (error) {}

  try {
    var XHR = window.XMLHttpRequest
    if (XHR && XHR.prototype) {
      var nativeOpen = XHR.prototype.open
      var nativeSend = XHR.prototype.send

      XHR.prototype.open = function (method, url) {
        try {
          this.__pl_method = method
          this.__pl_url = url
        } catch (error) {}
        return nativeOpen.apply(this, arguments)
      }

      XHR.prototype.send = function () {
        var xhr = this
        var started = Date.now()

        try {
          xhr.addEventListener('loadend', function () {
            post({
              action: 'network',
              entry: {
                kind: 'xhr',
                method: String(xhr.__pl_method || 'GET').toUpperCase(),
                url: String(xhr.__pl_url || '').slice(0, 2048),
                status: xhr.status || 0,
                ok: xhr.status >= 200 && xhr.status < 400,
                duration: Date.now() - started
              }
            })
          })
        } catch (error) {}

        return nativeSend.apply(this, arguments)
      }
    }
  } catch (error) {}

  /* ---------- навигация ---------- */

  function reportNavigation(href, target, extra) {
    var options = extra || {}
    post({
      action: 'navigate',
      href: String(href == null ? '' : href).slice(0, 2000),
      target: String(target || '').toLowerCase().slice(0, 40),
      newTab: Boolean(options.newTab),
      formMethod: options.formMethod ? String(options.formMethod) : ''
    })
  }

  // Слушаем последнюю фазу всплытия: если сама страница отменила переход
  // (SPA-навигация), мы не вмешиваемся.
  window.addEventListener('click', function (event) {
    if (!event.isTrusted || event.defaultPrevented) return

    var anchor = null
    try {
      anchor =
        event.target && event.target.closest
          ? event.target.closest('a[href]')
          : null
    } catch (error) {}

    if (!anchor) return

    var raw = anchor.getAttribute('href')
    if (raw === null) return

    var href = String(raw).trim()
    if (!href) return
    // Якоря внутри документа браузер прокручивает сам.
    if (href.charAt(0) === '#') return
    if (/^(javascript:|mailto:|tel:)/i.test(href)) return

    event.preventDefault()
    reportNavigation(href, anchor.getAttribute('target') || '', {
      newTab: event.metaKey || event.ctrlKey || event.shiftKey
    })
  })

  window.addEventListener('submit', function (event) {
    if (!event.isTrusted || event.defaultPrevented) return

    var form = event.target
    if (!form || String(form.tagName || '').toUpperCase() !== 'FORM') return

    event.preventDefault()

    var action = form.getAttribute('action') || ''
    var method = String(form.getAttribute('method') || 'get').toLowerCase()

    if (method === 'get') {
      try {
        var params = new URLSearchParams()
        var data = new FormData(form)
        data.forEach(function (value, key) {
          params.append(key, String(value))
        })
        var query = params.toString()
        if (query) {
          action += (action.indexOf('?') === -1 ? '?' : '&') + query
        }
      } catch (error) {}
    }

    // POST к статическим файлам комнаты всё равно некуда отправлять:
    // переходим на страницу, чтобы форма не ломала sandbox.
    reportNavigation(action, form.getAttribute('target') || '', {
      formMethod: method
    })
  })

  try {
    window.open = function (url, target) {
      if (url == null || !String(url).trim()) return null
      reportNavigation(
        String(url),
        target == null ? '_blank' : target,
        { newTab: true }
      )
      return null
    }
  } catch (error) {}

  /* ---------- взаимодействие для общего режима ---------- */

  function pathOf(element) {
    var parts = []
    var node = element

    while (
      node &&
      node.nodeType === 1 &&
      node !== document.documentElement &&
      node.parentNode
    ) {
      var index = Array.prototype.indexOf.call(node.parentNode.children, node)
      if (index < 0) return ''
      parts.unshift(index)
      node = node.parentNode
    }

    return parts.join('/')
  }

  function elementAt(path) {
    var node = document.documentElement
    if (!path) return node

    var parts = String(path).split('/')
    for (var i = 0; i < parts.length; i += 1) {
      node = node && node.children ? node.children[Number(parts[i])] : null
      if (!node) return null
    }

    return node
  }

  function isAnchor(target) {
    try {
      return Boolean(target && target.closest && target.closest('a[href]'))
    } catch (error) {
      return false
    }
  }

  if (MODE === 'capture') {
    document.addEventListener(
      'click',
      function (event) {
        if (!event.isTrusted) return

        var target = event.target
        if (!target || target.nodeType !== 1) return
        // Переходы по ссылкам обрабатываются отдельно.
        if (isAnchor(target)) return

        var tag = target.tagName
        if (tag === 'SELECT' || tag === 'TEXTAREA') return
        if (tag === 'INPUT') {
          var inputType = String(target.type || '').toLowerCase()
          if (
            ['button', 'submit', 'reset', 'image'].indexOf(inputType) === -1
          ) {
            return
          }
        }

        post({
          action: 'interaction',
          event: { action: 'click', path: pathOf(target) }
        })
      },
      true
    )

    document.addEventListener(
      'input',
      function (event) {
        if (!event.isTrusted) return

        var target = event.target
        if (!target || target.nodeType !== 1) return

        var detail = { action: 'input', path: pathOf(target) }
        if (typeof target.value === 'string') {
          detail.value = target.value.slice(0, 2000)
        } else if (target.isContentEditable) {
          detail.value = String(target.textContent || '').slice(0, 2000)
        }
        if (typeof target.checked === 'boolean') detail.checked = target.checked

        post({ action: 'interaction', event: detail })
      },
      true
    )

    document.addEventListener(
      'change',
      function (event) {
        if (!event.isTrusted) return

        var target = event.target
        if (!target || target.nodeType !== 1) return

        var detail = { action: 'change', path: pathOf(target) }
        if (typeof target.value === 'string') detail.value = target.value
        if (typeof target.checked === 'boolean') detail.checked = target.checked

        post({ action: 'interaction', event: detail })
      },
      true
    )

    ;['keydown', 'keyup'].forEach(function (type) {
      document.addEventListener(
        type,
        function (event) {
          if (!event.isTrusted) return

          var target = event.target
          post({
            action: 'interaction',
            event: {
              action: type,
              path:
                target && target.nodeType === 1 ? pathOf(target) : '',
              key: event.key,
              code: event.code,
              altKey: event.altKey,
              ctrlKey: event.ctrlKey,
              metaKey: event.metaKey,
              shiftKey: event.shiftKey
            }
          })
        },
        true
      )
    })
  }

  if (MODE === 'capture' || MODE === 'replay') {
    window.addEventListener('message', function (event) {
      var data = event.data
      if (!data || data.source !== 'peerlessons-preview') return
      if (data.action !== 'replay' || !data.event) return

      var detail = data.event
      var target = elementAt(detail.path || '')
      if (!target) return

      if (detail.action === 'click') {
        try {
          target.click()
        } catch (error) {}
        return
      }

      if (detail.action === 'input' || detail.action === 'change') {
        if (detail.checked !== undefined && 'checked' in target) {
          target.checked = Boolean(detail.checked)
        } else if (detail.value !== undefined) {
          if (target.isContentEditable) {
            target.textContent = detail.value
          } else {
            target.value = detail.value
          }
        }

        var kind = detail.action === 'input' ? 'input' : 'change'
        try {
          target.dispatchEvent(new Event(kind, { bubbles: true }))
        } catch (error) {}
        return
      }

      if (detail.action === 'keydown' || detail.action === 'keyup') {
        try {
          target.focus()
        } catch (error) {}

        try {
          target.dispatchEvent(
            new KeyboardEvent(detail.action, {
              key: detail.key,
              code: detail.code,
              altKey: Boolean(detail.altKey),
              ctrlKey: Boolean(detail.ctrlKey),
              metaKey: Boolean(detail.metaKey),
              shiftKey: Boolean(detail.shiftKey),
              bubbles: true,
              cancelable: true
            })
          )
        } catch (error) {}
      }
    })
  }

  /* ---------- команды из панели разработчика ---------- */

  var highlightElement = null
  var highlightPath = ''

  function clearHighlight() {
    if (highlightElement && highlightElement.parentNode) {
      highlightElement.parentNode.removeChild(highlightElement)
    }
    highlightElement = null
    highlightPath = ''
  }

  function positionHighlight() {
    if (!highlightElement) return

    var node = elementAt(highlightPath)
    if (!node || node.nodeType !== 1) {
      clearHighlight()
      return
    }

    var rect = node.getBoundingClientRect()
    highlightElement.style.left = rect.left + 'px'
    highlightElement.style.top = rect.top + 'px'
    highlightElement.style.width = Math.max(0, rect.width) + 'px'
    highlightElement.style.height = Math.max(0, rect.height) + 'px'
  }

  function highlight(path) {
    clearHighlight()
    if (!path) return

    var node = elementAt(path)
    if (!node || node.nodeType !== 1) return

    highlightPath = String(path)

    try {
      node.scrollIntoView({ block: 'nearest', inline: 'nearest' })
    } catch (error) {}

    highlightElement = document.createElement('div')
    highlightElement.setAttribute('data-peerlessons-highlight', '')
    highlightElement.style.cssText =
      'position:fixed;z-index:2147483647;pointer-events:none;' +
      'border:2px solid #ff7a45;background:rgba(255,122,69,0.14);' +
      'border-radius:2px;box-sizing:border-box;'
    document.documentElement.appendChild(highlightElement)
    positionHighlight()
  }

  window.addEventListener('resize', positionHighlight)
  window.addEventListener('scroll', positionHighlight, true)

  function serializeDom() {
    var count = 0

    function walk(node, depth) {
      if (!node) return null

      if (node.nodeType === 3) {
        var text = String(node.nodeValue || '').replace(/\s+/g, ' ').trim()
        return text ? { type: 'text', text: text.slice(0, 160) } : null
      }

      if (node.nodeType !== 1) return null

      count += 1
      if (count > 2000) return { type: 'more' }

      var attrs = []
      var names = ['id', 'class', 'src', 'href', 'type', 'name', 'value', 'alt', 'title']
      for (var i = 0; i < names.length; i += 1) {
        var value = node.getAttribute && node.getAttribute(names[i])
        if (value) attrs.push([names[i], String(value).slice(0, 140)])
      }

      var children = []
      if (depth < 14) {
        for (var j = 0; j < node.children.length; j += 1) {
          var child = walk(node.children[j], depth + 1)
          if (child) children.push(child)
        }
      }

      return {
        type: 'element',
        tag: String(node.tagName || '').toLowerCase(),
        path: pathOf(node),
        attrs: attrs,
        truncated: depth >= 14 && node.children.length > 0,
        children: children
      }
    }

    return walk(document.documentElement, 0)
  }

  function scrollToHash(hash) {
    var value = String(hash || '')
    if (!value || value.charAt(0) !== '#') return

    var id = value.slice(1)
    if (!id) return

    try {
      var target =
        document.getElementById(id) || document.getElementsByName(id)[0]
      if (target && target.scrollIntoView) {
        target.scrollIntoView({ block: 'start' })
      }
    } catch (error) {}
  }

  function runEval(data) {
    var requestId = data.requestId
    var code = String(data.code == null ? '' : data.code)
    var result
    var ok = true

    try {
      // Непрямой eval выполняется в глобальной области страницы.
      result = (0, eval)(code)
    } catch (error) {
      ok = false
      result = error
    }

    if (ok && result && typeof result.then === 'function') {
      result.then(
        function (value) {
          post({
            action: 'eval-result',
            requestId: requestId,
            ok: true,
            text: toDisplay(value, 0)
          })
        },
        function (error) {
          post({
            action: 'eval-result',
            requestId: requestId,
            ok: false,
            text: toDisplay(error, 0)
          })
        }
      )
      return
    }

    post({
      action: 'eval-result',
      requestId: requestId,
      ok: ok,
      text: toDisplay(result, 0)
    })
  }

  window.addEventListener('message', function (event) {
    var data = event.data
    if (!data || data.source !== 'peerlessons-app') return

    if (data.type === 'eval') {
      runEval(data)
      return
    }

    if (data.type === 'dom') {
      post({ action: 'dom', requestId: data.requestId, root: serializeDom() })
      return
    }

    if (data.type === 'highlight') {
      highlight(data.path)
      return
    }

    if (data.type === 'hash') {
      scrollToHash(data.hash)
    }
  })

  /* ---------- готовность ---------- */

  function announceTitle() {
    post({ action: 'title', title: String(document.title || '').slice(0, 160) })
  }

  function observeTitle() {
    try {
      var title = document.querySelector('title')
      if (!title || typeof MutationObserver === 'undefined') return

      new MutationObserver(announceTitle).observe(title, {
        childList: true,
        characterData: true,
        subtree: true
      })
    } catch (error) {}
  }

  function start() {
    scrollToHash(INITIAL_HASH)
    observeTitle()
    post({
      action: 'ready',
      title: String(document.title || '').slice(0, 160)
    })
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', start)
  } else {
    start()
  }
}

export function buildPreviewRuntime(options = {}) {
  const config = {
    tab: String(options.tabId || ''),
    doc: Number(options.docId || 0),
    mode:
      options.interactionMode === 'capture' ||
      options.interactionMode === 'replay'
        ? options.interactionMode
        : 'off',
    hash: String(options.initialHash || '')
  }

  return `<script>\n(${previewRuntime.toString()})(${JSON.stringify(
    config
  )});\n</script>`
}
