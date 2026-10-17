# Design system de Zaay

## Dirección

La portada se compone como una hoja editorial de turno: identidad y estado reales del bot en una placa oscura, y contenido de moderación en una superficie clara. Las vistas operativas comparten esta identidad, con el constructor como herramienta de dos paneles en escritorio y de panel intercambiable en móvil.

## Tokens

- Fondo: `#f7f6f9`; superficies: `#ffffff`.
- Tinta: `#111014`; superficie oscura: `#0a090d`; texto oscuro: `#fbfaff`.
- Acción violeta: `#7138e8`; violeta suave: `#b99bff`; violeta pálido: `#eee7ff`.
- Estado: verde `#37c987` para conexión y rojo `#ec7080` para desconexión.
- Tipografía de interfaz: IBM Plex Sans; titulares editoriales: Instrument Serif con Georgia como respaldo.
- Radios base: `16px`; ritmo adaptable mediante `clamp()`.

## Interacción y accesibilidad

- La acción principal de la portada es invitar Zaay.
- El constructor mantiene la vista previa sincronizada, la identidad real del bot y el JSON revisable/copible.
- En móvil, Editar y Vista previa son controles accesibles con estado `aria-pressed`; el panel Editar aparece inicialmente. La portada pasa a una sola columna en tabletas estrechas y las estadísticas se ordenan en filas completas en teléfono.
- Movimiento breve para navegación y aparición de vistas previas; `prefers-reduced-motion` elimina transiciones y animación no esencial.
- Foco visible de 3px, estados de validación y carga, y etiquetas de límites visibles.

## Componentes propios

La placa de identidad vertical, la ficha de estado, las líneas de catálogo tipográficas y la tarjeta de embed que replica la presentación de Discord son patrones de este producto. Los colores de marca enmarcan la interfaz; el acento lateral del embed sigue el color editable que verá la persona en Discord.
