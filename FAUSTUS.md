# Shannon's Hoard — capacidades para Faustus

Estado: v0.1.0, candidato (no registrado en Hub). Arranque explícito `python -m shannon` (puerto 5245). MCP stdio `python -m shannon.mcp_server`.

## Puede
- Comprobar conectividad, límites eléctricos (análisis nodal en continua en todo el rango del sensor), reguladores, corrientes y presupuesto de potencia.
- Comprobar que el firmware Arduino usa los pines como están cableados (ADC, solo entrada, ADC2 con Wi-Fi, pines sin usar o sin cablear).
- Estudiar la cadena de sensor con Monte Carlo y peor caso y decir dónde se cumple la precisión.
- Generar la tabla de conversión en C del circuito y bandas de aceptación para la prueba física; evaluar lecturas reales.
- Generar caja y tapa como especificación CAD de Vulcan.
- Importar netlists de KiCad (.net) sin lanzar KiCad.

## No puede (todavía)
- Transitorios, filtros, ruido, autocalentamiento, no linealidad real del ADC del ESP32.
- Más placas, sensores activos (I2C/SPI), motores o actuadores.
- Leer firmware que no sea estilo Arduino; compilar firmware.

## Herramientas MCP
shannon_examples, shannon_parts, shannon_check, shannon_sensor_study, shannon_firmware_header, shannon_evaluate_measurements, shannon_enclosure, shannon_import_kicad, shannon_records.
