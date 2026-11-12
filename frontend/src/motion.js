const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)')
const noMotion = () => reducedMotion.matches

function springEasing(stiffness = 170, damping = 19) {
  const w0 = Math.sqrt(stiffness)
  const zeta = damping / (2 * w0)
  const wd = w0 * Math.sqrt(1 - zeta * zeta)
  const duration = 6 / (zeta * w0)
  const points = []

  for (let i = 0; i <= 48; i++) {
    const t = (i / 48) * duration
    const decay = Math.exp(-zeta * w0 * t)
    const value = 1 - decay * (Math.cos(wd * t) + ((zeta * w0) / wd) * Math.sin(wd * t))
    points.push(Math.round(value * 1000) / 1000)
  }
  points[points.length - 1] = 1

  return `linear(${points.join(', ')})`
}

export const ease = {
  out: 'cubic-bezier(0.22, 1, 0.36, 1)',
  inOut: 'cubic-bezier(0.65, 0, 0.35, 1)',
  in: 'cubic-bezier(0.55, 0, 1, 0.45)',
  spring: CSS.supports('animation-timing-function', 'linear(0, 1)')
    ? springEasing()
    : 'cubic-bezier(0.34, 1.4, 0.64, 1)',
}

document.documentElement.style.setProperty('--ease-spring', ease.spring)

export function animate(el, keyframes, options = {}) {
  if (!el?.animate) return Promise.resolve()

  if (noMotion()) {
    if (options.fill && options.fill !== 'none') {
      el.animate([keyframes.at(-1)], { duration: 0, fill: options.fill })
    }
    return Promise.resolve()
  }

  const timing = { duration: 420, easing: ease.out, ...options }
  const animation = el.animate(keyframes, timing)
  const timeout = new Promise((resolve) =>
    setTimeout(resolve, (timing.delay || 0) + timing.duration + 120),
  )

  return Promise.race([animation.finished.catch(() => {}), timeout]).then(() => {
    if (animation.playState === 'running' || animation.playState === 'paused') {
      animation.finish()
    }
    return animation
  })
}

function reveal(el, { delay = 0, duration = 640, easing = ease.out, x = 0, y = 14, scale = 1, blur = 6 } = {}) {
  return animate(
    el,
    [
      {
        opacity: 0,
        transform: `translate3d(${x}px, ${y}px, 0) scale(${scale})`,
        filter: blur ? `blur(${blur}px)` : 'none',
      },
      { opacity: 1, transform: 'translate3d(0, 0, 0) scale(1)', filter: 'blur(0px)' },
    ],
    { duration, delay, easing, fill: 'backwards' },
  )
}

export function stagger(elements, { step = 55, delay = 0, ...options } = {}) {
  const items = [...elements].filter((el) => el?.nodeType === 1)
  return Promise.all(
    items.map((el, i) => reveal(el, { ...options, delay: delay + Math.min(i, 14) * step })),
  )
}

const hidden = {
  opacity: 0,
  height: '0px',
  paddingTop: '0px',
  paddingBottom: '0px',
  marginTop: '0px',
  marginBottom: '0px',
  overflow: 'hidden',
}

function shown(el) {
  const style = getComputedStyle(el)
  return {
    opacity: 1,
    height: `${el.offsetHeight}px`,
    paddingTop: style.paddingTop,
    paddingBottom: style.paddingBottom,
    marginTop: style.marginTop,
    marginBottom: style.marginBottom,
    overflow: 'hidden',
  }
}

export function expand(el) {
  return animate(
    el,
    [
      { ...hidden, transform: 'translateY(-6px) scale(0.98)' },
      { ...shown(el), transform: 'translateY(0) scale(1)' },
    ],
    { duration: 380 },
  )
}

export function collapse(el) {
  return animate(el, [shown(el), hidden], {
    duration: 260,
    easing: ease.inOut,
    fill: 'forwards',
  })
}

export const pageTransition = {
  onEnter(el, done) {
    animate(el, [{ opacity: 0 }, { opacity: 1 }], { duration: 220 }).then(done)
  },
  onLeave(el, done) {
    animate(el, [{ opacity: 1 }, { opacity: 0 }], {
      duration: 140,
      easing: ease.in,
      fill: 'forwards',
    }).then(done)
  },
}

export function switchThemeWithTransition(apply, event) {
  if (noMotion() || !document.startViewTransition || document.hidden) {
    apply()
    return
  }

  const x = event?.clientX ?? innerWidth / 2
  const y = event?.clientY ?? innerHeight / 2
  const radius = Math.hypot(Math.max(x, innerWidth - x), Math.max(y, innerHeight - y))

  let applied = false
  const applyOnce = () => {
    if (applied) return
    applied = true
    apply()
  }
  setTimeout(applyOnce, 350)

  document
    .startViewTransition(applyOnce)
    .ready.then(() => {
      document.documentElement.animate(
        {
          clipPath: [`circle(0px at ${x}px ${y}px)`, `circle(${radius}px at ${x}px ${y}px)`],
        },
        { duration: 620, easing: ease.inOut, pseudoElement: '::view-transition-new(root)' },
      )
    })
    .catch(() => {})
}

const waiting = new WeakMap()
const observer = new IntersectionObserver(
  (entries) => {
    for (const entry of entries) {
      if (!entry.isIntersecting) continue
      observer.unobserve(entry.target)
      waiting.get(entry.target)?.()
      waiting.delete(entry.target)
    }
  },
  { rootMargin: '0px 0px -6% 0px', threshold: 0.05 },
)

function onScreen(el) {
  if (!innerHeight) return true
  const rect = el.getBoundingClientRect()
  if (!rect.width && !rect.height) return false
  return rect.top < innerHeight && rect.bottom > 0
}

function whenVisible(el, callback) {
  if (onScreen(el)) {
    callback()
    return
  }
  waiting.set(el, callback)
  observer.observe(el)
}

function stopWatching(el) {
  observer.unobserve(el)
  waiting.delete(el)
}

const vReveal = {
  mounted(el, { value = {} }) {
    if (noMotion()) return
    el.style.opacity = '0'
    whenVisible(el, () => {
      el.style.removeProperty('opacity')
      reveal(el, value)
    })
  },
  beforeUnmount: stopWatching,
}

const vStagger = {
  mounted(el, { value = {} }) {
    if (noMotion()) return
    const { selector, ...options } = value
    const items = [...(selector ? el.querySelectorAll(selector) : el.children)]
    items.forEach((item) => (item.style.opacity = '0'))
    whenVisible(el, () => {
      items.forEach((item) => item.style.removeProperty('opacity'))
      stagger(items, options)
    })
  },
  beforeUnmount: stopWatching,
}

const childObservers = new WeakMap()

const vEnterChildren = {
  mounted(el, { value = {} }) {
    const { selector, max = 4, ...options } = value
    const mo = new MutationObserver((records) => {
      if (noMotion()) return
      const added = records
        .flatMap((record) => [...record.addedNodes])
        .filter((node) => node.nodeType === 1 && (!selector || node.matches(selector)))
      if (added.length && added.length <= max) {
        stagger(added, { y: 10, blur: 4, duration: 460, step: 40, ...options })
      }
    })
    mo.observe(el, { childList: true })
    childObservers.set(el, mo)
  },
  beforeUnmount(el) {
    childObservers.get(el)?.disconnect()
    childObservers.delete(el)
  },
}

const RIPPLE_TARGETS =
  '.btn, .settings-nav-item, .theme-option, .icon-btn, .tab-add, .preview-mode-btn'

function addRipple(event) {
  if (event.button !== 0 || noMotion()) return
  const target = event.target.closest?.(RIPPLE_TARGETS)
  if (!target || target.disabled || target.getAttribute('aria-disabled') === 'true') return

  if (getComputedStyle(target).position === 'static') {
    target.style.position = 'relative'
  }

  const rect = target.getBoundingClientRect()
  const size = Math.hypot(rect.width, rect.height) * 2

  const host = document.createElement('span')
  host.className = 'ripple-host'
  host.setAttribute('aria-hidden', 'true')

  const ripple = document.createElement('span')
  ripple.className = 'ripple'
  ripple.style.width = ripple.style.height = `${size}px`
  ripple.style.left = `${event.clientX - rect.left - size / 2}px`
  ripple.style.top = `${event.clientY - rect.top - size / 2}px`

  host.append(ripple)
  target.append(host)

  ripple
    .animate(
      [
        { transform: 'scale(0)', opacity: 0.3 },
        { transform: 'scale(1)', opacity: 0 },
      ],
      { duration: 700, easing: ease.out },
    )
    .finished.catch(() => {})
    .finally(() => host.remove())
}

export default {
  install(app) {
    app.directive('reveal', vReveal)
    app.directive('stagger', vStagger)
    app.directive('enter-children', vEnterChildren)
    document.addEventListener('pointerdown', addRipple, { passive: true })
  },
}
