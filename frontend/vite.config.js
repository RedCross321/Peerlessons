import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath, URL } from 'node:url'

import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'
import vueDevTools from 'vite-plugin-vue-devtools'

const DEFAULT_SITE_URL = 'https://your-domain.example'

function buildSeoFiles(siteUrl, repoUrl) {
  const disallow = [
    'Disallow: /room/',
    'Disallow: /create-room',
    'Disallow: /account',
    'Disallow: /settings',
    'Disallow: /verify-email',
    'Disallow: /api/',
    'Disallow: /ws/',
  ]

  const crawlers = [
    '*',
    'GPTBot',
    'OAI-SearchBot',
    'ChatGPT-User',
    'ClaudeBot',
    'PerplexityBot',
    'Google-Extended',
    'Applebot-Extended',
    'CCBot',
  ]

  const robots = [
    '# Peerlessons',
    '',
    ...crawlers.flatMap((agent) => [
      `User-agent: ${agent}`,
      'Allow: /',
      ...disallow,
      '',
    ]),
    `Sitemap: ${siteUrl}/sitemap.xml`,
    '',
  ].join('\n')

  const sitemap = `<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>${siteUrl}/</loc>
    <changefreq>weekly</changefreq>
    <priority>1.0</priority>
  </url>
  <url>
    <loc>${siteUrl}/about/</loc>
    <changefreq>monthly</changefreq>
    <priority>0.8</priority>
  </url>
</urlset>
`

  const repoLine = repoUrl ? `- Исходный код: ${repoUrl}\n` : ''

  const llms = `# Peerlessons

> Peerlessons — self-hosted веб-приложение для совместного редактирования кода в реальном времени. Участники работают в одной комнате с файлами HTML/CSS/JS, видят изменения, выделения и каретку редактора, могут передавать права редактирования и запускать общий предпросмотр.

## Основное

- Стек: Vue 3, Monaco Editor, FastAPI, WebSocket, PostgreSQL.
- Лицензия: GNU GPL v3.0.
${repoLine}- Главная: ${siteUrl}/
- О проекте: ${siteUrl}/about/
- Вход: ${siteUrl}/login
- Регистрация: ${siteUrl}/register

## Особенности

- Один редактор за раз; остальные наблюдают в реальном времени.
- Комнаты создают авторизованные пользователи.
- Приватные комнаты (/room/...) не индексируются.
- Интерфейс на русском языке.
`

  const repoLink = repoUrl
    ? `<a href="${repoUrl}" rel="noopener">Исходный код</a>`
    : ''

  const aboutHtml = `<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>О Peerlessons — совместное редактирование кода в реальном времени</title>
  <meta name="description" content="Peerlessons — self-hosted платформа для совместного редактирования кода: комнаты, Monaco Editor, передача прав и живой предпросмотр HTML/CSS/JS. Открытый исходный код, GPL-3.0.">
  <meta name="robots" content="index, follow">
  <link rel="canonical" href="${siteUrl}/about/">
  <link rel="icon" href="/favicon.ico">
  <meta name="theme-color" content="#090b10">
  <script>
    (function () {
      try {
        var stored = localStorage.getItem('peerlessons-theme');
        var theme =
          stored === 'light' || stored === 'dark'
            ? stored
            : window.matchMedia &&
                window.matchMedia('(prefers-color-scheme: light)').matches
              ? 'light'
              : 'dark';
        document.documentElement.dataset.theme = theme;
        document.documentElement.style.colorScheme = theme;
        var meta = document.querySelector('meta[name="theme-color"]');
        if (meta) {
          meta.setAttribute('content', theme === 'light' ? '#f4f5f8' : '#090b10');
        }
      } catch (error) {
        document.documentElement.dataset.theme = 'dark';
      }
    })();
  </script>
  <meta property="og:type" content="website">
  <meta property="og:site_name" content="Peerlessons">
  <meta property="og:locale" content="ru_RU">
  <meta property="og:title" content="О Peerlessons — совместное редактирование кода">
  <meta property="og:description" content="Комнаты, Monaco Editor, передача прав и живой предпросмотр HTML/CSS/JS. Self-hosted, GPL-3.0.">
  <meta property="og:url" content="${siteUrl}/about/">
  <meta property="og:image" content="${siteUrl}/og-cover.png">
  <meta property="og:image:width" content="1200">
  <meta property="og:image:height" content="630">
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:title" content="О Peerlessons — совместное редактирование кода">
  <meta name="twitter:description" content="Комнаты, Monaco Editor, передача прав и живой предпросмотр HTML/CSS/JS.">
  <meta name="twitter:image" content="${siteUrl}/og-cover.png">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700;800&display=swap" rel="stylesheet">
  <script type="application/ld+json">
  {
    "@context": "https://schema.org",
    "@type": "SoftwareApplication",
    "name": "Peerlessons",
    "description": "Self-hosted платформа для совместного редактирования кода в реальном времени: комнаты, Monaco Editor, передача прав и живой предпросмотр HTML/CSS/JS.",
    "applicationCategory": "DeveloperApplication",
    "operatingSystem": "Web",
    "url": "${siteUrl}/",
    "inLanguage": "ru",
    "isAccessibleForFree": true,
    "offers": {
      "@type": "Offer",
      "price": "0",
      "priceCurrency": "RUB"
    },
    "license": "https://www.gnu.org/licenses/gpl-3.0.html",
    "featureList": [
      "Совместное редактирование кода в реальном времени",
      "Monaco Editor с подсветкой и автодополнением",
      "Передача прав редактирования",
      "Живой предпросмотр HTML/CSS/JS",
      "Комнаты по ссылке"
    ],
    "screenshot": "${siteUrl}/og-cover.png"${repoUrl ? `,
    "codeRepository": "${repoUrl}"` : ''}
  }
  </script>
  <style>
    :root {
      --bg: #090b10;
      --surface: #121620;
      --border: #222a39;
      --border-strong: #303a4d;
      --text: #f3f5f9;
      --muted: #9aa4b6;
      --dim: #6d7789;
      --accent: #ff7a45;
      --accent-strong: #ff9163;
    }

    :root[data-theme='light'] {
      --bg: #f4f5f8;
      --surface: #ffffff;
      --border: #dfe3ea;
      --border-strong: #c8cfda;
      --text: #171a21;
      --muted: #5b6474;
      --dim: #79828f;
      --accent: #de5a22;
      --accent-strong: #c44a17;
    }

    * { box-sizing: border-box; }

    html { color-scheme: dark; }

    html[data-theme='light'] { color-scheme: light; }

    body {
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font-family: Manrope, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      line-height: 1.6;
      -webkit-font-smoothing: antialiased;
    }

    a { color: var(--accent); text-decoration: none; }
    a:hover { color: var(--accent-strong); }

    .top {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      flex-wrap: wrap;
      padding: 20px clamp(20px, 5vw, 64px);
      border-bottom: 1px solid var(--border);
    }

    .brand {
      display: inline-flex;
      align-items: center;
      gap: 10px;
      color: var(--text);
      font-size: 18px;
      font-weight: 700;
      letter-spacing: -0.02em;
    }

    .mark {
      display: grid;
      place-items: center;
      width: 30px;
      height: 30px;
      border-radius: 9px;
      background: var(--accent);
      color: #15100d;
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      font-weight: 700;
    }

    nav { display: flex; gap: 10px; flex-wrap: wrap; }

    .btn {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      padding: 10px 16px;
      border: 1px solid transparent;
      border-radius: 9px;
      font-size: 14px;
      font-weight: 600;
      line-height: 1;
      white-space: nowrap;
    }

    .btn-primary { background: var(--accent); color: #15100d; }
    .btn-primary:hover { background: var(--accent-strong); color: #15100d; }
    .btn-ghost { border-color: var(--border); color: var(--muted); }
    .btn-ghost:hover { color: var(--text); border-color: var(--border-strong); }
    .btn-lg { padding: 14px 24px; border-radius: 10px; font-size: 15px; }

    main {
      max-width: 1040px;
      margin: 0 auto;
      padding: 72px clamp(20px, 5vw, 48px) 88px;
    }

    .hero {
      max-width: 860px;
      margin: 0 auto 72px;
      text-align: center;
    }

    .rule {
      display: block;
      width: 44px;
      height: 3px;
      margin: 0 auto 28px;
      border-radius: 999px;
      background: var(--accent);
    }

    h1 {
      margin: 0 0 20px;
      font-size: clamp(32px, 5vw, 54px);
      line-height: 1.08;
      letter-spacing: -0.035em;
    }

    h1 span { color: var(--accent); }

    .lead {
      max-width: 62ch;
      margin: 0 auto 30px;
      color: var(--muted);
      font-size: 17px;
    }

    .actions {
      display: flex;
      justify-content: center;
      gap: 12px;
      flex-wrap: wrap;
    }

    h2 { margin: 0 0 20px; font-size: 26px; letter-spacing: -0.02em; }

    .features { margin-bottom: 64px; }

    .grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
      gap: 14px;
    }

    article {
      padding: 20px;
      border: 1px solid var(--border);
      border-radius: 14px;
      background: var(--surface);
    }

    article h3 { margin: 0 0 8px; font-size: 16px; }
    article p { margin: 0; color: var(--muted); font-size: 14px; }

    .facts {
      padding: 24px;
      border: 1px solid var(--border);
      border-radius: 14px;
      background: var(--surface);
    }

    .facts ul { margin: 0; padding-left: 20px; color: var(--muted); }
    .facts li + li { margin-top: 8px; }

    footer {
      display: flex;
      justify-content: space-between;
      gap: 12px;
      flex-wrap: wrap;
      padding: 24px clamp(20px, 5vw, 64px);
      border-top: 1px solid var(--border);
      color: var(--dim);
      font-size: 13px;
    }

    @media (max-width: 600px) {
      .top { padding: 16px 20px; }
      main { padding: 48px 20px 64px; }
    }
  </style>
</head>
<body>
  <header class="top">
    <a class="brand" href="/">
      <span class="mark">/</span>
      <span>Peerlessons</span>
    </a>
    <nav>
      <a class="btn btn-ghost" href="/login">Войти</a>
      <a class="btn btn-primary" href="/register">Создать аккаунт</a>
    </nav>
  </header>

  <main>
    <section class="hero">
      <span class="rule"></span>
      <h1>Совместное редактирование кода <span>в реальном времени</span></h1>
      <p class="lead">
        Peerlessons — self-hosted веб-приложение для совместной работы над кодом.
        Участники открывают одну комнату, видят один и тот же проект из файлов
        HTML, CSS и JavaScript и наблюдают за изменениями, выделениями и кареткой
        редактора.
      </p>
      <div class="actions">
        <a class="btn btn-primary btn-lg" href="/register">Создать аккаунт</a>
        <a class="btn btn-ghost btn-lg" href="/login">Войти</a>
      </div>
    </section>

    <section class="features">
      <h2>Возможности</h2>
      <div class="grid">
        <article>
          <h3>Комнаты по ссылке</h3>
          <p>Уникальный UUID комнаты и мгновенное подключение по WebSocket.</p>
        </article>
        <article>
          <h3>Monaco Editor</h3>
          <p>Подсветка синтаксиса, автодополнение и Emmet для HTML, CSS и JavaScript.</p>
        </article>
        <article>
          <h3>Передача прав</h3>
          <p>Один участник редактирует, остальные наблюдают. Ведущий может выдать и забрать права.</p>
        </article>
        <article>
          <h3>Живой предпросмотр</h3>
          <p>HTML, CSS и JavaScript собираются в отдельном iframe и обновляются после паузы.</p>
        </article>
        <article>
          <h3>Удалённые курсоры</h3>
          <p>Видно выделение и каретку текущего редактора в реальном времени.</p>
        </article>
        <article>
          <h3>JWT-аутентификация</h3>
          <p>Access-токен на 15 минут, refresh-токен на 7 дней, автоматическое обновление и отзыв при выходе.</p>
        </article>
      </div>
    </section>

    <section class="facts">
      <h2>Технологии и лицензия</h2>
      <ul>
        <li>Backend: Python, FastAPI, SQLAlchemy, PostgreSQL.</li>
        <li>Frontend: Vue 3, Monaco Editor, Vite.</li>
        <li>Realtime: WebSocket.</li>
        <li>Развёртывание: Nginx, systemd, Fedora/Linux.</li>
        <li>Лицензия: GNU General Public License v3.0.</li>
      </ul>
    </section>
  </main>

  <footer>
    <span>Peerlessons · self-hosted · GPL-3.0</span>
    <span>
      <a href="${siteUrl}/login">Вход</a> ·
      <a href="${siteUrl}/register">Регистрация</a>${repoLink ? ' · ' + repoLink : ''} ·
      <a href="https://www.gnu.org/licenses/gpl-3.0.html" rel="noopener">Лицензия</a>
    </span>
  </footer>
</body>
</html>`

  return {
    'robots.txt': robots,
    'sitemap.xml': sitemap,
    'llms.txt': llms,
    'about/index.html': aboutHtml,
  }
}

function seoPlugin(siteUrl, repoUrl) {
  const files = buildSeoFiles(siteUrl, repoUrl)

  return {
    name: 'peerlessons-seo',

    transformIndexHtml(html) {
      return html.replaceAll('%SITE_URL%', siteUrl)
    },

    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        const requestPath = (req.url || '').split('?')[0].replace(/^\//, '')
        const key =
          requestPath === 'about' || requestPath === 'about/'
            ? 'about/index.html'
            : requestPath
        const content = files[key]

        if (!content) {
          next()
          return
        }

        let contentType = 'text/plain; charset=utf-8'
        if (key.endsWith('.xml')) contentType = 'application/xml; charset=utf-8'
        if (key.endsWith('.html')) contentType = 'text/html; charset=utf-8'

        res.statusCode = 200
        res.setHeader('Content-Type', contentType)
        res.end(content)
      })
    },

    writeBundle(options) {
      const outDir =
        options.dir || fileURLToPath(new URL('./dist', import.meta.url))

      fs.mkdirSync(outDir, { recursive: true })

      for (const [fileName, source] of Object.entries(files)) {
        const target = path.join(outDir, fileName)
        fs.mkdirSync(path.dirname(target), { recursive: true })
        fs.writeFileSync(target, source, 'utf8')
      }
    },
  }
}

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const rootDir = fileURLToPath(new URL('.', import.meta.url))
  const env = loadEnv(mode, rootDir, 'VITE_')
  const siteUrl = (env.VITE_SITE_URL || DEFAULT_SITE_URL).replace(/\/+$/, '')
  const repoUrl = env.VITE_REPO_URL || ''

  return {
    plugins: [
      vue(),
      vueDevTools(),
      seoPlugin(siteUrl, repoUrl),
    ],
    optimizeDeps: {
      include: ['monaco-editor'],
    },
    worker: {
      format: 'es',
    },
    resolve: {
      alias: {
        '@': fileURLToPath(new URL('./src', import.meta.url)),
      },
    },
    server: {
      proxy: {
        '/api': {
          target: 'http://localhost:8000',
          changeOrigin: true,
        },
        '/ws': {
          target: 'ws://localhost:8000',
          ws: true,
          changeOrigin: true,
        },
      },
    },
  }
})
