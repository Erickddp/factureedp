"""Texto de una constancia de prueba con el MISMO formato que extrae pypdf de la del SAT (datos inventados)."""
CSF_FISICA = """Página [1] de [3]
CÉDULA DE IDENTIFICACIÓN FISCAL
XIAJ800101ABC
Registro Federal de Contribuyentes
JUAN XENON AGUILAR
Nombre, denominación o razón
social
idCIF: 12345678901
VALIDA TU INFORMACIÓN
FISCAL
CONSTANCIA DE SITUACIÓN FISCAL
Lugar y Fecha de Emisión
BENITO JUAREZ , CIUDAD DE MEXICO A
16 DE MARZO DE 2026
XIAJ800101ABC
Datos de Identificación del Contribuyente:
RFC: XIAJ800101ABC
CURP: XIAJ800101HDFXGN09
Nombre (s): JUAN
Primer Apellido: XENON
Segundo Apellido: AGUILAR
Fecha inicio de operaciones: 01 DE ENERO DE 2018
Estatus en el padrón: ACTIVO
Fecha de último cambio de estado: 20 DE JUNIO DE 2018
Nombre Comercial:
Datos del domicilio registrado
Código Postal:03100 Tipo de Vialidad: AVENIDA (AV.)
Nombre de Vialidad: AVENIDA INSURGENTES Número Exterior: 19
Número Interior:4 Nombre de la Colonia: DEL VALLE
Nombre de la Localidad: BENITO JUAREZ Nombre del Municipio o Demarcación Territorial: BENITO
JUAREZ
Nombre de la Entidad Federativa: CIUDAD DE MEXICO Entre Calle: CALLE UNO Página [1] de [3]
Y Calle: CALLE DOS
Actividades Económicas:
Orden Actividad Económica Porcentaje Fecha Inicio Fecha Fin
1 Asalariado 80 01/01/2018
2 Otros servicios relacionados con la contabilidad 10 16/03/2026
4 Servicios de contabilidad y auditoría 5 16/03/2026
3 Servicios de apoyo para efectuar trámites legales 5 16/03/2026
Regímenes:
Régimen Fecha Inicio Fecha Fin
Régimen de Sueldos y Salarios e Ingresos Asimilados a Salarios 01/01/2018
Régimen Simplificado de Confianza 16/03/2026
Obligaciones:
Descripción de la Obligación Descripción Vencimiento Fecha Inicio Fecha Fin
Pago provisional mensual de ISR. Régimen Simplificado de
Confianza.
A más tardar el día 17 del mes de calendario
inmediato posterior a aquél al que corresponda
el pago
16/03/2026
Pago definitivo mensual de IVA. Régimen Simplificado de
Confianza.
A más tardar el día 17 del mes inmediato
posterior al periodo que corresponda.
16/03/2026
Ajuste anual de ISR correspondiente a la declaración anual.
Régimen Simplificado de Confianza.
A más tardar el día 30 del mes de abril del
ejercicio siguiente
16/03/2026
Sus datos personales son incorporados y protegidos en los sistemas del SAT
Cadena Original Sello: ||2026/03/16 12:56:05|XIAJ800101ABC|CONSTANCIA DE SITUACIÓN FISCAL|2000010888888|U2Fsd||
"""

CSF_MORAL = CSF_FISICA.replace("XIAJ800101ABC", "XIA190128J61").replace(
    "Nombre (s): JUAN\nPrimer Apellido: XENON\nSegundo Apellido: AGUILAR", "Denominación/Razón Social: XENON INDUSTRIAL ARTICLES SA DE CV\nRégimen Capital: SOCIEDAD ANONIMA DE CAPITAL VARIABLE"
).replace("CURP: XIAJ800101HDFXGN09\n", "").replace(
    "Régimen de Sueldos y Salarios e Ingresos Asimilados a Salarios 01/01/2018\nRégimen Simplificado de Confianza 16/03/2026",
    "Régimen General de Ley Personas Morales 01/01/2019")
