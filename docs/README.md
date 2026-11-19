# NEXUS BOT — Documentación técnica

Esta carpeta es la referencia principal del proyecto. Si el código y estos documentos no coinciden, se corrige uno de los dos: no se improvisa.

| Documento | Contenido |
|---|---|
| [NEXUS_DATABASE_SPEC.md](NEXUS_DATABASE_SPEC.md) | Tablas, columnas, relaciones, índices, JSON de configuración, retención de datos |
| [NEXUS_API_SPEC.md](NEXUS_API_SPEC.md) | Endpoints, login con Discord, permisos, sincronización API → Redis → bot, seguridad |
| [NEXUS_UI_SPEC.md](NEXUS_UI_SPEC.md) | Sistema visual, rutas, páginas, componentes, estados e interacciones del dashboard |

Cada documento tiene dos niveles de detalle:

- **V1 (MVP):** especificado completo, listo para programar.
- **Fases 3 a 9:** especificado como referencia (qué tablas, páginas y endpoints existirán). Se detalla al empezar cada fase.

---

## 1. Decisiones tomadas

| Tema | Decisión | Motivo |
|---|---|---|
| Bot | Python 3.12 + discord.py 2.x | Versión de Python con mejor compatibilidad de librerías |
| API | FastAPI + Pydantic v2 | Validación automática, async, documentación OpenAPI |
| ORM / migraciones | SQLAlchemy 2 (async) + asyncpg + Alembic | Estándar en Python, migraciones versionadas |
| Base de datos | PostgreSQL 18 (Laragon en local) | Fuente de verdad; JSONB para configuración de módulos |
| Caché y avisos | Redis (Laragon en local) | Pub/Sub para avisar al bot, caché, rate limits |
| Tareas programadas | Tabla `scheduled_jobs` en PostgreSQL + worker | Sobrevive a reinicios; no hace falta una cola extra en V1 |
| Dashboard | Next.js (App Router) + TypeScript + Tailwind + shadcn/ui | Componentes accesibles y consistentes |
| Idiomas | Español e inglés desde V1 | Bot: archivos JSON; dashboard: next-intl |
| Login | Discord OAuth2 (scopes `identify guilds`) | Sesión en servidor con cookie httpOnly |
| Despliegue | Linux + HTTPS + Docker (fase 9) | En local no se usa Docker |

### Código compartido

El bot y la API comparten un paquete Python, **`nexus_core`**, para que nunca haya dos versiones distintas de la misma lógica:

- Modelos de base de datos (SQLAlchemy).
- Esquemas de configuración de cada módulo (Pydantic).
- Renderizado de variables (`{user}`, `{server}`…) y de embeds.
- Cálculo de permisos de Discord.
- Protocolo de sincronización por Redis.
- Textos del bot en español e inglés.

Así, la vista previa del dashboard, el botón "Enviar prueba" y el mensaje real del bot producen exactamente el mismo resultado.

---

## 2. Estructura de carpetas

```text
bot discord/
├── docs/                     ← estos documentos
├── core/                     ← paquete compartido nexus_core
│   ├── pyproject.toml
│   └── nexus_core/
│       ├── config.py         ← lectura de .env
│       ├── db/               ← engine, sesión, modelos
│       ├── modules/          ← esquemas Pydantic por módulo (welcome.py, …)
│       ├── messages/         ← MessageTemplate, variables, validación de límites
│       ├── discord/          ← permisos, cliente REST
│       ├── sync.py           ← eventos Redis
│       └── locales/          ← es.json, en.json (textos del bot)
├── bot/
│   ├── pyproject.toml
│   └── nexus_bot/
│       ├── main.py
│       ├── client.py         ← subclase de commands.Bot
│       ├── config_cache.py   ← caché de configuración por servidor
│       ├── sync_listener.py  ← escucha Redis
│       ├── worker.py         ← ejecuta scheduled_jobs
│       └── cogs/             ← welcome.py, general.py, …
├── api/
│   ├── pyproject.toml
│   └── nexus_api/
│       ├── main.py
│       ├── deps.py           ← sesión, usuario, permisos
│       ├── routers/          ← auth.py, guilds.py, modules.py, …
│       └── services/
├── migrations/               ← Alembic (alembic.ini en la raíz)
├── dashboard/                ← Next.js
│   ├── app/
│   ├── components/
│   ├── lib/
│   └── messages/             ← es.json, en.json (textos del dashboard)
├── tests/
├── .env                      ← secretos locales (NO se sube a git)
├── .env.example              ← plantilla sin secretos
└── .gitignore
```

## 3. Procesos en ejecución

| Proceso | Comando (local, desde la raíz del proyecto) | Puerto |
|---|---|---|
| PostgreSQL | Laragon | 5432 |
| Redis | Laragon (Menú → Redis) | 6379 |
| API | `.venv\Scripts\uvicorn nexus_api.main:app --port 8000` | 8000 |
| Bot + worker | `.venv\Scripts\python -m nexus_bot` | — |
| Dashboard | `npm --prefix dashboard run dev` | 3000 |

Otros comandos:

- Migraciones: `.venv\Scripts\alembic upgrade head`
- Pruebas: `.venv\Scripts\python -m pytest` (usan la base `nexus_test` y Redis db 15)
- Documentación interactiva de la API: http://localhost:8000/api/docs

El dashboard reenvía `/api/*` a `http://127.0.0.1:8000` (rewrite de Next.js). Para el navegador, todo vive en `localhost:3000`, así que no hace falta CORS y las cookies funcionan sin trucos.

## 4. Hoja de ruta

| Fase | Entregable | Estado |
|---|---|---|
| 0 | Plan técnico, base de datos, API, UI (estos documentos) | ✅ |
| 1 | Login, lista de servidores, layout, Overview, configuración general | ✅ |
| 2 | Welcome & Goodbye + editor de mensajes/embeds + vista previa | ✅ |
| 3 | Moderación, AutoMod, warnings, permisos del dashboard por rol, logs | ✅ |
| 4 | Autoroles, Reaction Roles, gestión de miembros | ✅ |
| 5 | Tickets, Suggestions, Polls, Giveaways, Starboard, comandos personalizados, anuncios programados | ✅ |
| 6 | Levels / XP, economía virtual | ✅ |
| 7 | Integraciones (YouTube, Twitch, RSS, GitHub), IA de moderación | ✅ |
| 8 | Analytics, plantillas, Quick Setup (Premium y notificaciones: pendientes de decidir) | ✅ |
| 9 | Seguridad, Docker, despliegue (docs/DEPLOY.md), páginas legales (borrador) | ✅ |

**V1 = fases 1 y 2.** Cada fase termina con pruebas antes de pasar a la siguiente.
