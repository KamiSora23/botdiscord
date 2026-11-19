# Despliegue de NEXUS BOT en el servidor (Docker + Cloudflare Tunnel)

En local se trabaja con Laragon. En el servidor todo corre en Docker, y el panel se publica con **Cloudflare Tunnel**:
Cloudflare pone el HTTPS, así que no hace falta certificado propio.

```
Internet ──HTTPS──> Cloudflare ──túnel──> cloudflared ──(red cloudflare_red)──> nexus-dashboard:3000
                                                                                   │  /api/* (red interna nexus)
                                                                                   ▼
                                                                        nexus-api:8000 ── nexus-db, nexus-redis
                                                                        nexus-bot ──────── Discord
```

**Redes:**
- Solo `nexus-dashboard` entra en `cloudflare_red`, y es el único que publica un puerto en el servidor (`NEXUS_PORT`,
  5010 por defecto), igual que tus otros proyectos.
- La API, el bot, PostgreSQL y Redis quedan en la red interna `nexus_internal`. No se ven desde el túnel ni desde tus
  otros contenedores.

| Contenedor | Qué es |
|---|---|
| `nexus-dashboard` | Panel web (Next.js) |
| `nexus-api` | API (FastAPI); el panel le reenvía `/api/*` |
| `nexus-bot` | El bot de Discord |
| `nexus-migrate` | Aplica las migraciones de la base de datos al arrancar y termina |
| `nexus-db` | PostgreSQL 18 (datos en el volumen `nexus_pgdata`) |
| `nexus-redis` | Redis (caché y mensajería panel ↔ bot) |

## 1. Requisitos

- Servidor Linux con Docker y Docker Compose. 2 GB de RAM bastan para empezar.
- Tu contenedor `cloudflared` conectado a la red externa `cloudflare_red`. Si la red no existe:
  `docker network create cloudflare_red`.

> **Seguridad del túnel:** el token del túnel da control total sobre él. No lo pongas en ningún archivo que se suba a
> git. Si alguna vez se ha visto en una captura o en un chat, **rótalo** en Cloudflare Zero Trust → Networks → Tunnels
> → tu túnel → *Refresh token*.

## 2. Preparar la configuración

1. Clona el proyecto en el servidor:
   ```bash
   git clone https://github.com/KamiSora23/botdiscord.git nexus && cd nexus
   ```
2. Crea `.env` a partir de la plantilla: `cp .env.example .env`. Este `.env` **nunca** se sube a git; ya está en
   `.gitignore`.
3. Rellénalo:

| Variable | Valor en producción |
|---|---|
| `ENV` | `production` |
| `DB_USER`, `DB_NAME` | `nexus` (o lo que quieras) |
| `DB_PASSWORD` | Contraseña larga aleatoria: `openssl rand -hex 24` |
| `NEXUS_PORT` | Puerto del servidor para el panel (5010 por defecto; cámbialo si está ocupado) |
| `DISCORD_CLIENT_ID`, `DISCORD_CLIENT_SECRET`, `DISCORD_BOT_TOKEN` | Los de tu aplicación de Discord (**rotados** antes del lanzamiento) |
| `DASHBOARD_URL` | `https://panel.tudominio.com` |
| `DISCORD_REDIRECT_URI` | `https://panel.tudominio.com/api/v1/auth/callback` |
| `ENCRYPTION_KEY` | Una clave **nueva** (ver el comentario en `.env.example`) |
| `DEV_GUILD_ID` | **Vacío** |
| `ANTHROPIC_API_KEY`, `TWITCH_*` | Opcionales |

`DATABASE_URL`, `REDIS_URL`, `ENV=production` y `TRUST_CLOUDFLARE=true` los pone `docker-compose.yml`, apuntando a
los contenedores.

4. En el [Developer Portal](https://discord.com/developers/applications) → OAuth2 → Redirects, añade
   `https://panel.tudominio.com/api/v1/auth/callback`.

> Si falta o está mal algo de lo anterior, la API y el bot **no arrancan** y dicen exactamente qué corregir en
> `docker compose logs api` y `docker compose logs bot`.

## 3. Publicar el panel en el túnel

En **Cloudflare Zero Trust → Networks → Tunnels → tu túnel → Public Hostname → Add**:

| Campo | Valor |
|---|---|
| Subdomain / Domain | `panel` / `tudominio.com` |
| Type | `HTTP` |
| URL | `nexus-dashboard:3000` |

Funciona porque `cloudflared` y `nexus-dashboard` comparten la red `cloudflare_red`, donde Docker resuelve el nombre
del contenedor. **Usa el puerto interno, 3000**, no el publicado (`NEXUS_PORT`). El publicado solo sirve para entrar
directamente por la IP del servidor, por ejemplo para pruebas.

Recomendado en Cloudflare para el dominio:
- SSL/TLS en *Full*.
- «Always Use HTTPS» activado.
- Sin caché en `/api/*` (por defecto Cloudflare no cachea JSON).

## 4. Arrancar

```bash
docker compose up -d --build
```

Se construyen las imágenes `nexus-backend` y `nexus-dashboard`, se aplican las migraciones (`nexus-migrate`) y
arrancan la base de datos, Redis, la API, el bot y el panel, en ese orden. Cada servicio espera a que el anterior
esté *healthy*.

Comprobar:

```bash
docker compose ps              # todos «healthy» (nexus-migrate sale con «Exited (0)», es normal)
docker compose logs -f bot     # «Conectado como …»
curl https://panel.tudominio.com/api/v1/health
```

## 5. Actualizar

```bash
git pull
docker compose up -d --build
```

Las migraciones se aplican solas antes de arrancar la API y el bot.

## 6. Copias de seguridad

Copia diaria conservando 14 días (`crontab -e`). Incluye las imágenes subidas desde el panel, porque se guardan en la
base de datos:

```bash
0 4 * * * cd /ruta/a/nexus && mkdir -p backups && docker compose exec -T db pg_dump -U nexus nexus | gzip > backups/nexus-$(date +\%F).sql.gz && find backups -name '*.sql.gz' -mtime +14 -delete
```

Restaurar: `gunzip -c backups/nexus-AAAA-MM-DD.sql.gz | docker compose exec -T db psql -U nexus nexus`.

## 7. Antes de hacerlo público

- [ ] Rota el token del bot, el client secret y el token del túnel si se han mostrado en alguna captura.
- [ ] Completa `/legal/terms` y `/legal/privacy` (`dashboard/app/legal/content.ts`): faltan tu nombre y contacto.
- [ ] Pon las URL de Términos y Privacidad en la ficha de la aplicación del Developer Portal.
- [ ] Revisa las condiciones de los intents privilegiados (Server Members, Message Content) y la verificación del bot,
  obligatoria a partir de 100 servidores.
- [ ] Si usas la IA de moderación, indica en la política que los mensajes analizados se envían a Anthropic.
- [ ] Firewall: con el túnel no hace falta abrir 80/443 ni `NEXUS_PORT` a internet. Deja solo SSH:
  `ufw allow 22/tcp && ufw enable`.

## 8. Si algo falla

| Síntoma | Qué revisar |
|---|---|
| `Falta DB_PASSWORD en .env` | Rellena `DB_PASSWORD` en `.env` |
| `nexus-api` o `nexus-bot` se reinician sin parar | `docker compose logs api`: «Configuración de producción incompleta» con la lista de lo que falta |
| Error 502 / «Bad gateway» de Cloudflare | `docker compose ps dashboard`; que `cloudflared` esté en `cloudflare_red` (`docker network inspect cloudflare_red`) y que el Public Hostname sea `nexus-dashboard:3000` |
| El login vuelve con error | `DISCORD_REDIRECT_URI` idéntico en `.env` y en el Developer Portal; `DISCORD_CLIENT_SECRET` correcto |
| «Bot desconectado» en el panel | `docker compose logs bot`: token inválido o intents sin activar |
| `network cloudflare_red declared as external, but could not be found` | `docker network create cloudflare_red` y reinicia tu `cloudflared` |
| `port is already allocated` | Cambia `NEXUS_PORT` en `.env` |
| Un servicio queda «unhealthy» | `docker compose restart <servicio>`; Docker solo reinicia solo lo que se cae del todo |
| Los cambios del panel tardan | Redis caído (`docker compose ps redis`); el bot se resincroniza igualmente en 5 minutos |
