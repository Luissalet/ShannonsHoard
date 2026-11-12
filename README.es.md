# Shannon's Hoard

Comprobador local de electrónica pequeña: un circuito, el microcontrolador que lo lee, su firmware y su caja, comprobados juntos. [English](README.md)

![Shannon's Hoard](app-icon.png)

## Qué es

Shannon detecta los errores de cableado, de límites y de firmware que obligan a rehacer una placa, dice qué precisión tiene de verdad una cadena de sensor una vez contadas todas las tolerancias, genera la tabla de conversión del firmware que corresponde al circuito, da bandas de aceptación para la primera prueba física y dimensiona una caja para Vulcan's Hoard.

No es un editor de esquemas ni lanza KiCad: lee la exportación de netlist de KiCad o un diseño escrito en JSON.

## Qué hace

- **Objeto de diseño** (JSON): componentes (resistencia, condensador, termistor NTC, LED, conector, fuente, regulador, placa con microcontrolador, genérico), redes como listas `REF.PIN`, cadena de sensor (elemento, variable, rango, precisión objetivo, pin ADC), firmware y tamaño de placa. Los valores admiten `10k`, `4k7`, `100n`. Los que faltan (termistor sin beta, resistencia sin valor, fuente sin tensión) vuelven como preguntas.
- **Placas con las capacidades reales de cada pin**: ESP32 DevKit v1 (ADC1/ADC2, GPIO34-39 solo de entrada, pines de arranque, límite de 3,6 V), Arduino Uno (A0-A5, 5 V) y Raspberry Pi Pico (GP26-28 con ADC). Reguladores: AMS1117-3.3, MCP1700-3.3 y LM7805.
- **Conectividad**: referencias o pines desconocidos, pines en dos redes (cortocircuitos), pines pasivos sin conectar, redes de un solo pin, redes sin camino en continua y falta de masa.
- **Comprobaciones eléctricas** por análisis nodal en continua a lo largo de todo el rango del sensor: sobretensión en pines (un divisor de 5 V hacia un pin de 3,3 V), pines de alimentación con tensión incorrecta, carriles alimentados dos veces, caída de tensión del regulador, sobrecarga y disipación, corriente de LED frente al límite del pin, LED en pines solo de entrada y presupuesto de potencia por carril y fuente.
- **Coherencia con el firmware** (C/C++ estilo Arduino): pines resueltos mediante `#define`, `const` y `constexpr`; `analogRead` en el pin cableado del sensor y en un pin ADC; salidas que no estén en pines solo de entrada; pines ADC2 con Wi-Fi activo; pines usados en el código pero no cableados, o cableados pero sin usar; resolución del ADC fijada en el código.
- **Estudio del sensor**: transferencia de la variable física al código ADC, resolución por LSB, Monte Carlo sobre todas las tolerancias (resistencias, R25 y beta del termistor, alimentación, referencia del ADC) y peor caso con cada tolerancia en un extremo; rango en el que se cumple la precisión objetivo; saturación; monotonía.
- **Tabla de firmware**: una cabecera C (`sensor_table.h`) con la tabla código-valor del circuito nominal y su función de interpolación, con el error de ida y vuelta; compila sin avisos con `-std=c99 -Wall -Werror`.
- **Prueba física**: bandas de código aceptables en puntos de referencia (baño de hielo, habitación con termómetro de referencia, agua hirviendo) a partir del estudio de tolerancias, y evaluación de las lecturas tomadas en la placa real: pasa, falla, inestable o en el carril (sensor abierto o en cortocircuito), además de monotonía.
- **Caja**: caja abierta con suelo, orificio para cable y tapa como especificaciones CAD (mm) para Vulcan's Hoard, dimensionada con la placa y su componente más alto; la especificación compila con el motor CAD de Vulcan.
- **Importación de netlist de KiCad** (.net, KiCad 6-8): componentes por símbolo de biblioteca, valores y tolerancias desde el campo de valor, beta del termistor desde `10k B3950`, pines de ESP32/Uno/Pico desde las funciones de pin (`IO34` → `GPIO34`) y reguladores por referencia; la alimentación externa se indica explícitamente porque una netlist solo muestra un conector.
- **Registros** de cada comprobación y estudio con el diseño exacto que usó.

Ejemplo incluido: un nodo de temperatura de máquina (ESP32, divisor con NTC de 10k en GPIO34, AMS1117 desde USB 5 V, LED de estado) que pasa limpio, cumple ±2,5 °C de 10 a 84 °C con piezas al 1 % y no lo cumple en los extremos, más tres variantes rotas (firmware que lee otro pin, divisor alimentado a 5 V, LED en un pin solo de entrada) que las comprobaciones detectan.

## Cómo ejecutarlo

Requiere Python 3.11 o superior.

```
python -m venv .venv
.venv\Scripts\pip install -e .[test]
.venv\Scripts\python -m shannon            # http://127.0.0.1:5245
.venv\Scripts\python -m pytest
```

## API HTTP

| Método | Ruta | Para qué |
| --- | --- | --- |
| GET | `/api/health` | `{service: "shannon-hoard"}` |
| GET | `/api/parts` | placas con capacidades de pin y reguladores |
| GET | `/api/examples`, `/api/examples/{id}` | diseño resuelto y variantes rotas (`machine_sensor:wrong_pin`, …) |
| POST | `/api/check` | `{design}` → incidencias, punto de funcionamiento, presupuesto de potencia, uso de pines del firmware |
| POST | `/api/sensor` | `{design, samples, seed}` → transferencia, errores, rango de precisión, tabla de firmware, plan de pruebas |
| POST | `/api/firmware/header` | `{design}` → `sensor_table.h` |
| POST | `/api/measurements` | `{design, readings: [{value, codes}], noise_lsb}` → veredictos |
| POST | `/api/enclosure` | `{design, wall, clearance, cable_hole}` → especificaciones CAD de Vulcan |
| POST | `/api/import/kicad` | `{netlist, name, supplies: [{net, voltage, max_ma}]}` |
| GET | `/api/records`, `/api/records/{id}` | comprobaciones y estudios guardados |

## Límites

Solo continua: sin transitorios, filtrado, ruido, autocalentamiento del termistor ni efectos de muestreo del ADC; los LED y las salidas del microcontrolador se tratan en el presupuesto de potencia, no en el solver nodal. El ADC del ESP32 se modela ideal y lineal; el real necesita calibración. Solo hay tres placas y tres reguladores descritos. La lectura del firmware es por patrones para código estilo Arduino, no un compilador. Una simulación no demuestra el comportamiento de una placa real y nada de esto certifica el cumplimiento de normas; las bandas de prueba sirven para que las primeras lecturas reales digan si el modelo se sostiene.

## Conexión con Faustus y Hoard Hub

`faustus-plugin.json` registra la app como plugin de Faustus. El Hub arranca la aplicación web de forma explícita, en un puerto que se adapta si el predeterminado está ocupado. Faustus recibe un panel con el borrador actual del circuito (incluido JSON incompleto) y la última operación con su entrada exacta y el resumen del resultado; la conversación, el modelo y las herramientas se quedan en Faustus.

MCP (stdio, `python -m shannon.mcp_server`) no arranca ninguna aplicación HTTP.

| Grupo | Herramientas |
| --- | --- |
| Lecturas puras (indicación de solo lectura, usables en modo Plan de Faustus; no crean registros ni archivos) | `shannon_examples`, `shannon_parts` |
| Comprobaciones y estudios | `shannon_check`, `shannon_sensor_study`, `shannon_evaluate_measurements` |
| Firmware, caja e importación | `shannon_firmware_header`, `shannon_enclosure`, `shannon_import_kicad` |
| Registros | `shannon_records` |

La app lleva además procedimientos de la biblioteca de skills de la familia para los agentes que se conectan (`electronics-wiring-check`, `spec-driven-development`, `verification-loop`). Aparecen en lo que el agente lee al conectarse, se leen con `skills_list` y `skill_read`, se buscan y asignan con `skills_library` y `skills_assign`, y se ofrecen como prompts. Se eligen en `/api/agent/skills/page` o en la pestaña Skills del Hub.

## Estructura del proyecto

| Ruta | Contenido |
| --- | --- |
| `shannon/circuit.py`, `analysis.py` | Modelo de netlist y análisis nodal en continua |
| `shannon/design.py`, `parts.py` | Objeto de diseño y biblioteca de placas y reguladores |
| `shannon/firmware.py` | Análisis de pines del firmware y generación de la cabecera |
| `shannon/kicad.py` | Importación de netlist de KiCad |
| `shannon/service.py`, `app.py`, `static/` | Servicio, API HTTP y página web |
| `shannon/mcp_server.py` | Servidor MCP |
| `shannon/hoard_link/` | Código compartido de la familia Hoard |
| `tests/` | Pruebas (dos comprobaciones necesitan GCC y se omiten sin él) |
| `docs/` | Notas de investigación (en español) |

## Créditos

Python con NumPy; la cabecera generada es C99 estándar.
