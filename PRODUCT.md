# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Administradores y moderadores de servidores de Discord que configuran Zaay y gestionan las funciones del servidor desde la web.

## Product Purpose

Zaay es un bot de Discord para moderación, protección, automatización y utilidades de servidores. La web permite conocer el bot, consultar comandos y estado, y conectar una cuenta de Discord para preparar y enviar embeds a servidores administrados.

## Positioning

La página reúne la información pública del bot y una herramienta autenticada para crear y enviar embeds al servidor y canal que el administrador elija.

## Operating Context

La experiencia es en español. Los administradores usan la web desde escritorio y móvil; la configuración de embeds depende de la sesión OAuth de Discord y de los permisos disponibles para Zaay en el servidor y canal elegidos.

## Capabilities and Constraints

- La portada, catálogo de comandos, estado del bot y constructor de embeds son rutas de una sola página en `website/index.html`.
- El estado público se consulta desde `/api/status`, que incluye el avatar del bot cuando está disponible.
- Los comandos se consultan desde `/api/commands`.
- El constructor autentica mediante OAuth de Discord, lista servidores y canales accesibles, crea una vista previa, permite revisar/copiar JSON y envía embeds por `/api/discord/send-embed`.
- El backend conserva sus verificaciones de sesión, CSRF, permisos de administración y permisos del canal; la interfaz no debe eludirlas.
- Se mantienen las capacidades existentes del editor, incluidos límites de Discord y validación de URLs.
- El envío debe verificarse sin publicar mensajes de prueba en servidores reales.

## Brand Commitments

El nombre es Zaay (algunas referencias técnicas existentes usan `Zayy`). La interfaz debe priorizar negro y blanco con violeta eléctrico; se permiten colores complementarios de forma medida. La acción principal de la portada es invitar a Zaay.

## Evidence on Hand

- Código y copy actuales de la web en `website/index.html`.
- Estado real y avatar del bot entregados por `/api/status`.
- Catálogo real entregado por `/api/commands`.
- No hay testimonios ni métricas de clientes confirmadas; no inventarlos.

## Product Principles

- Mantener claras y visibles las capacidades y el estado real del bot.
- Ayudar al administrador a elegir con precisión el servidor y el canal de destino.
- Reflejar cada cambio del editor inmediatamente en la vista previa.
- Explicar límites, errores y permisos con pasos de recuperación concretos.
- Respetar OAuth, CSRF y permisos del backend.
