const DEFAULT_SITE_URL = 'https://your-domain.example'

export const SITE_URL = (
  import.meta.env.VITE_SITE_URL || DEFAULT_SITE_URL
).replace(/\/+$/, '')

function upsertMeta(attribute, key, content) {
  let element = document.head.querySelector(`meta[${attribute}="${key}"]`)

  if (!element) {
    element = document.createElement('meta')
    element.setAttribute(attribute, key)
    document.head.appendChild(element)
  }

  element.setAttribute('content', content)
}

function upsertLink(rel, href) {
  let element = document.head.querySelector(`link[rel="${rel}"]`)

  if (!element) {
    element = document.createElement('link')
    element.setAttribute('rel', rel)
    document.head.appendChild(element)
  }

  element.setAttribute('href', href)
}

/**
 * Обновляет title, description, robots, canonical и OG/Twitter-теги
 * при клиентской навигации. Для страниц под авторизацией используйте
 * robots: 'noindex, nofollow' и canonical: false.
 */
export function setPageSeo({
  title,
  description,
  path = '/',
  robots = 'index, follow',
  canonical = true,
}) {
  const url = `${SITE_URL}${path.startsWith('/') ? path : `/${path}`}`

  document.title = title

  upsertMeta('name', 'description', description)
  upsertMeta('name', 'robots', robots)

  if (canonical) {
    upsertLink('canonical', url)
  } else {
    document.head.querySelector('link[rel="canonical"]')?.remove()
  }

  upsertMeta('property', 'og:title', title)
  upsertMeta('property', 'og:description', description)
  upsertMeta('property', 'og:url', url)

  upsertMeta('name', 'twitter:title', title)
  upsertMeta('name', 'twitter:description', description)
}
