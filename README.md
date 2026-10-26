<div align="center">

# Peerlessons

**Совместное редактирование кода в реальном времени — для занятий, парного программирования и код-ревью.**

[Сайт](https://www.peerlessons.ru) · [Возможности](#возможности) · [Быстрый старт](#быстрый-старт) · [Развёртывание](#развёртывание-на-сервере-fedora) · [API](#api)

[![License: GPL-3.0](https://img.shields.io/badge/license-GPL--3.0-orange.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-3776AB.svg?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688.svg?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Vue 3](https://img.shields.io/badge/Vue-3-42B883.svg?logo=vuedotjs&logoColor=white)](https://vuejs.org/)
[![Vite](https://img.shields.io/badge/Vite-8-646CFF.svg?logo=vite&logoColor=white)](https://vite.dev/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15%2B-4169E1.svg?logo=postgresql&logoColor=white)](https://www.postgresql.org/)

</div>

## О проекте

Peerlessons — self-hosted веб-приложение для совместной работы над кодом. Участники открывают одну комнату, видят один и тот же проект из трёх файлов (`index.html`, `style.css`, `main.js`) и наблюдают за изменениями в реальном времени.

Редактирует всегда один человек. Ведущий комнаты может передать права участнику, который поднял руку, забрать их обратно или позволить редактору завершить работу самостоятельно. Остальные участники в это время видят код, выделения и каретку редактора, а также общий предпросмотр результата.

Проект рассчитан на самостоятельный хостинг: статический фронтенд, FastAPI-бэкенд и PostgreSQL.

## Возможности

- **Комнаты по ссылке** — уникальный UUID комнаты и мгновенное подключение по WebSocket.
- **Monaco Editor** — подсветка синтаксиса, автодополнение и Emmet для HTML, CSS и JavaScript.
- **Синхронизация в реальном времени** — изменения кода, активная вкладка и предпросмотр общие для всех участников.
- **Передача прав редактирования** — поднятая рука, выдача прав ведущим, возврат прав и завершение редактирования делегатом.
- **Один редактор за раз** — сервер принимает изменения кода только от текущего редактора.
- **Удалённые выделения и каретка** — видно, что именно выделил и где находится редактор.
- **Живой предпросмотр** — HTML/CSS/JS собираются в отдельном `iframe`; окном управляет только текущий редактор.
- **JWT-аутентификация** — access-токен на 15 минут, refresh-токен на 7 дней, автоматическое обновление и отзыв при выходе.
- **Защищённые маршруты** — неавторизованный пользователь отправляется на вход и возвращается на исходный путь после него.
- **Тёмный адаптивный интерфейс** — единая дизайн-система без градиентов и визуального шума.
- **Понятные ошибки** — ответы FastAPI/Pydantic (включая 422) превращаются в аккуратные сообщения на русском.

## Технологии

| Слой | Стек |
| --- | --- |
| Backend | Python 3.11+, FastAPI, Uvicorn, SQLAlchemy 2, PostgreSQL, python-jose, bcrypt, pydantic-settings |
| Frontend | Vue 3, Vue Router, Pinia, Axios, Monaco Editor, emmet-monaco-es, Vite |
| Realtime | WebSocket |
| Deploy | Nginx, systemd, Fedora/Linux |

## Архитектура

```mermaid
flowchart LR
    B["Браузер: Vue 3 + Monaco"] -->|HTTPS| N["Nginx"]
    N -->|"статика dist"| S["SPA"]
    N -->|"/api"| A["FastAPI + Uvicorn"]
    N -->|"/ws"| A
    A -->|"SQLAlchemy"| D[("PostgreSQL")]
```

- **Frontend** — SPA с клиентским роутингом. В dev-режиме Vite проксирует `/api` и `/ws` на бэкенд; в production это делает Nginx.
- **Backend** — REST для аутентификации и комнат, WebSocket для всего, что происходит внутри комнаты.
- **PostgreSQL** — пользователи, комнаты, код комнаты и refresh-сессии.
- **Состояние присутствия** (участники, руки, курсоры, предпросмотр, текущий редактор) хранится в памяти процесса и сбрасывается при рестарте. Код комнаты и текущий редактор сохраняются в БД.

## Как это работает

1. Пользователь регистрируется или входит и создаёт комнату.
2. Открывает `/room/<uuid>` — фронтенд подключается к `/ws/room/<uuid>?token=<access_token>`.
3. Сервер присылает полное состояние: файлы, активную вкладку, участников, текущего редактора, руки и курсоры.
4. Только текущий редактор может отправлять `code-update`; сервер рассылает изменения остальным.
5. Участник поднимает руку, ведущий выдаёт ему права. Редактор может завершить работу сам, ведущий — забрать права в любой момент.
6. Код сохраняется в БД с debounce (1.5 с) и принудительно при отключении.

## Структура репозитория

```text
Peerlessons/
├── backend/
│   ├── config.py              # настройки из .env
│   ├── database.py            # engine, SessionLocal, Base
│   ├── main.py                # FastAPI, REST, WebSocket, менеджер комнат
│   ├── models.py              # SQLAlchemy-модели
│   ├── schemas.py             # Pydantic-схемы
│   ├── security.py            # пароли, JWT, refresh-токены
│   └── .env.example
├── frontend/
│   ├── src/
│   │   ├── assets/main.css    # дизайн-система
│   │   ├── components/        # ErrorAlert
│   │   ├── router/index.js    # маршруты и guard
│   │   ├── utils/errors.js    # разбор ошибок API
│   │   ├── views/             # Home, Login, Register, CreateRoom, CodeRoom
│   │   ├── auth.js            # токены, refresh, axios-интерцепторы
│   │   ├── main.js
│   │   └── monaco-workers.js  # воркеры Monaco через Vite
│   ├── index.html
│   ├── package.json
│   └── vite.config.js
├── deploy/
│   ├── nginx.conf.example
│   └── peerlessons.service.example
├── requirements.txt
├── LICENSE
└── README.md
```

## Быстрый старт

### Требования

- Python **3.11+** (рекомендуется 3.12+)
- Node.js **22.18+** или **24.12+** (требование Vite 8)
- PostgreSQL **15+**
- npm

### 1. Клонирование

```bash
git clone https://github.com/RedCross321/Peerlessons.git
cd Peerlessons
```

### 2. PostgreSQL

Создайте роль и базу (значения можно изменить):

```bash
sudo -u postgres psql <<'SQL'
CREATE ROLE peerlessons LOGIN PASSWORD 'change-me';
CREATE DATABASE peerlessons OWNER peerlessons;
SQL
```

### 3. Бэкенд

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

cp backend/.env.example backend/.env
```

Сгенерируйте секрет и заполните `backend/.env`:

```bash
python -c "import secrets; print(secrets.token_urlsafe(64))"
```

```env
DATABASE_URL=postgresql+psycopg://peerlessons:change-me@localhost:5432/peerlessons
SECRET_KEY=вставьте-сгенерированное-значение
ACCESS_TOKEN_EXPIRE_MINUTES=15
REFRESH_TOKEN_EXPIRE_DAYS=7
```

Запуск:

```bash
cd backend
uvicorn main:app --reload
```

- API: `http://localhost:8000`
- Swagger UI: `http://localhost:8000/docs`
- Health-check: `http://localhost:8000/health`

При первом запуске таблицы создаются автоматически.

### 4. Фронтенд

В отдельном терминале:

```bash
cd frontend
npm install
npm run dev
```

Откройте `http://localhost:5173`. Vite уже настроен на проксирование `/api` и `/ws` на `http://localhost:8000`.

## Переменные окружения

Файл `backend/.env`:

| Переменная | Обязательна | По умолчанию | Назначение |
| --- | --- | --- | --- |
| `DATABASE_URL` | да | — | SQLAlchemy URL. Используйте драйвер `psycopg` (psycopg3) |
| `SECRET_KEY` | да | — | Подпись JWT. Не меняйте без необходимости |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | нет | `15` | Время жизни access-токена |
| `REFRESH_TOKEN_EXPIRE_DAYS` | нет | `7` | Время жизни refresh-токена |

## База данных

Таблицы создаются автоматически при старте (`Base.metadata.create_all`):

- `users` — аккаунты;
- `rooms` — комнаты, текущий код и текущий редактор;
- `room_participants` — модель участия (зарезервирована под расширение);
- `code_snapshots` — модель снапшотов (зарезервирована);
- `edit_requests` — модель запросов на редактирование (зарезервирована);
- `refresh_tokens` — refresh-сессии с возможностью отзыва.

## API

Базовый URL: `/api`. Авторизация — `Authorization: Bearer <access_token>`.

| Метод | Путь | Доступ | Описание |
| --- | --- | --- | --- |
| `GET` | `/health` | — | Проверка живости |
| `POST` | `/api/auth/register` | — | Регистрация, возвращает пару токенов и пользователя |
| `POST` | `/api/auth/login` | — | Вход по email и паролю |
| `POST` | `/api/auth/refresh` | refresh-токен | Новый access-токен |
| `POST` | `/api/auth/logout` | refresh-токен | Отзыв refresh-токена (204) |
| `GET` | `/api/me` | Bearer | Текущий пользователь |
| `POST` | `/api/room` | Bearer | Создать комнату |
| `GET` | `/api/room/{room_id}` | — | Получить комнату |
| `WS` | `/ws/room/{room_id}?token=...` | access-токен | Комната в реальном времени |

### Аутентификация

- Access-токен живёт 15 минут, refresh — 7 дней.
- Фронтенд обновляет access-токен заранее и повторяет запрос при `401`.
- Refresh-токен не ротируется при обновлении, чтобы не ломать параллельные вкладки.
- Выход отзывает refresh-токен в БД.

### WebSocket-протокол

Клиент → сервер:

| Тип | Назначение |
| --- | --- |
| `code-update` | Обновление файлов и активной вкладки (только текущий редактор) |
| `raise-hand` / `lower-hand` | Поднять или опустить руку |
| `grant-edit` | Выдать права участнику (только ведущий) |
| `revoke-edit` | Забрать права / завершить редактирование |
| `preview-toggle` | Открыть или закрыть предпросмотр (только текущий редактор) |
| `preview-refresh` | Перезагрузить предпросмотр |
| `cursor-update` / `cursor-clear` | Позиция курсора и выделение |
| `request-state` | Запросить полное состояние комнаты |

Сервер → клиент: `room-state`, `code-update`, `participants`, `editor-changed`, `hand-raised`, `hand-lowered`, `preview-toggle`, `preview-refresh`, `cursor-update`, `cursor-clear`, `user-left`.

---

Если проект оказался полезным — поставьте звезду. Вопросы и предложения — через Issues.
