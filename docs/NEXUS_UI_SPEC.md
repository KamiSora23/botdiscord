# NEXUS BOT — Especificación de la interfaz (dashboard)

Stack: **Next.js (App Router) + TypeScript + Tailwind CSS + shadcn/ui** (componentes Radix accesibles), iconos **lucide-react**, datos con **TanStack Query**, formularios con **react-hook-form + zod**, idiomas con **next-intl**.

Referencias visuales (tus capturas):

- **Astero:** tarjetas de módulos agrupadas por categoría con contador "2/2 activos".
- **ORBT:** Overview con tarjetas de estadísticas, estado de módulos, actividad reciente y últimos miembros.
- **Ostra:** editor con variables resaltadas, selector de emojis y vista previa en vivo.

---

## 1. Sistema visual

### 1.1. Colores

Tema oscuro en V1. Todos los colores se definen como variables CSS (`--nx-*`) en `:root`, así un tema claro posterior solo redefine las variables.

| Token | Valor | Uso |
|---|---|---|
| `--nx-bg` | `#11131B` | Fondo de la página |
| `--nx-sidebar` | `#171923` | Sidebar y topbar |
| `--nx-panel` | `#1E202D` | Tarjetas y paneles |
| `--nx-panel-hover` | `#24273A` | Hover de filas y tarjetas |
| `--nx-input` | `#252938` | Campos de formulario |
| `--nx-border` | `#2E3245` | Bordes y separadores |
| `--nx-text` | `#E5E7EB` | Texto principal |
| `--nx-text-muted` | `#9CA3AF` | Texto secundario |
| `--nx-primary` | `#7465F7` | Color de marca: iconos, bordes activos, focus, gráficas |
| `--nx-primary-solid` | `#6455E8` | **Fondo de botones primarios** con texto blanco |
| `--nx-primary-text` | `#8B7CFF` | **Enlaces y texto de color** sobre fondo oscuro |
| `--nx-success` | `#22C55E` | Activo, guardado |
| `--nx-warning` | `#F59E0B` | Avisos |
| `--nx-danger` | `#EF4444` | Errores, borrar |

> **Corrección de contraste:** el `#7465F7` del plan da 4.3:1 con texto blanco y 4.4:1 como texto sobre el fondo. No llega al mínimo de accesibilidad (4.5:1). Por eso se usa `#6455E8` para el fondo de los botones (5.2:1) y `#8B7CFF` para enlaces (5.7:1). `#7465F7` se mantiene como color de marca en lo que no es texto.

Los estados nunca dependen solo del color: siempre van con icono o texto ("Activo", "Error").

### 1.2. Tipografía

| Uso | Fuente | Tamaño / peso |
|---|---|---|
| Título de página | Inter | 24 px / 600 |
| Título de tarjeta | Inter | 16 px / 600 |
| Texto | Inter | 14 px / 400 |
| Etiquetas y ayudas | Inter | 13 px / 400–500 |
| IDs, variables, código | JetBrains Mono | 13 px |

Se cargan con `next/font` (sin peticiones externas en tiempo de ejecución).

### 1.3. Espaciado y forma

- Escala de 4 px (Tailwind por defecto).
- Bordes redondeados: tarjetas 12 px, inputs y botones 8 px, badges completamente redondos.
- Ancho máximo del contenido: 1280 px.
- Sombras mínimas: la profundidad se marca con el color del panel y el borde.

---

## 2. Rutas

| Ruta | Página | Fase | Acceso |
|---|---|---|---|
| `/` | Inicio público: qué es NEXUS, botones "Iniciar sesión" e "Invitar" | 1 | público |
| `/login` | Redirige a `/api/v1/auth/login` | 1 | público |
| `/dashboard` | Mis servidores | 1 | sesión |
| `/dashboard/[guildId]` | Redirige a `overview` | 1 | sesión |
| `/dashboard/[guildId]/overview` | Overview | 1 | N1 |
| `/dashboard/[guildId]/settings` | Configuración general | 1 | N1 (guardar N3) |
| `/dashboard/[guildId]/diagnostics` | Permisos del bot | 1 | N1 |
| `/dashboard/[guildId]/audit-log` | Historial de cambios | 1 | N1 |
| `/dashboard/[guildId]/welcome` | Welcome & Goodbye | 2 | N1 (guardar N2) |
| `/account` | Mi cuenta (idioma, zona horaria, sesiones, borrar datos) | 1 | sesión |
| `/legal/terms`, `/legal/privacy` | Páginas legales | 9 (borrador antes) | público |
| `/dashboard/[guildId]/[módulo]` | Resto de módulos (§8) | 3–8 | |

Reglas:

- Cada página de servidor obtiene el `guildId` de la URL. Cambiar de servidor conserva la sección: `/dashboard/A/welcome` → `/dashboard/B/welcome`.
- Si no hay sesión, se redirige a `/login?next=<ruta actual>`.
- Un `guildId` sin acceso muestra la página "Servidor no disponible", nunca un error en blanco.

---

## 3. Estructura de la pantalla

```text
┌──────────────┬────────────────────────────────────────────────────┐
│  NEXUS BOT   │  Dashboard › Mi Comunidad › Welcome   🔍 Ctrl K  🔔 👤│ ← Topbar
│ ┌──────────┐ ├────────────────────────────────────────────────────┤
│ │Mi Comuni.│ │                                                    │
│ │ ● Online ▾│ │   Título de la página           [interruptor]     │
│ └──────────┘ │   Descripción                                      │
│ 🔍 Buscar…    │                                                    │
│              │   ┌───────────── contenido ─────────────┐          │
│ Overview     │   │                                      │          │
│ GENERAL    ▾ │   └──────────────────────────────────────┘          │
│  Settings    │                                                    │
│  Welcome   ● │                                                    │
│ MODERATION ▾ │                                                    │
│  …           │                                                    │
│ ─────────────│  ┌──────────────────────────────────────────────┐  │
│ 👤 Alex       │  │ Cambios sin guardar      [Descartar] [Guardar]│  │ ← SaveBar
│    Cerrar ses.│  └──────────────────────────────────────────────┘  │
└──────────────┴────────────────────────────────────────────────────┘
```

### 3.1. Sidebar

- **Selector de servidor** arriba: icono, nombre y estado del bot. Al abrirlo muestra la lista de servidores, con buscador y "Añadir otro servidor".
- **Buscador del menú** que filtra los elementos mientras escribes.
- **Grupos plegables**; el estado plegado se recuerda en `localStorage`.
- **Punto de estado** por módulo: verde = activo, gris = desactivado, ámbar = activo con un problema (por ejemplo, sin permisos en el canal).
- Abajo: usuario, enlace a "Mi cuenta" y "Cerrar sesión".

Grupos (orden final, según el plan revisado):

| Grupo | Elementos |
|---|---|
| — | Overview |
| GENERAL | Configuración, Welcome & Goodbye, Anuncios, Embeds |
| MODERACIÓN | Moderación, AutoMod, IA de moderación, Logs |
| ROLES Y MIEMBROS | Autoroles, Reaction Roles, Miembros |
| COMUNIDAD | Tickets, Sugerencias, Starboard, Encuestas, Sorteos, Comandos personalizados |
| PROGRESIÓN | Niveles y XP, Economía |
| UTILIDADES | Mensajes programados, Integraciones, Analytics |
| AVANZADO | Permisos, Diagnóstico, Historial |

Los módulos que todavía no existen aparecen en gris con la etiqueta **"Pronto"** y no se pueden abrir. Esto se controla con una opción (`NEXT_PUBLIC_SHOW_UPCOMING`) para poder ocultarlos en producción.

### 3.2. Topbar

- Migas de pan: `Dashboard › {servidor} › {página}`.
- **Búsqueda global (Ctrl/⌘ K):** busca páginas, módulos y opciones concretas ("canal de bienvenida"). Cada opción tiene un ancla, así que el resultado lleva directamente al campo y lo resalta 2 segundos. El índice es un archivo estático generado a partir de los textos de traducción.
- Notificaciones (fase 8; en V1 el icono no aparece).
- Menú del usuario: Mi cuenta, Idioma, Cerrar sesión.

### 3.3. Responsive

| Ancho | Sidebar | Editor y vista previa |
|---|---|---|
| ≥ 1280 px | Fija (260 px) | Dos columnas: editor + vista previa fija a la derecha |
| 768–1279 px | Plegable a iconos (72 px) | Vista previa debajo del editor |
| < 768 px | Menú desplegable con botón ☰ | Una columna; pestañas "Editar" / "Vista previa" |

Los objetivos táctiles miden al menos 40 × 40 px. La SaveBar ocupa todo el ancho en móvil.

---

## 4. Páginas de la V1

### 4.1. Inicio público `/`

- Logo y nombre, frase corta, botones "Iniciar sesión con Discord" e "Invitar NEXUS".
- Tres tarjetas con módulos destacados y pie con enlaces legales.
- Si ya hay sesión, el botón principal dice "Ir al dashboard".

### 4.2. Mis servidores `/dashboard`

- Título "Tus servidores", buscador y cuadrícula de tarjetas (3 / 2 / 1 columnas).
- **Tarjeta con bot:** icono, nombre, miembros, punto "Bot activo" y botón "Administrar".
- **Tarjeta sin bot:** icono en gris, etiqueta "No añadido" y botón "Invitar". La invitación se abre en una ventana; al volver a la pestaña, la lista se recarga sola.
- **Estado vacío:** "No administras ningún servidor. Necesitas el permiso *Administrar servidor*." + enlace de ayuda.
- Arriba, un resumen: servidores administrados, módulos activos y estado del bot.

### 4.3. Overview `/dashboard/[guildId]/overview`

Inspirado en ORBT y Astero:

1. **Cabecera:** icono y nombre del servidor, miembros, insignia "Bot online/offline" con latencia.
2. **Alertas** (si las hay), arriba del todo: "NEXUS no puede enviar mensajes en #bienvenida → Revisar permisos". Cada alerta lleva un botón que abre la página que lo resuelve.
3. **Tarjetas de estadísticas** (4): Miembros, Entradas en 7 días (con salidas como dato secundario), Comandos en 7 días y Módulos activos "1/1".
4. **Gráfica** de 7 o 30 días: entradas y salidas por día (barras), con selector de rango.
5. **Módulos por categoría** (estilo Astero): tarjetas con icono, contador "x/y activos" y lista de módulos con interruptor y enlace. Los que no están disponibles muestran "Pronto".
6. **Actividad reciente:** las últimas 8 entradas del historial ("Alex actualizó Welcome · hace 3 min") con enlace a "Ver todo".

### 4.4. Configuración `/dashboard/[guildId]/settings`

| Campo | Control |
|---|---|
| Idioma del bot en este servidor | Selector: Español / English |
| Zona horaria | Selector con búsqueda (IANA), con la hora actual de ejemplo |
| Color por defecto de los embeds | Selector de color + campo HEX + 8 colores sugeridos |

Se guarda con la SaveBar. Sin permiso N3, los campos aparecen deshabilitados con el aviso "Solo lectura: necesitas permiso de administración".

### 4.5. Diagnóstico `/dashboard/[guildId]/diagnostics`

- Lista de permisos que necesita el bot: ✅ concedido, ❌ falta. Cada uno indica qué módulos lo usan.
- Intents: Server Members ✅, Message Content (no necesario en V1).
- Botón "Volver a invitar con los permisos correctos" (`invite_url`).
- Explicación de la jerarquía de roles con un diagrama simple (se usa desde la fase 4).

### 4.6. Historial `/dashboard/[guildId]/audit-log`

- Tabla: fecha, quién (avatar y nombre), acción, módulo y botón "Ver cambios".
- "Ver cambios" abre un panel lateral con antes → después de cada campo, con los IDs de canales y roles traducidos a sus nombres.
- Filtro por módulo y carga infinita.

### 4.7. Welcome & Goodbye `/dashboard/[guildId]/welcome`

**Cabecera:** título, descripción y el **interruptor general** del módulo (N3). Si está apagado, el editor sigue visible pero atenuado, con el aviso "El módulo está desactivado: los cambios se guardan, pero no se envían mensajes".

**Pestañas:** `Bienvenida` · `Despedida`

> Cambio respecto a la propuesta de ChatGPT (pestañas General / Message / Design / Advanced): separar el mismo mensaje en 4 pestañas obliga a saltar de una a otra para ver el resultado. Aquí cada pestaña es un mensaje completo, y la vista previa siempre está visible.

**Pestaña Bienvenida** — columna izquierda (editor):

1. **Ajustes**
   - Interruptor "Enviar mensaje de bienvenida".
   - **Canal:** `ChannelSelect` agrupado por categoría. Si el bot no puede escribir ahí, el canal muestra ⚠ y un tooltip explica qué permiso falta.
   - "Ignorar bots" (interruptor).
   - "Borrar el mensaje después de…" (desactivado / 5 s … 24 h).
2. **Mensaje** → `MessageEditor` (§5.2).
3. **Mensaje privado (DM)**: interruptor y, si se activa, otro `MessageEditor`.

Columna derecha: **vista previa de Discord** fija, con selector "Canal / DM" cuando el DM está activo, y botón **"Enviar prueba"** (usa la configuración guardada; si hay cambios sin guardar, pregunta antes).

**Pestaña Despedida:** igual, sin DM.

---

## 5. Componentes

### 5.1. Lista

| Componente | Descripción |
|---|---|
| `AppShell` | Sidebar + topbar + contenido |
| `GuildSwitcher` | Selector de servidor |
| `CommandPalette` | Búsqueda Ctrl K |
| `PageHeader` | Título, descripción, acciones, interruptor del módulo |
| `Card`, `StatCard` | Tarjetas |
| `ModuleCard` | Tarjeta de categoría con contador (Overview) |
| `StatusDot`, `Badge` | Estados (siempre con texto accesible) |
| `ChannelSelect`, `RoleSelect` | Selectores con búsqueda, iconos por tipo y avisos de permisos |
| `TimezoneSelect`, `ColorPicker` | |
| `VariableInput` | Campo de texto con variables resaltadas y autocompletado |
| `MessageEditor` | Texto + constructor de embed |
| `DiscordPreview` | Vista previa estilo Discord |
| `SaveBar` | Barra de cambios sin guardar |
| `ConfirmDialog` | Confirmación de acciones destructivas |
| `Toast` | Avisos breves (sonner) |
| `EmptyState`, `ErrorState`, `Skeleton` | Estados de página (§6) |
| `ReadOnlyNotice` | Aviso de falta de permisos |

### 5.2. `MessageEditor`

```text
┌ Contenido ─────────────────────────────── 34 / 2000 ┐
│ ¡Bienvenido {user}! 👋                    [😀] [{ }] │
└─────────────────────────────────────────────────────┘
[ + Añadir embed ]   (si ya hay uno: tarjeta plegable "Embed")
┌ Embed ──────────────────────────────────────── 🗑 ┐
│ ▌Color [■ #7465F7]                                 │
│ ▸ Autor                                           │
│ ▾ Título y descripción                            │
│     Título        [¡Bienvenido a {server}!]  23/256│
│     Descripción   [ … ]                   120/4096│
│ ▸ Imágenes (miniatura, imagen grande)             │
│ ▸ Campos (0/25)                                   │
│ ▸ Pie y marca de tiempo                           │
│                               Total: 312 / 6000   │
└───────────────────────────────────────────────────┘
```

- Las secciones del embed se pliegan; solo "Título y descripción" está abierta por defecto.
- Contadores de caracteres en cada campo, en ámbar al 90 % y en rojo al superar el límite.
- **Botón `{ }`**: abre la lista de variables (§3.2 de la base de datos) con su descripción y un ejemplo; al hacer clic se inserta en el cursor.
- **Autocompletado:** al escribir `{` aparece la lista filtrada.
- **Resaltado:** las variables válidas en color `--nx-primary-text`; las desconocidas subrayadas en rojo con el tooltip "Variable desconocida".
- **Selector de emojis** (botón 😀): emojis Unicode y, en una pestaña, los emojis del servidor.
- Avanzado (fase 2, opcional): "Editar como JSON" con validación.

### 5.3. `DiscordPreview`

- Imita un mensaje de Discord: avatar y nombre del bot con la insignia "BOT", hora, contenido y embed (barra de color, autor, título, descripción, campos en línea, miniatura, imagen, pie y marca de tiempo).
- Sustituye las variables con datos de ejemplo: el usuario actual como miembro, el servidor real y `member_count + 1`.
- Renderiza el Markdown de Discord: `**negrita**`, `*cursiva*`, `__subrayado__`, `~~tachado~~`, `` `código` ``, bloques de código, `||spoiler||`, `> cita`, `#` títulos, listas, enlaces `[texto](url)` y menciones de usuario, canal y rol como "pastillas".
- Se actualiza mientras escribes, con 150 ms de espera para no recalcular en cada tecla.
- Etiqueta "Vista previa aproximada": Discord puede mostrar diferencias mínimas. "Enviar prueba" muestra el resultado real.

### 5.4. Guardado (`SaveBar`)

- Guardado **manual**. Al cambiar algo aparece la barra inferior: "Tienes cambios sin guardar" · `Descartar` · `Guardar`.
- `Ctrl/⌘ S` guarda.
- Si intentas salir de la página con cambios: diálogo "¿Salir sin guardar?" (navegación interna) y aviso del navegador (`beforeunload`).
- Mientras guarda, el botón muestra un spinner y se bloquea. Al terminar: toast "Cambios guardados" y la barra desaparece.
- Errores de validación: la barra se pone roja ("2 campos tienen errores"), se abren las secciones afectadas y se hace scroll al primer error.
- **`409 version_conflict`:** diálogo "Otra persona guardó cambios mientras editabas" con las opciones "Ver sus cambios" (recarga) o "Sobrescribir" (reenvía con la nueva versión).
- Los `warnings` del guardado aparecen como un aviso ámbar junto al campo correspondiente, pero el guardado cuenta como correcto.

---

## 6. Estados de cada página

| Estado | Qué se ve |
|---|---|
| Cargando | Skeletons con la forma real del contenido (no spinners a pantalla completa) |
| Vacío | Ilustración simple, frase y botón de acción ("Crear la primera regla") |
| Error | Mensaje claro, código de error pequeño y botón "Reintentar" |
| Sin permisos | `ReadOnlyNotice`: qué permiso falta y a quién pedirlo |
| Bot desconectado | Banner ámbar arriba: "NEXUS está desconectado. Puedes editar, pero los cambios se aplicarán cuando vuelva." |
| Bot no está en el servidor | Página completa con el botón "Invitar NEXUS" |
| Sesión caducada | Redirige al login y vuelve a la misma página después |
| 404 / 500 / mantenimiento | Páginas propias con enlace al inicio |

---

## 7. Idiomas, accesibilidad y calidad

### Idiomas

- **next-intl**, sin prefijo en la URL. El idioma sale de `users.locale`; antes del login, del navegador.
- Textos en `dashboard/messages/es.json` y `en.json`. Ningún texto se escribe directamente en los componentes.
- Fechas y números con `Intl` según el idioma y la zona horaria del usuario.
- Los mensajes de error usan el `code` de la API para traducirse en el dashboard.

### Accesibilidad

- Todo se puede usar con teclado, con foco visible (anillo `--nx-primary` de 2 px).
- Contraste mínimo 4.5:1 en texto (ver §1.1).
- Cada campo tiene su `label`; los errores se asocian con `aria-describedby`.
- Interruptores con texto ("Activado"), no solo color.
- Se respeta `prefers-reduced-motion`.

### Calidad

- Tipos de la API generados desde el OpenAPI de FastAPI (`openapi-typescript`), así el dashboard y la API no se desincronizan.
- Esquemas zod para formularios que replican los de Pydantic. Una prueba compara ambos con ejemplos compartidos.
- Lighthouse ≥ 90 en accesibilidad y rendimiento en `/dashboard` y `/welcome`.

---

## 8. Páginas de fases posteriores (referencia)

| Fase | Página | Contenido principal |
|---|---|---|
| 3 | Moderación | Mensajes de respuesta, razones predefinidas, duraciones, casos con buscador y detalle |
| 3 | AutoMod | Lista de reglas (interruptor, prioridad), editor de regla (condiciones, excepciones, acciones), modo de prueba |
| 3 | Logs | Categorías de eventos con un canal por categoría y checkboxes de eventos |
| 3 | Permisos | Matriz de roles × módulos (ver / editar / administrar) |
| 4 | Autoroles | Roles al entrar, roles para bots, retraso |
| 4 | Reaction Roles | Lista de paneles + constructor (botones, menú o reacciones) con vista previa y "Publicar" |
| 4 | Miembros | Buscador, perfil del miembro con casos y notas |
| 5 | Tickets | Paneles, categorías, staff, transcripciones, cierre automático |
| 5 | Sugerencias, Starboard, Encuestas, Sorteos | Configuración + listados con estado |
| 5 | Comandos personalizados | Constructor por acciones (sin código), prueba en vivo |
| 6 | Niveles | XP por mensaje, recompensas por nivel, ranking, diseñador de tarjeta de rango |
| 6 | Economía | Moneda, tienda, monederos, transacciones |
| 7 | Integraciones | Tarjetas por servicio, conexión, canal, mensaje y "Probar" |
| 7 | IA de moderación | Categorías, umbrales, acciones, cola de revisión, uso de tokens (como el contador de Astero) |
| 8 | Analytics, Premium, Plantillas, Quick Setup, Notificaciones | Según el plan maestro |

---

## 9. Criterios de "V1 terminada"

- [ ] Login y logout con Discord; la sesión sobrevive a recargar la página.
- [ ] `/dashboard` lista solo los servidores donde tengo Administrar servidor, con el estado del bot.
- [ ] Invitar el bot desde el dashboard y verlo aparecer como "Bot activo" sin recargar manualmente.
- [ ] Overview con datos reales: miembros, entradas/salidas, módulos, actividad y alertas.
- [ ] Configuración general guardada y aplicada (idioma del bot, zona horaria, color).
- [ ] Welcome y Goodbye completos: canal, texto, embed, DM, variables, vista previa y prueba.
- [ ] Un cambio guardado en el dashboard se aplica en el bot en menos de 2 segundos, sin reiniciarlo.
- [ ] El bot reiniciado conserva toda la configuración.
- [ ] Dos pestañas editando a la vez → la segunda recibe el aviso de conflicto.
- [ ] Un usuario sin permisos no puede leer ni guardar la configuración de otro servidor (probado contra la API directamente).
- [ ] Todo en español e inglés.
- [ ] Funciona en móvil (375 px) sin scroll horizontal.
