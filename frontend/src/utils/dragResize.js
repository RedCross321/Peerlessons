export function startDrag(event, { axis = 'x', onMove, onEnd } = {}) {
  if (event.button !== undefined && event.button !== 0) return

  const handle = event.currentTarget
  const getPos = (e) => (axis === 'x' ? e.clientX : e.clientY)
  const startPos = getPos(event)

  try {
    handle.setPointerCapture(event.pointerId)
  } catch {}

  handle.classList.add('is-dragging')
  document.body.style.cursor = axis === 'x' ? 'col-resize' : 'row-resize'
  document.body.style.userSelect = 'none'

  const move = (e) => onMove?.(getPos(e) - startPos)

  let stopped = false
  const stop = () => {
    if (stopped) return
    stopped = true

    try {
      handle.releasePointerCapture(event.pointerId)
    } catch {}

    handle.classList.remove('is-dragging')
    document.body.style.cursor = ''
    document.body.style.userSelect = ''
    window.removeEventListener('pointermove', move)
    window.removeEventListener('pointerup', stop)
    window.removeEventListener('pointercancel', stop)
    window.removeEventListener('blur', stop)
    handle.removeEventListener('lostpointercapture', stop)
    onEnd?.()
  }

  window.addEventListener('pointermove', move)
  window.addEventListener('pointerup', stop)
  window.addEventListener('pointercancel', stop)
  window.addEventListener('blur', stop)
  handle.addEventListener('lostpointercapture', stop)

  event.preventDefault()
}

export function clamp(value, min, max) {
  return Math.min(Math.max(value, min), Math.max(min, max))
}

export function readStoredSize(key, fallback) {
  try {
    const value = Number(localStorage.getItem(key))
    return value > 0 ? value : fallback
  } catch {
    return fallback
  }
}

export function storeSize(key, value) {
  try {
    localStorage.setItem(key, String(Math.round(value)))
  } catch {}
}
