# Shannon's Hoard — capacidades para Faustus

Lecturas MCP declaradas: shannon_examples, shannon_parts, shannon_firmware_header y shannon_enclosure. Devuelven datos o artefactos enmemoria, sin guardar ficheros/registros, y están disponibles en modoPlan. Check, estudio y evaluación de medidas conservan su persistencia. Sin cambios de permisos en Faustus. Conjunto40pruebas positivas y2omitidas por detección específica deGCC/cc.

Integración de familia1988: panel canónico mediante `/api/copilot`, borrador actual y última operación con su entrada exacta. Usa la conversación y los modelos globales de Faustus. Descubrir MCP no arranca HTTP; el Hub dispone de arranque explícito con puerto adaptable. Sin contrato HTTP agent; las9 herramientas propias se exponen por MCPstdio.

Estado: v0.1.0, integrado en main y visible en el Hub (arranque explícito). Arranque explícito `python -m shannon` (puerto 5245). MCP stdio `python -m shannon.mcp_server`.

Correcciones1983 y familia1988 integradas conecosystem1936, sin revisión aprobada nueva; conservar los votos históricos. Espacio propio shannon y proyectoFaustus74d2bc0f38db.38pruebas pasan,2omitidas por detección específica deGCC/cc;8regresiones de revisión incluyen MCPstdio real. Interfaz probada enBrave con circuitos inventados.

## Puede
- Comprobar conectividad, límites eléctricos (análisis nodal en continua en todo el rango del sensor), reguladores, corrientes y presupuesto de potencia.
- Comprobar que el firmware Arduino usa los pines como están cableados (ADC, solo entrada, ADC2 con Wi-Fi, pines sin usar o sin cablear).
- Estudiar la cadena de sensor con Monte Carlo y peor caso y decir dónde se cumple la precisión.
- Generar la tabla de conversión en C del circuito y bandas de aceptación para la prueba física; evaluar lecturas reales.
- Generar caja y tapa como especificación CAD de Vulcan.
- Importar netlists de KiCad (.net) sin lanzar KiCad.

La falta de masa de una placa impide afirmar que el diseño está limpio; no se inventa su punto de operación. Tensiones de pin/alimentación referidas a la masa de la placa. Presupuesto de reguladores externos y de placa propagado desde las cargas, independiente del orden de componentes; ciclos de alimentación explícitos. Registros únicos y publicación atómica incluso con mediciones distintas en el mismo segundo, sin dejar de leer IDs anteriores.

## No puede (todavía)
- Transitorios, filtros, ruido, autocalentamiento, no linealidad real del ADC del ESP32.
- Más placas, sensores activos (I2C/SPI), motores o actuadores.
- Leer firmware que no sea estilo Arduino; compilar firmware.

## Herramientas MCP
shannon_examples, shannon_parts, shannon_check, shannon_sensor_study, shannon_firmware_header, shannon_evaluate_measurements, shannon_enclosure, shannon_import_kicad, shannon_records.

Contraste C adicional: los dos headers generados compilan y se ejecutan conMSVC enC11, /W4 /WX; valores de calibración y sensores abiertos/cortocircuitados pasan. Las dos omisiones depytestGCC se conservan como tales.

Conector nativo permanentec157889e-09ea-46cd-b296-6182e2a5effd, servidorMCP0605ea67, 9herramientas conectado desdeMain. La aplicación HTTP conserva su parada manual; stdio funciona sin arrancarla. Datos QA aislados y ninguna inferencia solicitada para comprobar estos helpers.

## Skills for the agents that connect

This app carries procedures from the skill library of the family's workspace for the agents that connect to it: `electronics-wiring-check`, `spec-driven-development`, `verification-loop`. They are named in what an agent reads on connecting, read with `skills_list` and `skill_read`, searched and assigned with `skills_library` and `skills_assign`, and offered as prompts. The person chooses them on the skills page (`/api/agent/skills/page`) or in the hub's Skills tab; the `skills` block of `faustus-plugin.json` holds what the app asks for by default.
