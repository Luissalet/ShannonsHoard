# Objetivos futuros

Base, correcciones, panel y herramientas integrados enMain. Conector nativo y arranque explícito delHub comprobados por separado. El estado de integración no equivale a aprobación de revisión ni a prueba física. README/FAUSTUS describen la disponibilidad actual.

1. Análisis en alterna y transitorio (filtro RC del ADC, tiempo de asentamiento) y ruido.
2. Sensores digitales (I2C/SPI): direcciones, pull-ups, niveles lógicos y velocidad del bus contra el firmware.
3. Más placas (ESP32-S3/C3, STM32 Nucleo) y una tabla de pines editable desde la interfaz.
4. Calibración desde lecturas reales: ajustar R25/beta/offset con incertidumbre y regenerar la tabla.
5. Caja con soportes de tornillo, ventilación y prensaestopas, enviada directamente al módulo CAD de Vulcan.
6. Lectura de esquemas KiCad (.kicad_sch) además de la netlist.
