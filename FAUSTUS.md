# Shannon's Hoard — capacidades para Faustus

Estado: v0.1.0, candidato (no registrado en Hub). Arranque explícito `python -m shannon` (puerto 5245). MCP stdio `python -m shannon.mcp_server`.

Correcciones1983 preparadas sobre0777ef9, pendientes de revisión e integración junto aecosystem1936. Espacio propio shannon y proyectoFaustus74d2bc0f38db.38pruebas pasan,2omitidas por falta de compiladorC;8regresiones de revisión incluyen MCPstdio real. Interfaz probada enBrave con circuitos inventados.

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
