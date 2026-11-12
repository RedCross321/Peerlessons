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
      --bg-raised: #0d1017;
      --surface: #121620;
      --surface-2: #171c28;
      --border: #222a39;
      --border-strong: #303a4d;
      --text: #f3f5f9;
      --muted: #9aa4b6;
      --dim: #8a94a6;
      --accent: #ff7a45;
      --accent-strong: #ff9163;
      --accent-soft: rgba(255, 122, 69, 0.13);
      --accent-border: rgba(255, 122, 69, 0.35);
      --accent-glow: rgba(255, 122, 69, 0.38);
      --card-bg: rgba(18, 22, 32, 0.82);
      --card-highlight: rgba(255, 255, 255, 0.055);
      --header-bg: rgba(9, 11, 16, 0.72);
      --backdrop-grid: rgba(255, 255, 255, 0.055);
      --backdrop-glow: rgba(255, 122, 69, 0.11);
      --backdrop-glow-soft: rgba(255, 122, 69, 0.045);
      --shadow: 0 1px 0 rgba(255, 255, 255, 0.03) inset,
        0 2px 6px rgba(0, 0, 0, 0.25), 0 24px 64px -12px rgba(0, 0, 0, 0.6);
      --code-tag: #ff9163;
      --code-attr: #f5c46b;
      --code-str: #8fd19e;
      --code-prop: #7cb8ff;
      --code-punct: #6d7789;
      --ease-out: cubic-bezier(0.22, 1, 0.36, 1);
      --ease-spring: cubic-bezier(0.34, 1.4, 0.64, 1);
      --font-mono: 'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    }

    :root[data-theme='light'] {
      --bg: #f4f5f8;
      --bg-raised: #ffffff;
      --surface: #ffffff;
      --surface-2: #f0f2f6;
      --border: #dfe3ea;
      --border-strong: #c8cfda;
      --text: #171a21;
      --muted: #5b6474;
      --dim: #5f6877;
      --accent: #de5a22;
      --accent-strong: #c44a17;
      --accent-soft: rgba(222, 90, 34, 0.12);
      --accent-border: rgba(222, 90, 34, 0.35);
      --accent-glow: rgba(222, 90, 34, 0.3);
      --card-bg: rgba(255, 255, 255, 0.86);
      --card-highlight: rgba(255, 255, 255, 0.9);
      --header-bg: rgba(244, 245, 248, 0.75);
      --backdrop-grid: rgba(23, 28, 38, 0.055);
      --backdrop-glow: rgba(222, 90, 34, 0.09);
      --backdrop-glow-soft: rgba(222, 90, 34, 0.04);
      --shadow: 0 1px 0 rgba(255, 255, 255, 0.9) inset,
        0 1px 3px rgba(23, 28, 38, 0.06), 0 20px 48px -14px rgba(23, 28, 38, 0.18);
      --code-tag: #c44a17;
      --code-attr: #9a6a00;
      --code-str: #24804a;
      --code-prop: #2f6bc4;
      --code-punct: #79828f;
    }

    * { box-sizing: border-box; }

    html { color-scheme: dark; scroll-behavior: smooth; }
    html[data-theme='light'] { color-scheme: light; }

    body {
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font-family: Manrope, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      line-height: 1.6;
      -webkit-font-smoothing: antialiased;
      overflow-x: hidden;
    }

    a { color: var(--accent); text-decoration: none; transition: color 0.18s var(--ease-out); }
    a:hover { color: var(--accent-strong); }

    :focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }

    ::selection { background: rgba(255, 122, 69, 0.32); }

    .backdrop {
      position: fixed;
      inset: 0;
      z-index: 0;
      pointer-events: none;
      background:
        radial-gradient(900px 520px at 50% -12%, var(--backdrop-glow), transparent 70%),
        radial-gradient(640px 480px at 100% 105%, var(--backdrop-glow-soft), transparent 70%);
    }

    .backdrop::before {
      content: '';
      position: absolute;
      inset: 0;
      background-image:
        linear-gradient(var(--backdrop-grid) 1px, transparent 1px),
        linear-gradient(90deg, var(--backdrop-grid) 1px, transparent 1px);
      background-size: 44px 44px;
      background-position: center top;
      -webkit-mask-image: radial-gradient(ellipse 75% 65% at 50% 28%, #000 25%, transparent 78%);
      mask-image: radial-gradient(ellipse 75% 65% at 50% 28%, #000 25%, transparent 78%);
    }

    .shell { position: relative; z-index: 1; }

    .top {
      position: sticky;
      top: 0;
      z-index: 10;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      flex-wrap: wrap;
      padding: 14px clamp(20px, 5vw, 64px);
      border-bottom: 1px solid transparent;
      transition: background-color 0.3s var(--ease-out), border-color 0.3s var(--ease-out);
    }

    .top.is-scrolled {
      border-bottom-color: var(--border);
      background: var(--header-bg);
      -webkit-backdrop-filter: blur(14px) saturate(1.2);
      backdrop-filter: blur(14px) saturate(1.2);
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

    .brand:hover { color: var(--text); }

    .mark {
      display: grid;
      place-items: center;
      width: 30px;
      height: 30px;
      border-radius: 9px;
      background: var(--accent);
      color: #15100d;
      font-family: var(--font-mono);
      font-weight: 700;
      box-shadow: 0 6px 18px -6px var(--accent-glow), inset 0 1px 0 rgba(255, 255, 255, 0.28);
      transition: transform 0.5s var(--ease-spring);
    }

    .brand:hover .mark { transform: rotate(-12deg) scale(1.08); }

    nav { display: flex; gap: 10px; flex-wrap: wrap; }

    .btn {
      position: relative;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 8px;
      padding: 10px 16px;
      border: 1px solid transparent;
      border-radius: 10px;
      font-size: 14px;
      font-weight: 600;
      line-height: 1;
      white-space: nowrap;
      transition: background-color 0.18s var(--ease-out), border-color 0.18s var(--ease-out),
        color 0.18s var(--ease-out), box-shadow 0.32s var(--ease-out),
        transform 0.45s var(--ease-spring);
    }

    .btn:active { transform: scale(0.98); transition-duration: 0.08s; }

    .btn-primary {
      background: var(--accent);
      color: #15100d;
      box-shadow: 0 1px 0 rgba(255, 255, 255, 0.18) inset;
    }

    .btn-primary:hover {
      background: var(--accent-strong);
      color: #15100d;
    }

    .btn-ghost { border-color: var(--border); color: var(--muted); background: transparent; }
    .btn-ghost:hover { color: var(--text); border-color: var(--border-strong); background: var(--surface); }
    .btn-lg { padding: 14px 24px; border-radius: 11px; font-size: 15px; }

    .ripple-host {
      position: absolute;
      inset: 0;
      overflow: hidden;
      border-radius: inherit;
      pointer-events: none;
    }

    .ripple {
      position: absolute;
      border-radius: 50%;
      background: currentColor;
      transform: scale(0);
      opacity: 0;
    }

    main {
      max-width: 1120px;
      margin: 0 auto;
      padding: 56px clamp(20px, 5vw, 48px) 40px;
    }

    .hero {
      display: grid;
      grid-template-columns: minmax(0, 1fr) minmax(0, 1.05fr);
      align-items: center;
      gap: clamp(32px, 5vw, 64px);
      margin-bottom: 104px;
    }

    h1 {
      margin: 0 0 20px;
      font-size: clamp(34px, 5vw, 56px);
      line-height: 1.06;
      letter-spacing: -0.04em;
    }

    @property --line {
      syntax: '<percentage>';
      inherits: false;
      initial-value: 100%;
    }

    .accent-word { color: var(--accent); }

    .accent-word .split-word,
    .no-split .accent-word {
      background: linear-gradient(var(--accent-border), var(--accent-border)) no-repeat
        left 92% / var(--line, 100%) 0.11em;
    }

    .split-word { display: inline-block; }

    .lead {
      max-width: 52ch;
      margin: 0 0 30px;
      color: var(--muted);
      font-size: 17px;
    }

    .actions { display: flex; gap: 12px; flex-wrap: wrap; }

    .window {
      overflow: hidden;
      border: 1px solid var(--border);
      border-radius: 16px;
      background: var(--card-bg);
      box-shadow: var(--shadow);
      -webkit-backdrop-filter: blur(14px) saturate(1.2);
      backdrop-filter: blur(14px) saturate(1.2);
    }

    .window-bar {
      display: flex;
      align-items: center;
      gap: 10px;
      padding: 10px 14px;
      border-bottom: 1px solid var(--border);
      background: var(--surface-2);
    }

    .dots { display: flex; gap: 6px; }
    .dots i { width: 9px; height: 9px; border-radius: 50%; background: var(--border-strong); }
    .dots i:first-child { background: var(--accent); }

    .tabs { display: flex; gap: 4px; font-family: var(--font-mono); font-size: 11.5px; }

    .tab {
      padding: 4px 9px;
      border-radius: 6px;
      color: var(--dim);
    }

    .tab.is-active { background: var(--bg-raised); color: var(--text); }

    .presence {
      display: flex;
      margin-left: auto;
    }

    .avatar {
      display: grid;
      place-items: center;
      width: 22px;
      height: 22px;
      margin-left: -6px;
      border: 2px solid var(--surface-2);
      border-radius: 50%;
      color: #15100d;
      font-size: 10px;
      font-weight: 800;
    }

    .window-body {
      display: grid;
      grid-template-columns: minmax(0, 1.25fr) minmax(0, 1fr);
      min-height: 248px;
    }

    .code {
      position: relative;
      margin: 0;
      padding: 16px 14px;
      border-right: 1px solid var(--border);
      font-family: var(--font-mono);
      font-size: 12.5px;
      line-height: 1.75;
      white-space: pre;
      overflow: hidden;
      color: var(--text);
    }

    .ln {
      display: inline-block;
      width: 18px;
      margin-right: 10px;
      color: var(--dim);
      opacity: 0.55;
      text-align: right;
      user-select: none;
    }

    .t-tag { color: var(--code-tag); }
    .t-attr { color: var(--code-attr); }
    .t-str { color: var(--code-str); }
    .t-prop { color: var(--code-prop); }
    .t-punct { color: var(--code-punct); }

    .caret {
      display: inline-block;
      width: 2px;
      height: 1.15em;
      margin-left: 1px;
      vertical-align: -0.2em;
      background: #5fb3ff;
      animation: blink 1s steps(1) infinite;
    }

    .caret-tag {
      position: relative;
      display: inline-block;
      width: 0;
      vertical-align: top;
    }

    .caret-tag b {
      position: absolute;
      bottom: 1.35em;
      left: -1px;
      padding: 1px 6px;
      border-radius: 5px 5px 5px 0;
      background: #5fb3ff;
      color: #0b1220;
      font-family: Manrope, sans-serif;
      font-size: 10px;
      font-weight: 700;
      white-space: nowrap;
    }

    @keyframes blink { 50% { opacity: 0; } }

    .preview {
      display: flex;
      flex-direction: column;
      background: var(--bg-raised);
    }

    .preview-bar {
      display: flex;
      align-items: center;
      gap: 6px;
      padding: 7px 10px;
      border-bottom: 1px solid var(--border);
      color: var(--dim);
      font-family: var(--font-mono);
      font-size: 10.5px;
    }

    .preview-url {
      flex: 1;
      padding: 3px 8px;
      border-radius: 5px;
      background: var(--surface-2);
    }

    .preview-page {
      flex: 1;
      display: grid;
      place-items: center;
      align-content: center;
      gap: 12px;
      padding: 18px;
      text-align: center;
    }

    .preview-title {
      margin: 0;
      font-size: 17px;
      font-weight: 800;
      letter-spacing: -0.02em;
      transition: color 0.5s var(--ease-out);
    }

    .preview-btn {
      padding: 8px 16px;
      border: 0;
      border-radius: 999px;
      background: var(--border-strong);
      color: var(--text);
      font: inherit;
      font-size: 12.5px;
      font-weight: 700;
      transition: background-color 0.6s var(--ease-out), color 0.6s var(--ease-out),
        transform 0.6s var(--ease-spring), box-shadow 0.6s var(--ease-out);
    }

    .preview.is-styled .preview-btn {
      background: var(--accent);
      color: #15100d;
      transform: scale(1.06);
      box-shadow: 0 10px 24px -10px var(--accent-glow);
    }

    .status {
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 8px 14px;
      border-top: 1px solid var(--border);
      color: var(--dim);
      font-size: 11.5px;
    }

    .status-dot { width: 6px; height: 6px; border-radius: 50%; background: #5fb37a; }

    section.block { margin-bottom: 96px; }

    .eyebrow {
      display: block;
      margin-bottom: 10px;
      color: var(--accent);
      font-size: 12px;
      font-weight: 700;
      letter-spacing: 0.1em;
      text-transform: uppercase;
    }

    h2 {
      margin: 0 0 12px;
      font-size: clamp(26px, 3.4vw, 36px);
      line-height: 1.15;
      letter-spacing: -0.03em;
    }

    .section-lead {
      max-width: 60ch;
      margin: 0 0 32px;
      color: var(--muted);
    }

    .grid {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 14px;
    }

    .card {
      position: relative;
      isolation: isolate;
      padding: 22px;
      border: 1px solid var(--border);
      border-radius: 16px;
      background: var(--card-bg);
      box-shadow: 0 1px 0 var(--card-highlight) inset;
      -webkit-backdrop-filter: blur(12px);
      backdrop-filter: blur(12px);
      transition: transform 0.5s var(--ease-spring), border-color 0.3s var(--ease-out),
        box-shadow 0.3s var(--ease-out);
    }

    .card:hover {
      transform: translateY(-3px);
      border-color: var(--border-strong);
      box-shadow: 0 1px 0 var(--card-highlight) inset, 0 18px 40px -22px rgba(0, 0, 0, 0.6);
    }

    .icon {
      display: grid;
      place-items: center;
      width: 40px;
      height: 40px;
      margin-bottom: 16px;
      border: 1px solid var(--accent-border);
      border-radius: 11px;
      background: var(--accent-soft);
      color: var(--accent);
      transition: transform 0.5s var(--ease-spring);
    }

    .card:hover .icon { transform: scale(1.08) rotate(-6deg); }

    .card h3 { margin: 0 0 8px; font-size: 16px; letter-spacing: -0.01em; }
    .card p { margin: 0; color: var(--muted); font-size: 14px; }

    .steps {
      position: relative;
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 14px;
      margin: 0;
      padding: 0;
      list-style: none;
    }

    .steps-line {
      position: absolute;
      top: 21px;
      left: 22px;
      right: calc((100% - 42px) / 4 - 22px);
      height: 2px;
      border-radius: 2px;
      background: var(--border);
      overflow: hidden;
    }

    .steps-line i {
      display: block;
      height: 100%;
      background: var(--accent);
      transform-origin: left center;
    }

    .step { position: relative; }

    .step-num {
      position: relative;
      z-index: 1;
      display: grid;
      place-items: center;
      width: 44px;
      height: 44px;
      margin-bottom: 16px;
      border: 1px solid var(--accent-border);
      border-radius: 50%;
      background: var(--bg);
      color: var(--accent);
      font-family: var(--font-mono);
      font-weight: 700;
    }

    .step h3 { margin: 0 0 6px; font-size: 15.5px; }
    .step p { margin: 0; color: var(--muted); font-size: 14px; }

    .tech {
      display: grid;
      grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
      gap: 14px;
    }

    .chips { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 4px; }

    .chip {
      padding: 6px 12px;
      border: 1px solid var(--border);
      border-radius: 999px;
      background: var(--surface-2);
      color: var(--text);
      font-size: 13px;
      font-weight: 600;
      transition: border-color 0.3s var(--ease-out), color 0.3s var(--ease-out),
        transform 0.45s var(--ease-spring);
    }

    .chip:hover { border-color: var(--accent-border); color: var(--accent); transform: translateY(-2px); }

    .tech-row + .tech-row { margin-top: 18px; }

    .tech-label {
      margin: 0 0 8px;
      color: var(--dim);
      font-size: 12px;
      font-weight: 700;
      letter-spacing: 0.06em;
      text-transform: uppercase;
    }

    .cta {
      text-align: center;
      padding: clamp(32px, 6vw, 56px) 24px;
    }

    .cta h2 { margin-bottom: 10px; }
    .cta p { max-width: 48ch; margin: 0 auto 26px; color: var(--muted); }
    .cta .actions { justify-content: center; }

    footer {
      position: relative;
      z-index: 1;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      flex-wrap: wrap;
      padding: 24px clamp(20px, 5vw, 64px);
      border-top: 1px solid var(--border);
      color: var(--dim);
      font-size: 13px;
    }

    .js [data-reveal]:not(.is-in) { opacity: 0; }

    @media (max-width: 900px) {
      .hero { grid-template-columns: minmax(0, 1fr); }
      .grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .steps { grid-template-columns: repeat(2, minmax(0, 1fr)); row-gap: 28px; }
      .steps-line { display: none; }
      .tech { grid-template-columns: minmax(0, 1fr); }
    }

    @media (max-width: 600px) {
      .top { padding: 12px 16px; }
      footer { padding: 20px 16px; }
      .top nav .btn-ghost { display: none; }
      main { padding: 32px 16px 24px; }
      .hero { margin-bottom: 72px; }
      .window-body { grid-template-columns: minmax(0, 1fr); }
      .code { border-right: 0; border-bottom: 1px solid var(--border); font-size: 11.5px; }
      .tabs .tab:not(.is-active) { display: none; }
      .steps { grid-template-columns: minmax(0, 1fr); }
      .grid { grid-template-columns: minmax(0, 1fr); }
      section.block { margin-bottom: 72px; }
      .actions .btn { flex: 1; }
    }

    @media (prefers-reduced-motion: reduce) {
      *, *::before, *::after {
        animation-duration: 0.01ms !important;
        animation-iteration-count: 1 !important;
        transition-duration: 0.01ms !important;
        scroll-behavior: auto !important;
      }
      .js [data-reveal] { opacity: 1; }
    }
  </style>
</head>
<body>
  <div class="backdrop" aria-hidden="true"></div>

  <div class="shell">
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
        <div>
          <h1 data-split>Совместное редактирование кода <span class="accent-word">в реальном времени</span></h1>
          <p class="lead" data-reveal data-delay="420">
            Peerlessons — self-hosted веб-приложение для совместной работы над кодом.
            Участники открывают одну комнату, видят один и тот же проект из файлов
            HTML, CSS и JavaScript и наблюдают за изменениями, выделениями и кареткой
            редактора.
          </p>
          <div class="actions" data-reveal data-delay="520">
            <a class="btn btn-primary btn-lg" href="/register">Создать аккаунт</a>
            <a class="btn btn-ghost btn-lg" href="/login">Войти</a>
          </div>
        </div>

        <div class="window" data-reveal data-delay="260" aria-label="Пример комнаты: участник редактирует код, предпросмотр обновляется" role="img">
          <div class="window-bar">
            <span class="dots"><i></i><i></i><i></i></span>
            <span class="tabs">
              <span class="tab">index.html</span>
              <span class="tab is-active">style.css</span>
              <span class="tab">main.js</span>
            </span>
            <span class="presence">
              <span class="avatar" style="background:#5fb3ff">А</span>
              <span class="avatar" style="background:#ff7a45">М</span>
              <span class="avatar" style="background:#8fd19e">К</span>
            </span>
          </div>
          <div class="window-body">
            <pre class="code" aria-hidden="true"><span class="ln">1</span><span class="t-tag">.cta</span> <span class="t-punct">{</span>
<span class="ln">2</span>  <span class="t-prop">padding</span><span class="t-punct">:</span> <span class="t-str">8px 16px</span><span class="t-punct">;</span>
<span class="ln">3</span>  <span class="t-prop">border-radius</span><span class="t-punct">:</span> <span class="t-str">999px</span><span class="t-punct">;</span>
<span class="ln">4</span>  <span data-typed></span><span class="caret-tag"><b>Анна</b></span><span class="caret"></span>
<span class="ln">5</span><span class="t-punct">}</span></pre>
            <div class="preview" aria-hidden="true">
              <div class="preview-bar">
                <span class="preview-url">preview / index.html</span>
              </div>
              <div class="preview-page">
                <p class="preview-title">Привет, класс!</p>
                <button class="preview-btn" type="button" tabindex="-1">Начать урок</button>
              </div>
            </div>
          </div>
          <div class="status"><span class="status-dot"></span> Редактирует Анна · 3 участника</div>
        </div>
      </section>

      <section class="block" aria-labelledby="featuresTitle">
        <span class="eyebrow" data-reveal>Возможности</span>
        <h2 id="featuresTitle" data-reveal data-delay="60">Всё, что нужно для занятия</h2>
        <p class="section-lead" data-reveal data-delay="120">
          Один редактор за раз, остальные видят каждое изменение. Без установки — достаточно браузера.
        </p>
        <div class="grid" data-stagger>
          <article class="card">
            <span class="icon"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M10 13a5 5 0 0 0 7.5.5l3-3a5 5 0 0 0-7-7l-1.7 1.7"/><path d="M14 11a5 5 0 0 0-7.5-.5l-3 3a5 5 0 0 0 7 7l1.7-1.7"/></svg></span>
            <h3>Комнаты по ссылке</h3>
            <p>Уникальный адрес комнаты и мгновенное подключение по WebSocket.</p>
          </article>
          <article class="card">
            <span class="icon"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M16 18l6-6-6-6M8 6l-6 6 6 6"/></svg></span>
            <h3>Monaco Editor</h3>
            <p>Подсветка синтаксиса, автодополнение и Emmet для HTML, CSS и JavaScript.</p>
          </article>
          <article class="card">
            <span class="icon"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M18 11V6a2 2 0 0 0-4 0M14 10V4a2 2 0 0 0-4 0v2M10 10.5V6a2 2 0 0 0-4 0v8"/><path d="M18 8a2 2 0 1 1 4 0v6a8 8 0 0 1-8 8h-2c-2.8 0-4.5-.86-5.99-2.34l-3.6-3.6a2 2 0 0 1 2.83-2.82L7 15"/></svg></span>
            <h3>Передача прав</h3>
            <p>Один участник редактирует, остальные наблюдают. Ведущий выдаёт права поднявшему руку и забирает их.</p>
          </article>
          <article class="card">
            <span class="icon"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="2" y="3" width="20" height="14" rx="2"/><path d="M8 21h8M12 17v4"/></svg></span>
            <h3>Живой предпросмотр</h3>
            <p>Мини-браузер с вкладками и панелью разработчика: консоль, дерево DOM и сеть.</p>
          </article>
          <article class="card">
            <span class="icon"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 4l7.07 17 2.51-7.39L21 11.07z"/></svg></span>
            <h3>Удалённые курсоры</h3>
            <p>Видно выделение и каретку текущего редактора в реальном времени.</p>
          </article>
          <article class="card">
            <span class="icon"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg></span>
            <h3>Чат комнаты</h3>
            <p>Упоминания, реакции, код-блоки, закреплённые сообщения и индикатор «печатает».</p>
          </article>
        </div>
      </section>

      <section class="block" aria-labelledby="howTitle">
        <span class="eyebrow" data-reveal>Как это работает</span>
        <h2 id="howTitle" data-reveal data-delay="60">Четыре шага до общего кода</h2>
        <p class="section-lead" data-reveal data-delay="120">Код сохраняется автоматически, а права редактирования переходят по поднятой руке.</p>
        <ol class="steps" data-steps>
          <li class="steps-line" aria-hidden="true"><i></i></li>
          <li class="step">
            <span class="step-num">1</span>
            <h3>Создайте комнату</h3>
            <p>Зарегистрируйтесь и дайте комнате название — адрес появится сразу.</p>
          </li>
          <li class="step">
            <span class="step-num">2</span>
            <h3>Пригласите участников</h3>
            <p>Поделитесь ссылкой: все увидят файлы, участников и курсор редактора.</p>
          </li>
          <li class="step">
            <span class="step-num">3</span>
            <h3>Передавайте права</h3>
            <p>Участник поднимает руку, ведущий выдаёт ему редактор и забирает обратно.</p>
          </li>
          <li class="step">
            <span class="step-num">4</span>
            <h3>Смотрите результат</h3>
            <p>Предпросмотр обновляется у всех, код сохраняется в базе.</p>
          </li>
        </ol>
      </section>

      <section class="block" aria-labelledby="techTitle">
        <span class="eyebrow" data-reveal>Под капотом</span>
        <h2 id="techTitle" data-reveal data-delay="60">Технологии и лицензия</h2>
        <p class="section-lead" data-reveal data-delay="120">Разворачивается на своём сервере: статический фронтенд, FastAPI и PostgreSQL.</p>
        <div class="tech" data-stagger>
          <div class="card">
            <div class="tech-row">
              <p class="tech-label">Backend</p>
              <div class="chips"><span class="chip">Python</span><span class="chip">FastAPI</span><span class="chip">SQLAlchemy</span><span class="chip">PostgreSQL</span></div>
            </div>
            <div class="tech-row">
              <p class="tech-label">Frontend</p>
              <div class="chips"><span class="chip">Vue 3</span><span class="chip">Monaco Editor</span><span class="chip">Vite</span></div>
            </div>
          </div>
          <div class="card">
            <div class="tech-row">
              <p class="tech-label">Realtime и развёртывание</p>
              <div class="chips"><span class="chip">WebSocket</span><span class="chip">Nginx</span><span class="chip">systemd</span><span class="chip">Fedora/Linux</span></div>
            </div>
            <div class="tech-row">
              <p class="tech-label">Лицензия</p>
              <div class="chips"><span class="chip">GNU GPL v3.0</span></div>
            </div>
          </div>
        </div>
      </section>

      <section class="block card cta" data-reveal aria-labelledby="ctaTitle">
        <h2 id="ctaTitle">Готовы писать код вместе?</h2>
        <p>Создайте аккаунт и откройте первую комнату за минуту.</p>
        <div class="actions">
          <a class="btn btn-primary btn-lg" href="/register">Создать аккаунт</a>
          <a class="btn btn-ghost btn-lg" href="/login">Войти</a>
        </div>
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
  </div>

  <script>
    (function () {
      var root = document.documentElement;
      var reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
      var fine = window.matchMedia && window.matchMedia('(hover: hover) and (pointer: fine)').matches;
      var EASE = 'cubic-bezier(0.22, 1, 0.36, 1)';

      if (!reduce) root.classList.add('js');

      function run(el, frames, opts) {
        if (!el || !el.animate || reduce) return;
        var anim = el.animate(frames, opts);
        setTimeout(function () {
          try { if (anim.playState === 'running') anim.finish(); } catch (e) {}
        }, (opts.delay || 0) + opts.duration + 150);
      }

      function reveal(el, delay, from) {
        el.style.opacity = '';
        el.classList.add('is-in');
        run(el, [
          { opacity: 0, transform: from || 'translate3d(0, 16px, 0)', filter: 'blur(6px)' },
          { opacity: 1, transform: 'translate3d(0, 0, 0)', filter: 'blur(0px)' }
        ], { duration: 680, delay: delay || 0, easing: EASE, fill: 'backwards' });
      }

      function splitWords(node, out) {
        Array.prototype.slice.call(node.childNodes).forEach(function (child) {
          if (child.nodeType === 3) {
            var parts = child.textContent.split(/(\\s+)/);
            if (!child.textContent.trim()) return;
            var frag = document.createDocumentFragment();
            parts.forEach(function (part) {
              if (!part) return;
              if (!part.trim()) { frag.appendChild(document.createTextNode(part)); return; }
              var span = document.createElement('span');
              span.className = 'split-word';
              span.setAttribute('aria-hidden', 'true');
              span.textContent = part;
              frag.appendChild(span);
              out.push(span);
            });
            child.parentNode.replaceChild(frag, child);
          } else if (child.nodeType === 1) {
            splitWords(child, out);
          }
        });
      }

      var title = document.querySelector('[data-split]');
      if (title && !reduce) {
        title.setAttribute('aria-label', title.textContent.replace(/\\s+/g, ' ').trim());
        var words = [];
        splitWords(title, words);
        words.forEach(function (word, i) {
          run(word, [
            { opacity: 0, transform: 'translate3d(0, 22px, 0)', filter: 'blur(10px)' },
            { opacity: 1, transform: 'translate3d(0, 0, 0)', filter: 'blur(0px)' }
          ], { duration: 820, delay: 80 + i * 65, easing: EASE, fill: 'backwards' });
        });
        title.querySelectorAll('.accent-word .split-word').forEach(function (word, i) {
          run(word, [{ '--line': '0%' }, { '--line': '100%' }],
            { duration: 520, delay: 760 + i * 160, easing: EASE, fill: 'backwards' });
        });
      } else if (title) {
        title.classList.add('no-split');
      }

      var targets = [];
      document.querySelectorAll('[data-reveal]').forEach(function (el) {
        targets.push({ el: el, run: function () { reveal(el, Number(el.getAttribute('data-delay')) || 0); } });
      });
      document.querySelectorAll('[data-stagger]').forEach(function (group) {
        var items = Array.prototype.slice.call(group.children);
        if (!reduce) items.forEach(function (item) { item.style.opacity = '0'; });
        targets.push({ el: group, run: function () {
          items.forEach(function (item, i) { reveal(item, i * 70); });
        } });
      });
      document.querySelectorAll('[data-steps]').forEach(function (list) {
        var steps = list.querySelectorAll('.step');
        var line = list.querySelector('.steps-line i');
        if (!reduce) steps.forEach(function (s) { s.style.opacity = '0'; });
        targets.push({ el: list, run: function () {
          steps.forEach(function (step, i) { reveal(step, 150 + i * 180, 'translate3d(0, 14px, 0) scale(0.96)'); });
          run(line, [{ transform: 'scaleX(0)' }, { transform: 'scaleX(1)' }],
            { duration: 1100, delay: 120, easing: EASE, fill: 'backwards' });
        } });
      });

      function inView(el) {
        if (!window.innerHeight) return true;
        var r = el.getBoundingClientRect();
        return r.top < window.innerHeight && r.bottom > 0;
      }

      if (reduce || !('IntersectionObserver' in window)) {
        document.querySelectorAll('[data-reveal], [data-stagger] > *, [data-steps] .step').forEach(function (el) {
          el.style.opacity = '';
          el.classList.add('is-in');
        });
      } else {
        var io = new IntersectionObserver(function (entries) {
          entries.forEach(function (entry) {
            if (!entry.isIntersecting) return;
            io.unobserve(entry.target);
            var t = entry.target.__reveal;
            if (t) t();
          });
        }, { rootMargin: '0px 0px -8% 0px', threshold: 0.08 });
        targets.forEach(function (t) {
          if (inView(t.el)) { t.run(); return; }
          t.el.__reveal = t.run;
          io.observe(t.el);
        });
      }

      var header = document.querySelector('.top');
      function onScroll() { header.classList.toggle('is-scrolled', window.scrollY > 8); }
      window.addEventListener('scroll', onScroll, { passive: true });
      onScroll();

      var typed = document.querySelector('[data-typed]');
      var preview = document.querySelector('.preview');
      var LINE = [
        ['t-prop', 'background'], ['t-punct', ':'], ['', ' '], ['t-str', 'var(--accent)'], ['t-punct', ';']
      ];
      var full = LINE.map(function (p) { return p[1]; }).join('');

      function render(count) {
        var html = '';
        var left = count;
        LINE.forEach(function (part) {
          if (left <= 0) return;
          var text = part[1].slice(0, left);
          left -= part[1].length;
          html += part[0] ? '<span class="' + part[0] + '">' + text + '</span>' : text;
        });
        typed.innerHTML = html;
      }

      function typeLoop() {
        var i = 0;
        preview.classList.remove('is-styled');
        render(0);
        var timer = setInterval(function () {
          i += 1;
          render(i);
          if (i >= full.length) {
            clearInterval(timer);
            preview.classList.add('is-styled');
            setTimeout(function () {
              var j = full.length;
              var erase = setInterval(function () {
                j -= 1;
                render(j);
                if (j <= 0) { clearInterval(erase); setTimeout(typeLoop, 700); }
              }, 28);
            }, 2600);
          }
        }, 70 + Math.round(Math.random() * 30));
      }

      if (typed && preview) {
        if (reduce) { render(full.length); preview.classList.add('is-styled'); }
        else setTimeout(typeLoop, 1200);
      }

      document.addEventListener('pointerdown', function (e) {
        if (reduce || e.button !== 0) return;
        var btn = e.target.closest && e.target.closest('.btn');
        if (!btn) return;
        var r = btn.getBoundingClientRect();
        var size = Math.hypot(r.width, r.height) * 2;
        var host = document.createElement('span');
        host.className = 'ripple-host';
        var ripple = document.createElement('span');
        ripple.className = 'ripple';
        ripple.style.width = ripple.style.height = size + 'px';
        ripple.style.left = (e.clientX - r.left - size / 2) + 'px';
        ripple.style.top = (e.clientY - r.top - size / 2) + 'px';
        host.appendChild(ripple);
        btn.appendChild(host);
        var anim = ripple.animate([{ transform: 'scale(0)', opacity: 0.3 }, { transform: 'scale(1)', opacity: 0 }],
          { duration: 700, easing: EASE });
        anim.onfinish = function () { host.remove(); };
        setTimeout(function () { host.remove(); }, 900);
      }, { passive: true });
    })();
  </script>
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
