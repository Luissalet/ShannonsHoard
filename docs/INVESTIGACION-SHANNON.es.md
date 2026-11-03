# Shannon: decisiones de la primera entrega

## Circuito elegido
Nodo de temperatura de máquina: ESP32 DevKit, divisor NTC 10k/B3950 con resistencia del 1 % en GPIO34 (ADC1, solo entrada), condensador de 100 nF, AMS1117-3.3 desde USB 5 V y LED de estado en GPIO2. Es pequeño, cubre alimentación, adquisición, firmware y caja, y tiene una prueba física barata (hielo, ambiente con termómetro de referencia, agua hirviendo).

## Representaciones y componentes integrables
- Objeto propio en JSON (componentes, redes, sensor, firmware, placa): diffable y guardable con cada resultado.
- Netlist de KiCad (.net) como formato de intercambio: se lee la exportación (S-expresión) sin lanzar KiCad ni envolver su CLI. El esquema (.kicad_sch) queda para más adelante.
- Datos de pines de placas y reguladores como tabla propia con origen en los pinouts y hojas de datos públicos.
- Solución nodal propia con NumPy (BSD). Se evaluó ngspice/PySpice: más completos, pero un binario externo y licencias mixtas para algo que en continua cabe en 200 líneas; se reconsiderará para transitorios.

## Coherencia netlist–pines–firmware
Comprobada en las tres direcciones: el firmware lee/escribe pines que existen y están cableados; los pines cableados se usan; el pin del sensor tiene ADC (y ADC1 si hay Wi-Fi); las salidas no van a pines solo de entrada; las tensiones de todos los pines quedan dentro del límite de la placa en todo el rango del sensor. Tres variantes rotas del ejemplo lo demuestran.

## Rangos y tolerancias
Monte Carlo (uniforme dentro de cada banda) y peor caso con todas las tolerancias en un extremo. Con piezas del 1 % y referencia ADC del 1 %, el nodo cumple ±2,5 °C de 10 a 84 °C y no en los extremos; con piezas del 0,1 % el rango se amplía. La tabla de firmware se genera del circuito nominal y compila sin avisos.

## Prueba física posterior
Bandas de código esperadas en cada punto de referencia, ensanchadas por ruido de medida; evaluación de lecturas reales con veredictos pasa/falla/inestable/carril y monotonía. No se arranca hardware desde aquí.

## Plataforma y licencias
Python con NumPy, FastAPI y MCP; funciona en Windows sin compiladores. Nada de KiCad, ngspice ni bibliotecas de terceros se distribuye.

## API, MCP y objetos
HTTP `/api/check`, `/api/sensor`, `/api/firmware/header`, `/api/measurements`, `/api/enclosure`, `/api/import/kicad`, `/api/records`; MCP `shannon_*` (9 herramientas). Objetos: diseño, informe de comprobación, estudio de sensor, plan de prueba, evaluación de lecturas, especificación de caja.

## Reutilizar frente a reimplementar
No se construye un CAD electrónico: el esquema se dibuja en KiCad y aquí se comprueba lo que KiCad no comprueba (firmware, rangos con tolerancias, prueba física, caja). Lo propio es la conexión entre esas piezas.
