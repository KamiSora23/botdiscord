# Lista de pruebas en tu servidor de Discord

Hazlas en tu **servidor de pruebas**, con el bot, la API y el panel encendidos. Marca cada casilla al terminar.
Si algo falla, dime el número de la prueba: yo veo los errores del bot y de la API en directo.

> Consejo: crea un canal `#pruebas-nexus` y, si puedes, invita a una segunda cuenta (o pide a un amigo) para probar las sanciones y la economía entre dos personas.

## 0. Antes de empezar (en el panel)
- [ ] 0.1 Entra en http://localhost:3000 → «Ir al dashboard» → autoriza con Discord.
- [ ] 0.2 Elige tu servidor → **Diagnóstico**: no debería faltar ningún permiso. Si falta alguno, vuelve a invitar al bot con el botón del panel.
- [ ] 0.3 En Ajustes del servidor de Discord → Roles, arrastra el rol de **NEXUS** por encima de los roles que vaya a dar o quitar.

## 1. Comandos generales (cualquier miembro)
- [ ] 1.1 `/ping` → responde con la latencia.
- [ ] 1.2 `/ayuda` → lista de comandos.
- [ ] 1.3 `/servidor` → ficha del servidor.
- [ ] 1.4 `/usuario` y `/usuario` eligiendo a otra persona.
- [ ] 1.5 `/avatar`.
- [ ] 1.6 `/panel` → enlace al panel.

## 2. Bienvenidas (panel → Bienvenida)
- [ ] 2.1 Activa el módulo, elige canal, guarda.
- [ ] 2.2 `/bienvenida probar` → aparece el mensaje en el canal.
- [ ] 2.3 Entra con la segunda cuenta → mensaje real de bienvenida.

## 3. Moderación (panel → Moderación activada)
- [ ] 3.1 `/advertir` a la segunda cuenta → caso #1.
- [ ] 3.2 `/historial` de esa cuenta → aparece la advertencia.
- [ ] 3.3 `/aislar` 1m → la cuenta no puede escribir; `/quitar-aislamiento`.
- [ ] 3.4 `/nota` → luego panel → **Miembros** → la nota aparece.
- [ ] 3.5 `/modo-lento 10` y luego `/modo-lento 0`.
- [ ] 3.6 `/bloquear` → la segunda cuenta no puede escribir; `/desbloquear`.
- [ ] 3.7 `/limpiar 5`.
- [ ] 3.8 Panel → **Registros** con un canal → las acciones anteriores aparecen allí.
- [ ] 3.9 Panel → **AutoMod**: crea una regla de palabras prohibidas y escribe una con la segunda cuenta.

## 4. Roles
- [ ] 4.1 Panel → **Autoroles**: rol al entrar → entra con la segunda cuenta y comprueba el rol.
- [ ] 4.2 Panel → **Roles por reacción**: crea un panel con botones y publícalo → pulsa un botón → recibes el rol; púlsalo otra vez → se quita.

## 5. Comunidad
- [ ] 5.1 Panel → **Tickets**: publica el panel → abre un ticket → `/ticket añadir`, `/ticket cerrar` → llega la transcripción.
- [ ] 5.2 Panel → **Sugerencias**: elige canal → `/sugerir` → vota → `/sugerencia` para aceptarla.
- [ ] 5.3 `/encuesta` → vota con los botones.
- [ ] 5.4 `/sorteo` de 1 minuto → participa → al terminar anuncia ganador.
- [ ] 5.5 Panel → **Starboard**: umbral 1 → reacciona con ⭐ a un mensaje → aparece en el canal de destacados.
- [ ] 5.6 Panel → **Comandos personalizados**: crea uno y úsalo.
- [ ] 5.7 Panel → **Mensajes programados**: uno para dentro de 2 minutos → llega.

## 6. Niveles y economía
- [ ] 6.1 Panel → **Niveles** activado → escribe varios mensajes (espaciados) → `/nivel` y `/ranking`.
- [ ] 6.2 Panel → **Economía** activada, crea un artículo en la tienda → `/diario`, `/trabajar`, `/saldo`, `/tienda`, `/comprar`, `/pagar` a la segunda cuenta.

## 7. Integraciones e IA (opcionales)
- [ ] 7.1 Panel → **Integraciones**: añade un canal de YouTube o un RSS → botón «Probar».
- [ ] 7.2 Twitch: solo si rellenaste `TWITCH_CLIENT_ID/SECRET` en `.env`.
- [ ] 7.3 IA de moderación: solo si rellenaste `ANTHROPIC_API_KEY` (tiene coste por uso).

## 8. Panel
- [ ] 8.1 **Inicio** muestra estadísticas; **Analíticas** muestra gráficos (necesita algo de actividad).
- [ ] 8.2 **Permisos**: da a un rol «ver» en un módulo → la segunda cuenta entra al panel y solo ve eso.
- [ ] 8.3 **Registro de auditoría**: aparecen todos los cambios que hiciste.
- [ ] 8.4 Cambia el idioma a inglés en **Ajustes** → los comandos y mensajes del bot cambian.
