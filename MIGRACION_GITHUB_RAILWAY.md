# Migración de Zaay a otra cuenta de GitHub y Railway

Inventario revisado el 18 de octubre de 2026. Este documento no contiene valores de secretos. El repositorio es público; no pegar tokens, contraseñas, URI completas ni archivos `.env` aquí.

## Ruta recomendada

Primero intenta transferir el proyecto de Railway al usuario nuevo. Railway indica que el usuario destino debe ser miembro del proyecto y que ambos usuarios deben tener un plan Hobby o Pro activo. La persona destino recibe una invitación por correo y tiene 24 horas para aceptarla. Una transferencia del proyecto evita recrear servicios y el volumen de MongoDB manualmente.

Después conecta la nueva cuenta de GitHub a Railway y vuelve a autorizar el repositorio `imtydiscord21-del/nayrux-oficial` (o su nuevo propietario) para los servicios `zayy-bot` y `lavalink`. Cambiar la cuenta conectada de Codex es independiente y se realiza desde la conexión de GitHub de Codex.

Si no se puede transferir el proyecto, crea el proyecto y servicios nuevos, respalda/restaura MongoDB antes del cambio de tráfico y vuelve a introducir las variables secretas directamente en Railway. No elimines el proyecto viejo ni su volumen hasta validar el bot y los datos del nuevo.

## GitHub

- Repositorio: `imtydiscord21-del/nayrux-oficial` (público).
- Rama desplegada: `main`.
- Último commit inventariado: `d04ca1a` (la rama puede tener commits posteriores al hacer la migración).
- Servicios Railway conectados al mismo repositorio: `zayy-bot` y `lavalink`.
- El repositorio contiene el código del bot y `lavalink/`; no contiene los secretos de Railway.
- Railway no tiene webhooks de proyecto configurados actualmente.

La transferencia nativa del repositorio conserva historial, issues, pull requests y releases; el propietario anterior queda como colaborador. Acepta la invitación en la cuenta destino y comprueba el acceso de la app de Railway al repositorio nuevo antes de cambiar cualquier dominio.

## Railway

- Proyecto: `friendly-amazement` en el workspace `imty's Projects`.
- Entorno: `production`; no había cambios pendientes al revisar.
- Región de los servicios: `sfo`.
- Bot `zayy-bot`: origen GitHub `imtydiscord21-del/nayrux-oficial`, rama `main`, raíz del repositorio, Railpack V3, 1 réplica. Dominio Railway `zaay.up.railway.app`, puerto `8080`.
- Nodo `lavalink`: mismo repositorio y rama, directorio raíz `/lavalink`, Railpack V3, 1 réplica; límite de 1 CPU y 500 MB de memoria. Sin dominio público ni proxy TCP.
- Servicio `MongoDB`: imagen `mongo:8.0`, 1 réplica, región `sfo`; comando `docker-entrypoint.sh mongod --ipv6 --bind_ip ::,0.0.0.0 --setParameter diagnosticDataCollectionEnabled=false`.
- Volumen `mongodb-volume`: 500 MB, montado en MongoDB en `/data/db`.
- Red privada de MongoDB: endpoint `mongodb`. Lavalink tiene su propio endpoint privado (en la configuración actual se consume como `lavalink.railway.internal:2333`). Al recrear servicios, comprueba el hostname privado asignado y actualiza `MONGO_URI`, `MONGO_URL` y `LAVALINK_URI` según corresponda.
- Sin buckets ni variables compartidas a nivel de entorno.
- Dominios personalizados: ninguno. El dominio actual es el dominio Railway anterior.
- Estado al revisar: `zayy-bot`, `lavalink` y `MongoDB` en `SUCCESS`.

### Variables configuradas

Los valores se ocultaron por la conexión OAuth de Railway; el inventario solo registra nombres. Railway también añade variables `RAILWAY_*` automáticamente: no hace falta recrearlas manualmente.

| Servicio | Variables propias que hay que revisar/reconfigurar |
| --- | --- |
| `zayy-bot` | `DISCORD_CLIENT_SECRET`, `DISCORD_REDIRECT_URI`, `EMOJI_GUILD_ID`, `GITHUB_WEBHOOK_SECRET`, `LAVALINK_PASSWORD`, `LAVALINK_URI`, `MONGO_URI`, `MONGO_URL`, `OWNER_IDS`, `PORT`, `TOKEN` |
| `lavalink` | `JAVA_TOOL_OPTIONS`, `LAVALINK_PASSWORD`, `LAVALINK_SERVER_PASSWORD`, `YOUTUBE_REFRESH_TOKEN` |
| `MongoDB` | `MONGOHOST`, `MONGOPASSWORD`, `MONGOPORT`, `MONGOUSER`, `MONGO_INITDB_ROOT_PASSWORD`, `MONGO_INITDB_ROOT_USERNAME`, `MONGO_URL` |

No guardes valores secretos en este archivo, GitHub, chat ni capturas. Cópielos de forma directa en el panel de Railway si Railway permite verlos; las variables selladas no se pueden leer y deben volver a emitirse desde su servicio de origen. Si se cambia el dominio, actualiza `DISCORD_REDIRECT_URI` y agrega la URL callback nueva en la configuración OAuth de Discord. El callback en el código es `/api/auth/callback`.

## Datos MongoDB

El volumen es lo que contiene la base de datos en disco. La configuración y variables del servicio no sustituyen ese contenido. Si el proyecto se transfiere dentro de Railway, verifica que el volumen siga montado en `/data/db` y que el bot conecte a la base esperada. Si creas otra instancia, realiza una exportación lógica (`mongodump`) y restauración (`mongorestore`) en un canal seguro antes de apagar la antigua; así también viajan los backups del servidor que el bot guarda en MongoDB.

La API consultada no expuso el calendario de snapshots/respaldos de Railway del volumen. Verifica en Railway → MongoDB → Volume → Backups si hay una programación activa y crea un respaldo manual antes de migrar.

## Orden de cambio seguro

1. Acepta la invitación al proyecto Railway o prepara el proyecto destino sin borrar el anterior.
2. Transfiere `nayrux-oficial` a la cuenta nueva de GitHub, o concede a Railway acceso explícito al repo nuevo.
3. Reautoriza la integración de GitHub en Railway y comprueba los orígenes de `zayy-bot` y `lavalink`.
4. Confirma el volumen de MongoDB y haz un respaldo manual. Si creaste otra instancia, migra los datos antes de cambiar tráfico.
5. Revisa las variables secretas por servicio, referencias privadas y límites de recursos.
6. Despliega `lavalink`, valida su salud y después despliega `zayy-bot`.
7. Mantén `zaay.up.railway.app` si Railway permite conservarlo; de lo contrario crea el dominio nuevo y actualiza el callback OAuth de Discord y `DISCORD_REDIRECT_URI`.
8. Comprueba login, conexión a MongoDB, comandos de estado y backup, y logs; conserva el proyecto/volumen antiguos hasta que todo funcione.

## Referencias

- [Transferir proyectos en Railway](https://docs.railway.com/projects)
- [Respaldos de volúmenes en Railway](https://docs.railway.com/volumes/backups)
- [Transferir un repositorio de GitHub](https://docs.github.com/en/repositories/creating-and-managing-repositories/transferring-a-repository)
