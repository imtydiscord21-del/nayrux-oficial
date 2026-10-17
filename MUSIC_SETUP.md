# Activar música en Zaay

El código ya está preparado para `,play`, cola, saltar, pausa, volumen y repetición. Para reproducir audio hace falta conectar Lavalink, que mantiene el procesamiento de audio fuera del proceso principal del bot.

## Railway

1. Crea un servicio nuevo desde el mismo repositorio y fija su directorio raíz en `/lavalink` para que use ese `Dockerfile`.
2. En ese servicio crea `LAVALINK_SERVER_PASSWORD` como secreto, con una contraseña larga aleatoria.
3. En el servicio `zayy-bot`, añade el mismo valor como `LAVALINK_PASSWORD` y `LAVALINK_URI=http://lavalink.railway.internal:2333` (ajusta `lavalink` al nombre privado asignado al servicio, si Railway muestra otro).
4. Despliega primero Lavalink y luego `zayy-bot`. El bot cargará los comandos de música solo cuando las dos variables estén configuradas y Lavalink responda.

El servicio de Lavalink queda encendido mientras esté desplegado. Railway factura el uso de CPU y memoria: Free aporta $1 mensual, pero limita cada servicio a 0.5 GB de RAM y 3 servicios después de la prueba; Hobby tiene un mínimo de $5 mensuales e incluye $5 de uso. El proyecto ya tiene tres servicios, así que el nodo puede exigir cambiar de plan o reemplazar uno. No puedo estimar el consumo exacto sin las métricas de tu cuenta, así que revisa el panel antes de activarlo. Si Lavalink no cabe en el límite de memoria de Free, necesitará más recursos.

## Comandos

Entra primero a un canal de voz y usa:

- `,play <búsqueda o enlace>`; también acepta listas de reproducción de YouTube.
- `,queue`, `,nowplaying`, `,skip`, `,pause`, `,resume`.
- `,volume <0-200>`, `,loop track|queue|off`, `,shuffle`.
- `,stop` limpia la cola y desconecta; `,leave` desconecta.

La búsqueda por texto empieza en YouTube y, si una pista no se puede transmitir, intenta encontrarla en SoundCloud. Los enlaces directos compatibles los resuelve Lavalink. No incluye Spotify, filtros de audio ni autoplay en esta primera versión.
