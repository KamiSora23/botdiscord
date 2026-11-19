# Manual de NEXUS BOT

Guía completa para **administrar** NEXUS: qué hace cada parte, cómo se configura desde el panel, qué comandos hay
en Discord y quién puede usarlos. Al final hay una sección para **quien mantiene el servidor** (arranque, despliegue,
copias de seguridad).

> Versión del manual: noviembre de 2026. Si algo del panel no coincide con lo que ves aquí, manda captura.

---

## Índice

1. [Cómo está hecho NEXUS](#1-cómo-está-hecho-nexus)
2. [Primeros pasos](#2-primeros-pasos)
3. [Quién puede usar qué](#3-quién-puede-usar-qué)
4. [El panel, sección por sección](#4-el-panel-sección-por-sección)
5. [Mensajes, embeds y variables](#5-mensajes-embeds-y-variables)
6. [Imágenes](#6-imágenes)
7. [Comandos de Discord](#7-comandos-de-discord)
8. [Formatos de tiempo y fecha](#8-formatos-de-tiempo-y-fecha)
9. [Problemas frecuentes](#9-problemas-frecuentes)
10. [Para quien mantiene el servidor](#10-para-quien-mantiene-el-servidor)

---

## 1. Cómo está hecho NEXUS

| Pieza | Qué es | Dónde la ves |
|---|---|---|
| **Bot** | La cuenta *NEXUS* dentro de tu servidor: responde comandos, modera, da roles, envía mensajes. | Discord |
| **Panel** | La web donde se configura todo (módulos, mensajes, permisos, estadísticas). | `https://tu-dominio` (en local, `http://localhost:3000`) |
| **API** | El intermediario entre el panel, la base de datos y el bot. No se ve. | — |
| **Base de datos** (PostgreSQL) | Guarda la configuración, casos de moderación, niveles, economía, imágenes subidas… | — |
| **Redis** | Mensajería instantánea entre el panel y el bot (los cambios se aplican al momento). | — |

Lo que cambias en el panel llega al bot **en el acto**, sin reiniciar nada. Cada cambio queda apuntado en
**Avanzado → Historial** (quién, qué y cuándo).

---

## 2. Primeros pasos

1. **Invita a NEXUS** desde la portada del panel o con `/invitar`. Acepta todos los permisos que pide: cada módulo
   necesita los suyos.
2. **Sube el rol de NEXUS**: en Discord → *Ajustes del servidor → Roles*, arrastra **NEXUS** por encima de todos los
   roles que vaya a dar, quitar o sancionar. Un bot no puede tocar roles que estén por encima del suyo.
3. Entra al panel con «Iniciar sesión con Discord» y elige tu servidor.
4. **General → Configuración rápida**: eliges el tipo de comunidad y NEXUS activa y configura los módulos
   recomendados en tres pasos.
5. **Avanzado → Diagnóstico**: comprueba que no falte ningún permiso. En cada página del panel también aparece un
   aviso si a NEXUS le falta algún permiso para ese módulo.
6. En **Overview** tienes la lista **«Primeros pasos»** con lo que te falta por hacer.

---

## 3. Quién puede usar qué

### En Discord

- Los **comandos de staff** (moderar, `/embed`, `/decir`, `/bloquear`…) vienen ocultos para quien no tiene el permiso
  de Discord correspondiente (tabla de la sección 7).
- Puedes cambiarlo en Discord: *Ajustes del servidor → Integraciones → NEXUS*. Ahí eliges, comando por comando, qué
  roles o canales pueden usarlo. Por ejemplo, dar `/advertir` a un rol «Ayudante» sin darle «Aislar miembros».
- Los comandos para todos (`/nivel`, `/saldo`, `/ayuda`…) los puede usar cualquiera, salvo que tú los limites ahí.
- Los **eventos** (`/evento crear` y `/evento cancelar`) los pueden usar quienes tengan *Gestionar servidor* o
  *Gestionar eventos*, o un rol de **Gestores de eventos** (se elige en el panel → Eventos).

### En el panel

- Entra quien tenga **Administrador** o **Gestionar servidor** en Discord.
- En **Avanzado → Permisos** puedes dar acceso a otros roles, módulo por módulo, con tres niveles:
  - **Ver**: solo mirar.
  - **Editar**: cambiar la configuración.
  - **Administrar**: además, publicar paneles, crear canales…

---

## 4. El panel, sección por sección

Cada módulo tiene un interruptor **Activar**. Los cambios se guardan con la barra inferior **«Guardar cambios»**; si
sales sin guardar, el panel te avisa.

### General

| Sección | Para qué sirve |
|---|---|
| **Overview** | Resumen: estado del bot, miembros, actividad reciente y la lista «Primeros pasos». |
| **Configuración rápida** | Asistente que activa los módulos recomendados según el tipo de comunidad. |
| **Configuración** | Opciones del servidor en NEXUS: idioma (español/inglés), zona horaria y color de los embeds. |
| **Welcome & Goodbye** | Mensaje al entrar, despedida al salir y mensaje privado opcional. Se puede borrar solo tras X segundos. `/bienvenida probar` lo envía de prueba. |
| **Embeds** | Editor libre de mensajes con vista previa idéntica a Discord. Se envía una vez a cualquier canal. El borrador se guarda en tu navegador. |
| **Imágenes** | Las imágenes que subiste: dónde se usan, cuánto ocupan, borrar las que sobran (ver la [sección 6](#6-imágenes)). |

### Moderación

| Sección | Para qué sirve |
|---|---|
| **Moderación** | Canal de registro de sanciones, mensajes de aviso por MD y sanciones automáticas por número de advertencias (p. ej. 3 avisos → aislar 1 h). Cada sanción es un **caso** numerado (`/caso`). |
| **AutoMod** | Reglas automáticas: palabras prohibidas, invitaciones, enlaces, spam, menciones masivas, mayúsculas… Cada regla tiene acciones (borrar, avisar, aislar…), roles y canales exentos y **modo prueba** (solo registra, no castiga). |
| **Anti-raid** | Varias protecciones: <ul><li>**Verificación** al entrar (botón o captcha) y **puerta**: los no verificados solo ven los canales públicos que elijas.</li><li>Filtro de **cuentas nuevas**.</li><li>Detección de **entradas masivas**, que activa el modo raid.</li><li>**Cuarentena**: quita todos los roles y los guarda para devolverlos.</li></ul> |
| **Canal trampa (honeypot)** | Lo crea NEXUS (`#honeypot`, arriba del todo). Quien escribe ahí casi siempre es un bot de spam: <ul><li>NEXUS borra lo que envió en los últimos minutos en todos los canales y aplica la sanción elegida.</li><li>Con **«Si vuelve a caer»** sanciona más fuerte a quien reincide, p. ej. a la 3.ª vez, ban.</li><li>El staff y los roles exentos nunca son sancionados.</li></ul> |
| **IA de moderación** | Claude (IA de Anthropic) revisa mensajes y marca estafas, acoso o spam que las reglas no ven. Siempre con revisión humana. Necesita `ANTHROPIC_API_KEY` y **tiene coste por uso**. |
| **Logs** | Qué se registra y dónde. Hay categorías (mensajes, miembros, moderación, servidor, **voz**) y puedes mandar **cada evento a un canal distinto** (p. ej. «mensaje borrado» a `#logs-mensajes`). |

### Roles y miembros

| Sección | Para qué sirve |
|---|---|
| **Autoroles** | Roles automáticos al entrar, por separado para personas y bots. Admite retraso opcional y esperar a que acepte las reglas del servidor. |
| **Reaction Roles** | Paneles para que cada miembro elija sus roles con **botones**, **menú desplegable** o **reacciones**. Modos: normal, único (solo uno), solo dar, solo quitar. Se publican desde el panel; si cambias algo, pulsa «Actualizar». |
| **Miembros** | Buscar a un miembro y ver su historial: casos, notas del staff, nivel, saldo. |

### Comunidad

| Sección | Para qué sirve |
|---|---|
| **Tickets** | Hasta 5 paneles con botón para abrir canales privados de soporte. Cada panel tiene su categoría, roles de soporte, mensaje de bienvenida y opción de pedir un asunto. Opciones generales: límite de tickets por persona, cierre automático por inactividad y **transcripción** al cerrar (a un canal y, si quieres, por MD). Comandos `/ticket …`. |
| **Sugerencias** | `/sugerir` publica la idea con votos. El staff responde con `/sugerencia` (aceptada, rechazada…). |
| **Starboard** | Los mensajes que llegan a X ⭐ se copian a un canal de destacados. |
| **Encuestas** | `/encuesta` con hasta 10 respuestas, duración y voto múltiple (encuestas nativas de Discord). |
| **Sorteos** | `/sorteo` con botón para participar. Eliges qué roles pueden crear sorteos y a qué rol mencionar al publicarlos. |
| **Eventos** | Eventos con botones **Asistiré / Tal vez / No podré**. <ul><li>Cada persona ve la hora en su zona horaria.</li><li>Aviso por MD X minutos antes y mención a los inscritos al empezar.</li><li>Cupos opcionales e **imagen**: enlace o subida, ver la [sección 6](#6-imágenes).</li></ul> |
| **Comandos personalizados** | Tus propios comandos slash (`/reglas`, `/ip`…) con respuesta de texto o embed, roles que da o quita y quién puede usarlos. |
| **Respuestas automáticas** | Tres herramientas: <ul><li>**Etiquetas**: textos guardados que se publican con `/tag`.</li><li>**Disparadores**: NEXUS responde cuando alguien escribe ciertas palabras.</li><li>**Mensajes fijos (sticky)**: un mensaje que siempre queda al final de un canal.</li></ul> |

### Progresión

| Sección | Para qué sirve |
|---|---|
| **Niveles y XP** | XP por mensaje con tiempo de espera, multiplicadores por rol o canal, canales sin XP y **roles por nivel**. Mensaje de subida de nivel configurable. `/nivel`, `/ranking`, `/xp`. |
| **Economía** | Moneda del servidor (nombre y emoji propios). Gana con `/diario`, `/semanal`, `/trabajar` y `/crimen`; arriesga con `/apostar`, `/tragamonedas` y `/robar`; mueve con `/pagar`. La **tienda** vende roles o artículos, y `/inventario` los muestra. |

### Utilidades

| Sección | Para qué sirve |
|---|---|
| **Anuncios y mensajes programados** | Publica ahora o programa (una vez, cada día, cada semana…), en la zona horaria del navegador y con selector de fecha. |
| **Integraciones** | Avisos de **YouTube**, **Twitch** (necesita claves de Twitch), **RSS** y **GitHub** (versiones) en el canal que elijas. |
| **Voz temporal** | Canal «➕ Crear sala»: quien entra recibe su propia sala, que se borra al quedar vacía. El dueño la controla con `/voz`. |
| **Actividad de voz** | Quién estuvo en voz, cuánto tiempo y en qué canales (nunca audio): gráficos, ranking e historial. `/tiempo-voz`, `/ranking-voz`. |
| **Contadores** | Canales de voz bloqueados arriba que muestran cifras en vivo (miembros, personas, bots, en línea, boosts…). Se actualizan cada 10 minutos (límite de Discord). |
| **Analytics** | Gráficos de crecimiento, mensajes, comandos y moderación. |

### Avanzado

| Sección | Para qué sirve |
|---|---|
| **Permisos** | Acceso al panel por rol y módulo (ver la [sección 3](#3-quién-puede-usar-qué)). |
| **Diagnóstico** | Revisa permisos de NEXUS, posición de su rol, intents de Discord y estado del bot. |
| **Historial** | Registro de auditoría: cada cambio hecho desde el panel o por el bot. |

---

## 5. Mensajes, embeds y variables

Todos los mensajes configurables (bienvenida, tickets, paneles, programados, comandos personalizados, honeypot…)
usan el **mismo editor**:

- **Texto del mensaje** (hasta 2000 caracteres).
- **Embed** con autor, título, enlace del título, descripción, color, miniatura, imagen grande, campos (hasta 25), pie y
  marca de tiempo.
- **Vista previa** igual a Discord, con datos de ejemplo.
- Botón **Emojis** y botón **Variables** (`{`) para insertar datos que cambian.

### Variables

| Variable | Se convierte en |
|---|---|
| `{user}` | Mención del miembro (@nombre) |
| `{user.name}` / `{user.display_name}` | Su nombre de usuario / su apodo visible |
| `{user.id}` | Su ID |
| `{user.avatar}` | Enlace de su avatar (sirve como imagen o miniatura) |
| `{user.created_at}` / `{user.joined_at}` | Fecha de creación de la cuenta / de entrada al servidor |
| `{server}` / `{server.id}` / `{server.icon}` | Nombre, ID e icono del servidor |
| `{member_count}` / `{member_count.ordinal}` | Número de miembros / «1.420.º» |
| `{channel}` | Mención del canal |

Las **integraciones** añaden `{title}`, `{url}`, `{author}`, `{name}` y `{thumbnail}` del vídeo o artículo.

---

## 6. Imágenes

Hay **tres formas** de poner una imagen en un mensaje:

| Forma | Cuándo usarla | ¿Ocupa espacio en NEXUS? |
|---|---|---|
| **Enlace** `https://…` | Imágenes que ya están en internet. ⚠️ Los enlaces de adjuntos de Discord (`cdn.discordapp.com/attachments/…`, `media.discordapp.net/…`) **caducan en ~24 h**: no los uses en mensajes que se vuelven a enviar. | No |
| **Subir y guardar** | Mensajes que el bot envía muchas veces (bienvenida, paneles, programados, eventos…). NEXUS guarda la imagen y la adjunta en cada envío: **nunca caduca**. | Sí |
| **Solo enviar (no guardar)** | Solo en **Embeds**, para un mensaje que se manda una vez. La imagen sale con el mensaje y Discord guarda su copia; NEXUS no guarda nada. | No |

### Cómo se sube

En cualquier editor, junto a **Miniatura**, **Imagen grande**, **icono del autor** e **icono del pie**, está el botón
🖼️. Abre la galería del servidor:

- Arrastra o haz clic para subir. Se aceptan **PNG, JPG, GIF y WEBP de hasta 8 MB**. Se comprueba el contenido real
  del archivo, no la extensión.
- O elige una imagen que ya subiste.
- En la página **Embeds**, arriba aparece además **«Guardar en el servidor» / «Solo enviar (no guardar)»**.
- La imagen elegida aparece como «Imagen subida» (o «Solo este envío») con su miniatura y una ✕ para quitarla.
- Si recargas la página antes de enviar, una imagen «solo enviar» hay que volver a elegirla.

### Página «Imágenes» (General → Imágenes)

- Barra de espacio: **máximo 50 imágenes o 100 MB por servidor**.
- Cada imagen muestra dónde se usa (*Welcome & Goodbye*, *Comando /info*, *Evento: Torneo*…) o **«Sin usar»** con la
  fecha en que se borrará.
- Filtros **Todas / En uso / Sin usar**, botón **Borrar imagen** y **«Borrar las no usadas»**.
- **Limpieza automática**: las imágenes que nada usa se borran solas **7 días** después de subirlas. Los mensajes ya
  enviados **no pierden** la imagen: Discord guarda su propia copia.

### Desde Discord

| Comando | Opción | Qué pasa con la imagen |
|---|---|---|
| `/embed` | `archivo` | Se envía dentro del embed. No se guarda. |
| `/anunciar` | `archivo` | Igual que `/embed`. |
| `/evento crear` | `archivo` | **Se guarda** en «Imágenes», porque la tarjeta del evento se actualiza con cada respuesta. |
| `/embed-editar` | — | Si el embed tenía una imagen adjunta, se conserva al editar. |

---

## 7. Comandos de Discord

Los comandos están en **español** (y en inglés si Discord está en inglés). Con clic derecho sobre un mensaje o
usuario → **Apps** hay atajos: *Reportar mensaje al staff*, *Guardar en mis MD*, *Ver avatar*, *Aislar 10 minutos* e
*Historial de advertencias*.

**Columna «Permiso por defecto»:** quién lo ve sin configurar nada. «Todos» = cualquier miembro. Se puede cambiar en
Integraciones (ver la [sección 3](#3-quién-puede-usar-qué)).

### Generales e información

| Comando | Qué hace | Permiso por defecto |
|---|---|---|
| `/ayuda` | Ayuda y botón al panel | Todos |
| `/panel` | Enlace al panel del servidor | Todos |
| `/invitar` | Enlace para invitar a NEXUS | Todos |
| `/ping` | Latencia del bot | Todos |
| `/info servidor` · `usuario` · `avatar` · `banner` · `rol` · `bot` · `color` | Fichas de información | Todos |
| `/afk [motivo]` | Te marca ausente; avisa a quien te mencione | Todos |
| `/recordatorio cuando texto [privado]` | Te recuerda algo (máx. 10 activos) | Todos |
| `/reportar usuario motivo` | Envía un reporte al staff | Todos |

### Mensajes del staff

| Comando | Qué hace | Permiso por defecto |
|---|---|---|
| `/embed [canal] [titulo] [descripcion] [color] [imagen] [miniatura] [pie] [archivo]` | Envía un embed. Sin título ni descripción abre un formulario. | Gestionar mensajes |
| `/embed-editar enlace` | Edita un embed que envió NEXUS (formulario relleno) | Gestionar mensajes |
| `/anunciar titulo texto [canal] [mencionar] [color] [imagen] [archivo]` | Anuncio con 📢 y mención opcional de un rol o @everyone (solo si tú podrías mencionarlo) | Gestionar mensajes |
| `/decir texto [canal]` | NEXUS escribe el texto (sin @everyone ni roles) | Gestionar mensajes |
| `/snipe` · `/editsnipe` | Último mensaje borrado / editado del canal | Gestionar mensajes |

### Moderación

| Comando | Qué hace | Permiso por defecto |
|---|---|---|
| `/advertir usuario [motivo]` | Advertencia (cuenta para las sanciones automáticas) | Aislar miembros |
| `/historial usuario` · `/caso numero` · `/perdonar numero` · `/limpiar-advertencias usuario` | Ver, consultar y anular casos | Aislar miembros |
| `/nota usuario nota` | Nota interna del staff (no se avisa al miembro) | Aislar miembros |
| `/aislar usuario duracion [motivo]` · `/quitar-aislamiento` | Timeout de Discord (máx. 28 días) | Aislar miembros |
| `/modstats [moderador]` | Estadísticas de moderación | Aislar miembros |
| `/expulsar usuario [motivo]` | Expulsar | Expulsar miembros |
| `/banear usuario [motivo] [duracion] [borrar-dias]` | Ban; con duración se desbanea solo | Banear miembros |
| `/softban` · `/desbanear id-usuario` · `/baneo-masivo ids` | Variantes de ban | Banear miembros |
| `/limpiar cantidad [usuario] [solo]` | Borra mensajes (bots, enlaces, imágenes…) | Gestionar mensajes |
| `/modo-lento segundos` · `/bloquear` · `/desbloquear` · `/recrear-canal` | Control de canales | Gestionar canales |
| `/bloqueo-total activar` · `/modo-raid activar` | Cierra todo el servidor / modo raid | Administrador |
| `/cuarentena usuario` · `/liberar usuario` | Quita y guarda roles / los devuelve | Aislar + Gestionar roles |
| `/rol dar` · `/rol quitar` | Dar o quitar un rol | Gestionar roles |
| `/apodo usuario [apodo]` | Cambiar o quitar apodo | Gestionar apodos |
| `/verificacion publicar` | Publica el mensaje de verificación del anti-raid | Gestionar servidor |
| `/bienvenida probar` · `estado` | Prueba la bienvenida | Gestionar servidor |

### Comunidad

| Comando | Qué hace | Permiso por defecto |
|---|---|---|
| `/ticket abrir` · `cerrar` · `reclamar` · `renombrar` · `añadir` · `quitar` | Gestión de tickets | Todos (dentro del ticket, staff) |
| `/sugerir texto` · `/sugerencia numero estado [respuesta]` | Sugerencias | Todos / staff |
| `/encuesta pregunta respuestas [horas] [multiple]` | Encuesta | Todos |
| `/sorteo premio duracion [ganadores] [canal]` | Sorteo | Gestionar servidor o un rol de **Gestores de sorteos** (panel → Sorteos) |
| `/evento crear titulo cuando [descripcion] [cupos] [canal] [imagen] [archivo]` · `cancelar` · `lista` | Eventos | Gestores de eventos |
| `/tag nombre [usuario]` | Publica una etiqueta | Todos |
| `/voz cerrar` · `abrir` · `limite` · `nombre` · `permitir` · `echar` · `reclamar` · `calidad` | Control de tu sala de voz temporal | Dueño de la sala |
| `/tiempo-voz [usuario] [periodo]` · `/ranking-voz [periodo]` | Actividad de voz | Todos |
| `/juego bola8` · `moneda` · `dado` · `elegir` · `ppt` · `tresenraya` · `ship` | Juegos | Todos |

### Niveles y economía

| Comando | Qué hace | Permiso por defecto |
|---|---|---|
| `/nivel [usuario]` · `/ranking [pagina]` | Nivel y clasificación | Todos |
| `/xp dar` · `quitar` · `reiniciar` | Ajustar XP | Gestionar servidor |
| `/saldo` · `/diario` · `/semanal` · `/trabajar` · `/crimen` | Ganar monedas | Todos |
| `/pagar` · `/robar` · `/apostar` · `/tragamonedas` | Mover o arriesgar monedas | Todos |
| `/tienda` · `/comprar articulo` · `/inventario` | Tienda | Todos |
| `/dinero dar` · `quitar` | Ajustar saldo | Gestionar servidor |

Los **comandos personalizados** que crees en el panel aparecen también aquí, con su propio nombre.

---

## 8. Formatos de tiempo y fecha

| Dónde | Formato | Ejemplos |
|---|---|---|
| Duraciones (`/aislar`, `/banear`, `/sorteo`, `/recordatorio`) | número + `m` / `h` / `d` / `w`, combinables | `10m`, `2h`, `7d`, `1d12h` |
| `/evento crear cuando` | relativo o fecha y hora **en la zona horaria del servidor** | `2h`, `1d3h`, `20/11 21:00`, `20/11/2026 21:00`, `2026-11-20 21:00` |
| Panel (programados, eventos) | selector de fecha y hora | En la zona horaria **de tu navegador**; no deja elegir una fecha pasada |

---

## 9. Problemas frecuentes

| Síntoma | Causa probable | Solución |
|---|---|---|
| «Missing Permissions» o NEXUS no da un rol | El rol de NEXUS está por debajo, o le falta un permiso | Sube el rol de NEXUS; mira **Diagnóstico** |
| Un comando no aparece | No tienes el permiso de Discord, o lo limitaron en Integraciones | Ver la [sección 3](#3-quién-puede-usar-qué) |
| El panel dice «Bot desconectado» | El bot está apagado o sin internet | Revisa el bot (ver la [sección 10](#10-para-quien-mantiene-el-servidor)) |
| «Discord no responde ahora mismo» | Corte momentáneo de conexión con Discord | Vuelve a intentarlo en unos segundos |
| Una imagen dejó de verse en un mensaje que se reenvía | Era un enlace de adjunto de Discord (caduca) | Súbela con el botón 🖼️ |
| La imagen «solo enviar» desapareció del editor | Recargaste la página antes de enviar | Elígela otra vez |
| «Este servidor ya alcanzó el límite de imágenes» | 50 imágenes o 100 MB | **Imágenes → Borrar las no usadas** |
| AutoMod no lee el texto | Falta el intent *Message Content* | Developer Portal → Bot → *Privileged Gateway Intents* |
| Los contadores tardan en cambiar | Discord limita renombrar canales | Se actualizan cada 10 minutos |

---

## 10. Para quien mantiene el servidor

### En local (desarrollo, Windows con Laragon)

- **Requisitos:** PostgreSQL y Redis de Laragon encendidos.
- **Configuración:** `.env` en la raíz, con `ENV=development` y `DEV_GUILD_ID` = tu servidor de pruebas, para que los
  comandos se registren al instante.
- **Arranque** (en tres terminales):
  - API: `.venv\Scripts\uvicorn nexus_api.main:app --port 8000`
  - Bot: `.venv\Scripts\python -m nexus_bot`
  - Panel: `cd dashboard && npm run dev` → `http://localhost:3000`
- **Migraciones** tras actualizar: `.venv\Scripts\alembic upgrade head`
- **Pruebas:** `.venv\Scripts\python -m pytest`. Usan otra base de datos (`nexus_test`), nunca los datos reales.

### En producción (Docker + Cloudflare Tunnel)

Todo el detalle está en [`docs/DEPLOY.md`](DEPLOY.md). Resumen:

1. Clona el repositorio en el servidor, copia `.env.example` a `.env` y rellena los valores:
   - `ENV=production` y **`DEV_GUILD_ID` vacío**.
   - `DASHBOARD_URL=https://tu-dominio` y `DISCORD_REDIRECT_URI=https://tu-dominio/api/v1/auth/callback`; añade
     también ese callback en Developer Portal → OAuth2.
   - Un `ENCRYPTION_KEY` nuevo y un `DB_PASSWORD` fuerte.
2. `docker compose up -d --build`
3. En Cloudflare Zero Trust, el *Public Hostname* apunta a `http://nexus-dashboard:3000` (red `cloudflare_red`).

Detalles a tener en cuenta:

- **Arranque con comprobación:** si la configuración de producción está incompleta (token o clave vacíos,
  `DEV_GUILD_ID` puesto, URL sin https…), la API y el bot **no arrancan** y explican qué falta en
  `docker compose logs api` o `docker compose logs bot`.
- **Healthchecks:** `docker compose ps` muestra `healthy` o `unhealthy` para la API, el bot y el panel. Docker
  reinicia solo lo que se cae del todo. Lo que se queda «unhealthy» hay que reiniciarlo a mano:
  `docker compose restart bot`.
- **Documentación de la API** (`/api/docs`): solo existe en desarrollo.
- **Copias de seguridad:** cron diario con `pg_dump` (ver `DEPLOY.md`). Incluye las imágenes subidas, porque se
  guardan en la base de datos.
- **Actualizar:** sube el código nuevo y vuelve a ejecutar `docker compose up -d --build`. El servicio `migrate`
  aplica las migraciones antes de arrancar la API y el bot.

### Antes del primer lanzamiento

- [ ] Rotar el token del bot y el client secret (Developer Portal) y el token del túnel de Cloudflare.
- [ ] Completar los textos legales en `dashboard/app/legal/content.ts` (nombre y contacto).
- [ ] Hacer las pruebas de `docs/PRUEBAS.md` con una segunda cuenta (sanciones, honeypot, AutoMod, bienvenida…).
- [ ] Al pasar de **100 servidores**, Discord exige verificar el bot y justificar los intents *Server Members* y
  *Message Content*.
