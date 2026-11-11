# Shannon's Hoard

Electrónica pequeña en tu PC: un circuito, el microcontrolador que lo lee, su firmware y su caja, comprobados juntos. Detecta los errores de cableado, límites y firmware que obligan a rehacer una placa; dice qué precisión tiene de verdad una cadena de sensor contando todas las tolerancias; genera la tabla de conversión del firmware que corresponde al circuito; da bandas de aceptación para la primera prueba física y dimensiona una caja para Vulcan's Hoard.

No es un editor de esquemas ni lanza KiCad: lee la exportación de netlist de KiCad o un diseño escrito en JSON.

## Qué hace

- **Diseño** (JSON): componentes, redes `REF.PIN`, cadena de sensor (elemento, variable, rango, precisión objetivo, pin ADC), firmware y tamaño de placa. Los valores que faltan se convierten en preguntas.
- **Placas con capacidades reales de cada pin**: ESP32 DevKit v1 (ADC1/ADC2, GPIO34-39 solo entrada, pines de arranque, 3,6 V), Arduino Uno, Raspberry Pi Pico; reguladores AMS1117-3.3, MCP1700-3.3 y LM7805.
- **Conectividad**: referencias o pines desconocidos, cortocircuitos, pines sin conectar, redes de un solo pin, redes sin camino en continua, falta de masa.
- **Comprobaciones eléctricas** por análisis nodal en todo el rango del sensor: sobretensión en pines, alimentación incorrecta, carriles con dos fuentes, caída del regulador, sobrecarga y disipación, corriente de LED frente al límite del pin, LED en pines solo de entrada y presupuesto de potencia.
- **Coherencia con el firmware** (C/C++ estilo Arduino): pines resueltos por `#define`/`const`, `analogRead` en el pin cableado y con ADC, salidas en pines solo de entrada, ADC2 con Wi-Fi, pines usados sin cablear o cableados sin usar.
- **Estudio del sensor**: transferencia, resolución, Monte Carlo y peor caso con todas las tolerancias, rango que cumple la precisión, saturación.
- **Tabla de firmware** en C que compila sin avisos, con su error de ida y vuelta.
- **Prueba física**: bandas de código esperadas en puntos de referencia y evaluación de las lecturas reales (pasa, falla, inestable o en el carril).
- **Caja** y tapa como especificaciones CAD de Vulcan.
- **Importación de netlist de KiCad** (.net, KiCad 6-8) con la alimentación externa indicada explícitamente.
- **Registros** de cada comprobación y estudio.

Arranque y API: ver README.md. Puerto 5245.

## Límites

Solo continua: sin transitorios, filtrado, ruido ni autocalentamiento del termistor; ADC del ESP32 ideal y lineal; tres placas y tres reguladores; lectura del firmware por patrones. Una simulación no demuestra el comportamiento de una placa real ni certifica nada; las bandas de prueba sirven para que las primeras lecturas reales digan si el modelo se sostiene.

## Skills para los agentes que se conectan

Esta app lleva procedimientos de la biblioteca de skills del espacio de trabajo de la familia para los agentes que se conectan: `electronics-wiring-check`, `spec-driven-development`, `verification-loop`. Aparecen en lo que el agente lee al conectarse, se leen con `skills_list` y `skill_read`, se buscan y asignan con `skills_library` y `skills_assign`, y se ofrecen como prompts. Se eligen en la página de skills (`/api/agent/skills/page`) o en la pestaña Skills del hub; el bloque `skills` de `faustus-plugin.json` guarda lo que la app pide por defecto.
