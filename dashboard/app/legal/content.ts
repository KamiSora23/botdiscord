// Borradores de Términos y Privacidad. Describen lo que NEXUS realmente guarda (docs/NEXUS_DATABASE_SPEC.md §5).
// Antes de publicar el bot: completa [Tu nombre / contacto] y haz que alguien con conocimientos legales los revise.

type Doc = { title: string; updated: string; draft: string; sections: { h: string; p: string[] }[] };

export const LEGAL: Record<"es" | "en", { terms: Doc; privacy: Doc }> = {
  es: {
    terms: {
      title: "Términos de servicio",
      updated: "Última actualización: noviembre de 2026",
      draft: "Borrador: revísalo y completa los datos de contacto antes de publicar el bot.",
      sections: [
        { h: "1. Qué es NEXUS", p: ["NEXUS BOT es un bot de Discord con un panel web para configurar bienvenidas, moderación, roles, tickets, niveles y otras funciones en servidores de Discord.", "Al añadir NEXUS a un servidor o usar el panel aceptas estos términos y las Condiciones de Discord."] },
        { h: "2. Uso permitido", p: ["Solo quien tenga permiso para administrar un servidor puede configurarlo, o quien haya recibido acceso desde la página Permisos.", "No está permitido usar NEXUS para acosar, enviar spam, eludir sanciones de Discord ni infringir la ley.", "Los comandos personalizados y mensajes que crees son tu responsabilidad."] },
        { h: "3. Economía virtual", p: ["Las monedas, niveles y artículos de NEXUS son puntos virtuales sin valor monetario. No se pueden comprar con dinero ni canjear fuera del servidor."] },
        { h: "4. Disponibilidad", p: ["NEXUS se ofrece «tal cual». Podemos cambiar o retirar funciones, y puede haber interrupciones.", "Podemos dejar de dar servicio a servidores que incumplan estos términos."] },
        { h: "5. Contacto", p: ["[Tu nombre o el del proyecto] · [correo o servidor de soporte]"] },
      ],
    },
    privacy: {
      title: "Política de privacidad",
      updated: "Última actualización: noviembre de 2026",
      draft: "Borrador: refleja lo que el código guarda hoy. Revísalo y completa el contacto antes de publicar el bot.",
      sections: [
        { h: "Qué datos guardamos", p: [
          "De quien entra al panel: ID, nombre y avatar de Discord, idioma y zona horaria, sesiones (dispositivo e IP) y los tokens de Discord cifrados.",
          "De cada servidor: nombre, icono, número de miembros y la configuración de los módulos.",
          "De los miembros: casos de moderación, notas del staff, experiencia y nivel, saldo y movimientos de la economía, tickets, sugerencias y votos, participaciones en sorteos.",
          "Estadísticas diarias agregadas (entradas, salidas, comandos usados).",
          "Si el servidor activa «Actividad de voz»: en qué canal de voz entró cada miembro, cuándo entró y salió y cuánto tiempo estuvo. Se conserva entre 7 y 365 días, según elija el servidor (90 por defecto).",
        ] },
        { h: "Qué NO guardamos", p: [
          "El contenido de los mensajes. Los logs de mensajes borrados o editados se envían al canal de logs del servidor y no se guardan en nuestra base de datos.",
          "Las transcripciones de tickets se envían como archivo al canal elegido; no las almacenamos.",
          "El audio de los canales de voz: NEXUS nunca escucha, graba ni guarda lo que se dice.",
          "AutoMod guarda solo un fragmento de hasta 200 caracteres del mensaje detectado, durante 30 días.",
        ] },
        { h: "IA de moderación (si el servidor la activa)", p: [
          "El texto del mensaje y las reglas del servidor se envían a Anthropic (Claude) para clasificarlo. No se envían nombres ni IDs.",
          "Guardamos la categoría, la puntuación y una explicación corta durante 90 días, sin el texto del mensaje.",
        ] },
        { h: "Integraciones", p: ["Para YouTube, RSS, GitHub y Twitch solo consultamos fuentes públicas y guardamos los IDs de las publicaciones ya avisadas durante 30 días."] },
        { h: "Cuánto tiempo", p: [
          "Si NEXUS sale de un servidor, sus datos se borran 30 días después (salvo que vuelva antes).",
          "Historial de cambios del panel: 180 días. Sesiones caducadas: 7 días.",
        ] },
        { h: "Tus derechos", p: [
          "Puedes borrar tu cuenta del panel en «Mi cuenta → Eliminar mis datos».",
          "Los administradores pueden expulsar a NEXUS para iniciar el borrado de los datos del servidor.",
          "Para cualquier otra solicitud: [correo o servidor de soporte].",
        ] },
      ],
    },
  },
  en: {
    terms: {
      title: "Terms of Service",
      updated: "Last updated: November 2026",
      draft: "Draft: review it and fill in the contact details before making the bot public.",
      sections: [
        { h: "1. What NEXUS is", p: ["NEXUS BOT is a Discord bot with a web dashboard to configure welcomes, moderation, roles, tickets, levels and other features in Discord servers.", "By adding NEXUS to a server or using the dashboard you accept these terms and Discord's Terms."] },
        { h: "2. Acceptable use", p: ["Only people allowed to manage a server, or given access on the Permissions page, can configure it.", "You may not use NEXUS to harass, spam, evade Discord sanctions or break the law.", "Custom commands and messages you create are your responsibility."] },
        { h: "3. Virtual economy", p: ["NEXUS coins, levels and items are virtual points with no monetary value. They can't be bought with money or redeemed outside the server."] },
        { h: "4. Availability", p: ["NEXUS is provided “as is”. Features may change or be removed, and there may be outages.", "We may stop serving servers that break these terms."] },
        { h: "5. Contact", p: ["[Your name or the project's] · [email or support server]"] },
      ],
    },
    privacy: {
      title: "Privacy Policy",
      updated: "Last updated: November 2026",
      draft: "Draft: it reflects what the code stores today. Review it and fill in the contact before making the bot public.",
      sections: [
        { h: "What we store", p: [
          "For dashboard users: Discord ID, name and avatar, language and time zone, sessions (device and IP) and encrypted Discord tokens.",
          "For each server: name, icon, member count and module configuration.",
          "For members: moderation cases, staff notes, XP and level, economy balance and transactions, tickets, suggestions and votes, giveaway entries.",
          "Aggregated daily statistics (joins, leaves, commands used).",
          "If the server enables \"Voice activity\": which voice channel each member joined, when they joined and left and how long they stayed. Kept for 7 to 365 days, as the server chooses (90 by default).",
        ] },
        { h: "What we DON'T store", p: [
          "Message content. Deleted/edited message logs are sent to the server's log channel and not stored in our database.",
          "Ticket transcripts are sent as a file to the chosen channel; we don't keep them.",
          "Voice channel audio: NEXUS never listens to, records or stores what is said.",
          "AutoMod keeps only an excerpt of up to 200 characters of a detected message, for 30 days.",
        ] },
        { h: "AI moderation (if the server enables it)", p: [
          "The message text and the server rules are sent to Anthropic (Claude) for classification. No names or IDs are sent.",
          "We keep the category, score and a short explanation for 90 days, without the message text.",
        ] },
        { h: "Integrations", p: ["For YouTube, RSS, GitHub and Twitch we only read public sources and keep the IDs of already-announced posts for 30 days."] },
        { h: "How long", p: [
          "If NEXUS leaves a server, its data is deleted 30 days later (unless it comes back first).",
          "Dashboard change history: 180 days. Expired sessions: 7 days.",
        ] },
        { h: "Your rights", p: [
          "You can delete your dashboard account under “My account → Delete my data”.",
          "Admins can remove NEXUS to start deleting the server's data.",
          "For any other request: [email or support server].",
        ] },
      ],
    },
  },
};
