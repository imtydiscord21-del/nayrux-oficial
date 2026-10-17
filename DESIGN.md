# Design system de Zaay

## Dirección

La experiencia sigue de cerca la composición de zayybot.xyz: fondo negro con una red tenue de estrellas, navegación centrada en una cápsula, avatar y nombre del bot centrados, métricas e información en tarjetas oscuras de bordes finos. El catálogo usa búsqueda y filtros en chips; el constructor presenta pestañas por tipo de contenido y una vista previa de Discord. El contenido, la identidad y las funciones siguen siendo los de Zaay.

## Tokens

- Fondo: `#07080c`; superficies: `#0b0c10` y `#101116`.
- Texto: `#f4f5f9`; texto secundario: `#9b9daa`.
- Acción violeta: `#5865f2`; acento suave: `#8790ff`.
- Estado: verde `#54d39a` para conexión y rojo `#f07583` para desconexión.
- Tipografía: IBM Plex Sans; encabezados en pesos 700–800.
- Radios: `16–24px`; ritmo adaptable mediante `clamp()`.

## Interacción y accesibilidad

- La acción principal de la portada es «Invitar a Zaay».
- El constructor mantiene la vista previa sincronizada, la identidad real del bot y el JSON revisable/copible.
- En escritorio (900 px o más), el editor y la vista previa se muestran en paralelo. En tabletas y móviles, Editar y Vista previa son controles accesibles con estado `aria-pressed`; el panel Editar aparece inicialmente. La portada pasa a una sola columna en tabletas estrechas y las estadísticas se ordenan en filas completas en teléfono.
- Anime.js anima el titular principal por caracteres y revela una vez las secciones promocionales al entrar en pantalla. Los controles mantienen respuestas breves; los campos del editor no se desplazan al usarlos.
- `prefers-reduced-motion` deja el texto y las secciones visibles sin movimiento.
- Foco visible de 3px, estados de validación y carga, y etiquetas de límites visibles.

## Componentes propios

La constelación de fondo, el hero centrado, las tarjetas de funciones, los filtros del catálogo y el constructor con pestañas forman una composición consistente. La tarjeta del embed replica la presentación de Discord y su acento lateral sigue el color editable que verá la persona en Discord.
