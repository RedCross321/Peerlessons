const FIELD_LABELS = {
  title: 'Название комнаты',
  username: 'Имя пользователя',
  email: 'Email',
  password: 'Пароль',
  password_check: 'Повтор пароля',
  refresh_token: 'Сессия'
}

const NETWORK_ERROR =
  'Сервер недоступен. Проверьте подключение и попробуйте ещё раз.'

export function getErrorMessages(
  error,
  fallback = 'Не удалось выполнить действие. Попробуйте ещё раз.'
) {
  const response = error?.response

  if (!response) {
    return [NETWORK_ERROR]
  }

  const detail = response.data?.detail

  if (Array.isArray(detail)) {
    const messages = detail.map(describeValidationError).filter(Boolean)

    if (messages.length) {
      return [...new Set(messages)]
    }
  }

  if (typeof detail === 'string' && detail.trim()) {
    return [detail.trim()]
  }

  switch (response.status) {
    case 401:
      return ['Неверный email или пароль']
    case 403:
      return ['Недостаточно прав. Возможно, аккаунт деактивирован.']
    case 404:
      return ['Запрошенные данные не найдены']
    case 409:
      return ['Такие данные уже используются']
    case 422:
      return ['Проверьте правильность введённых данных']
    default:
      return [fallback]
  }
}

function describeValidationError(item) {
  if (!item || typeof item !== 'object') {
    return typeof item === 'string' ? item : ''
  }

  const field = fieldLabel(item.loc)
  const ctx = item.ctx || {}
  const type = item.type || ''
  const rawMessage = String(item.msg || '')

  let message

  switch (type) {
    case 'missing':
      message = 'обязательное поле'
      break
    case 'string_too_short':
      message = ctx.min_length
        ? `минимум ${ctx.min_length} ${plural(ctx.min_length, 'символ', 'символа', 'символов')}`
        : 'значение слишком короткое'
      break
    case 'string_too_long':
      message = ctx.max_length
        ? `не больше ${ctx.max_length} ${plural(ctx.max_length, 'символ', 'символа', 'символов')}`
        : 'значение слишком длинное'
      break
    case 'string_pattern_mismatch':
      message = 'недопустимые символы'
      break
    case 'value_error':
      message = humanizeMessage(rawMessage)
      break
    default:
      message = humanizeMessage(rawMessage) || 'некорректное значение'
  }

  if (field === 'Email' && message === 'некорректный email') {
    return 'Некорректный email'
  }

  if (!field) {
    return capitalize(message)
  }

  // Не дублируем название поля, если сервер уже начал сообщение с него
  // (например, «Пароль слишком простой…»).
  if (message.toLowerCase().startsWith(field.toLowerCase())) {
    return capitalize(message)
  }

  return `${field}: ${message}`
}

function humanizeMessage(rawMessage) {
  const message = rawMessage.replace(/^Value error,\s*/i, '').trim()

  if (!message) return ''

  const min = message.match(/at least (\d+) characters?/i)
  if (min) {
    return `минимум ${min[1]} ${plural(Number(min[1]), 'символ', 'символа', 'символов')}`
  }

  const max = message.match(/at most (\d+) characters?/i)
  if (max) {
    return `не больше ${max[1]} ${plural(Number(max[1]), 'символ', 'символа', 'символов')}`
  }

  if (/valid email/i.test(message)) return 'некорректный email'
  if (/field required/i.test(message)) return 'обязательное поле'
  if (/should match pattern/i.test(message)) return 'недопустимые символы'
  if (/valid string/i.test(message)) return 'ожидается текст'

  return message
}

function fieldLabel(loc) {
  if (!Array.isArray(loc) || loc.length === 0) return ''
  return FIELD_LABELS[loc[loc.length - 1]] || ''
}

function plural(count, one, few, many) {
  const abs = Math.abs(Number(count)) % 100
  const last = abs % 10

  if (abs > 10 && abs < 20) return many
  if (last === 1) return one
  if (last >= 2 && last <= 4) return few
  return many
}

function capitalize(text) {
  return text ? text[0].toUpperCase() + text.slice(1) : text
}
