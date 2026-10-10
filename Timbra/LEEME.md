# Timbra — facturación CFDI 4.0

## Instalar en cualquier PC (recomendado)
1. En tu PC de desarrollo: doble clic en **CONSTRUIR_INSTALADOR.bat** (la primera vez instala Inno Setup con winget).
2. Te deja `instalador\salida\Timbra-Instalador-2.4.0.exe`. Cópialo a la PC que quieras y ábrelo: no pide administrador ni Python.
3. Timbra queda en el menú Inicio, junto al reloj (clic derecho: abrir, respaldar, carpeta de datos) y, si lo marcas, arranca con Windows.
4. Tus datos viven en `%LOCALAPPDATA%\Timbra` (base, XML, `.env` y `Respaldos` con un ZIP diario de los últimos 14 días).
   Actualizar o desinstalar no los borra. Para pasar tu información de la versión con INICIAR.bat: clic derecho al ícono →
   **Importar datos de la versión anterior…** → elige la carpeta `backend` vieja.
5. Windows puede mostrar "Windows protegió su PC" porque el instalador no está firmado: **Más información → Ejecutar de todas formas**.

## Lo nuevo en 2.0
- **Timbres**: registra cada paquete comprado; avisa al quedar pocos y no deja timbrar en cero. SW: saldo en vivo.
- **Recurrentes y favoritas** (Alt+R): igualas y rentas con día del mes; se timbran solas o te avisan. `{MES} {año}` en la descripción.
  Alt+Shift+1…9 abre tu plantilla favorita en Facturar.
- **Nómina 1.2** (Alt+E): empleados con receta (sueldos, asimilados, honorarios asimilados), Alt+Q arma la quincena, Ctrl+Enter timbra todo.
  El ISR y el IMSS los capturas tú (Timbra valida la estructura SAT, no calcula con tablas).
- **Descarga SAT**: con la e.firma del cliente pide al SAT los recibidos/emitidos del mes, los concilia contra Timbra y exporta Excel para COI.
- **Autofactura**: liga pública donde tus clientes facturan su ticket (folio + total). En la PC sólo se ve en tu red; para internet usa un túnel seguro.
- **Cobranza** (Alt+B): antigüedad de saldos por días de crédito, estado de cuenta imprimible y recordatorios por correo (manual o cada lunes).
- **PDF con tu marca**: logo y color por emisor en *Marca, nómina y e.firma*.
- **Diseño** minimalista blanco/negro con modo oscuro (Ctrl+Shift+L o el botón de tema).

## Barra de Facturar más completa y menú plegable (2.5)
- **Clientes** (Alt+G) y **Mis conceptos** (Alt+I): listas de lo que ya tienes guardado o ya facturaste, con filtro; un clic y queda cargado.
- La **descripción** del concepto ahora busca en tu catálogo, en lo ya facturado y en el **catálogo completo del SAT** (te pone la clave).
- **Más impuestos**: retención de IVA 6% (servicios especializados) y total, IEPS 8%, 25%, 26.5%, 30% y 53% (el IVA se calcula sobre
  precio + IEPS) y **«Otro impuesto o tasa…»** para armar cualquier combinación, incluido IEPS por cuota. Arrendamiento usa las mismas
  retenciones que honorarios (más la cuenta predial en el concepto).
- **Impuestos locales** con lista (ISH, cedular, 5 y 2 al millar) y el importe calculado solo. Confirma la tasa de tu estado.
- **Addendas básicas** nuevas: contrato/arrendamiento, referencia de pago y servicios médicos (informativas).
- **Modo demo a la vista**: si el emisor no tiene PAC, Facturar lo avisa, la factura sale marcada «Demo» y el PDF trae una banda
  «SIN VALIDEZ FISCAL».
- **Menú lateral**: se pliega a iconos con el botón de arriba o **Ctrl+B**, los grupos se abren y cierran, y abajo está **Mi perfil**
  (nombre, correo, rol, emisor activo, contraseña y cerrar sesión).
- Mensajes de CSD y e.firma en español claro (contraseña que no abre el .key, archivos que no son pareja).

## Clientes en masa y Pendientes (2.4)
- **Importar clientes** ahora detecta **conflictos**: si el RFC ya existe con otro nombre, CP o régimen, ves lo guardado contra lo de la hoja y
  eliges (usar la hoja / conservar lo guardado). Sin tu decisión no se cambia nada. Lo idéntico sale como "sin cambios".
- **Clientes → Revisar clientes**: datos que el SAT rechazaría (uso incompatible, nombre con SA de CV, CP…) con **Arreglar** de un clic o
  **Arreglar lo seguro**; **Duplicados** (mismo RFC → fusionar y las facturas pasan al conservado) y **Lista 69-B** del SAT.
  En **Descarga SAT** puedes marcar a tus proveedores que aparecen en la lista 69-B.
- **Pendientes** (Alt+J): todo lo que necesita una acción tuya, en un solo lugar y con su botón: facturas de lote por corregir, clientes con
  datos inválidos, cancelaciones en espera, recurrentes que fallaron, cobranza vencida, CSD por vencer y timbres bajos. El menú muestra el número.
- **Estabilidad**: se corrigió un fallo del catálogo del SAT cuando varias pantallas lo consultaban a la vez (podía dar error al facturar).

## Claves SAT y catálogo (2.3)
- **Claves SAT** (Alt+K): escribe lo que haces o vendes (“dentista”, “renta local”, “vitaminas”) y ves la clave, qué es, avisos y notas
  (IVA de servicios médicos, retenciones, cuenta predial, medicamentos). **Agregar a mi catálogo** en un clic, o **Bloquear** una clave
  en el emisor para que nunca se timbre. La pestaña *Unidades* te dice cuándo usar E48, H87, MON…
- **Productos**: *Catálogos sugeridos* por giro (contabilidad, salud con IVA o exenta, arrendamiento, tecnología…), *Importar tabla*
  (pega tu Excel; si no traes clave, Timbra te sugiere una y tú la confirmas) y búsqueda en tu catálogo.
- En cualquier buscador de clave (Facturar, Productos, perfiles de lote) ahora salen mejores resultados y un ⚠ cuando la clave es de la
  familia de medicamentos. Las orientaciones fiscales son ayuda: confírmalas con tu contador.

## Lotes desde tabla (2.2)
1. Menú **Lotes desde tabla** (Alt+L) → crea un **perfil** (una vez): serie, uso, forma de pago, en qué columna va cada dato y cómo se
   arman los conceptos con fórmulas (`servicio / 1.16`, `(monto - servicio) / 1.16`). Hay un ejemplo listo para editar.
2. Copia las filas de tu hoja (con o sin encabezados) y pégalas, o sube un CSV/Excel → **Revisar filas**. No se timbra nada todavía.
3. Cada fila muestra cliente, conceptos, total del CFDI contra lo cobrado, avisos (fecha fuera de orden, CP de otra zona, cliente nuevo,
   posible duplicado) y errores. Si el total sale un centavo distinto, Timbra lo mueve (hasta lo que permitas) y te lo marca.
4. **Timbrar la primera y revisar** → si todo bien, **Timbrar todas**. Las filas con error quedan en *Por corregir* con su **folio apartado**:
   corriges el dato y sale con el mismo folio. Puedes volver a pegar la hoja completa: lo ya timbrado se reconoce y no se duplica.
5. Al final: **Registro** (Excel con folio de la hoja, folio, UUID, total, estado) y **PDF + XML** nombrados `C-30_UUID`.

## Lo nuevo en 2.1
- **Barra de Facturar configurable** (botón junto a los tipos de comprobante): nivel *Simple* (cliente, descripción y precio),
  *Estándar* o *Completo*; prende o apaga cada campo, fija tus valores por defecto y crea **perfiles rápidos** (un clic llena
  tipo, pago, impuestos, concepto con `{MES}` y tercero). Al elegir cliente: **Repetir la última** (Alt+U).
- **A cuenta de terceros** (menú *Terceros*): guarda a los dueños/mandantes una vez y elígelos por concepto. También cuenta
  predial y pedimentos (los pedimentos se acomodan solos al formato del SAT).
- **Errores con solución**: si el PAC rechaza, ves qué pasó y qué hacer. Timbra corrige solo lo seguro: reintenta si se cayó
  internet (sin duplicar), recupera el UUID si el PAC ya lo había timbrado y re-arma la fecha si el SAT la rechazó.
- **Más estable**: nunca timbra dos veces la misma factura (doble clic o reintento), los folios no se repiten aunque timbren
  dos procesos a la vez, y si el disco o la base fallan justo después de timbrar, la factura se recupera sola del respaldo.

## Arrancar sin instalar (desarrollo)
1. Descomprime la carpeta donde quieras (ej. `C:\Timbra`).
2. Doble clic en **INICIAR.bat**. La primera vez instala todo solo (2–5 min). Si no tienes Python lo instala con winget; cierra y vuelve a abrir el .bat.
3. Se abre http://localhost:8000. Entra con el `ADMIN_EMAIL` de `backend\.env` y contraseña `cambiame`. **Cámbiala** en *PAC, addendas y usuarios*.

Para apagar: cierra la ventana negra. **ACTUALIZAR_CATALOGOS.bat** cuando el SAT cambie catálogos (normalmente en enero). Para respaldar: **RESPALDAR.bat** (guarda la base, los XML y el `.env`; súbelo a Drive).

## Poner a timbrar de verdad
Guía completa paso a paso (Finkok y SW Sapien): **GUIA_PAC.md**. Resumen:
1. **CSD de cada RFC**: el Certificado de Sello Digital (.cer, .key y su contraseña). No es la e.firma. Se tramita en el SAT con la e.firma.
2. **Timbres**: contrata un PAC (ver tabla). Te dan usuario y contraseña de pruebas y de producción.
3. En Timbra:
   - *PAC, addendas y usuarios* → **+ PAC** → elige proveedor, pega credenciales, deja "pruebas" marcado.
   - *Emisores y CSD* → **+ RFC emisor** → sube el CSD → asígnale el PAC.
   - Timbra una factura de prueba. Si sale bien, desmarca "pruebas" en el PAC y ya timbras en serio.

| PAC | Costo (consultado sep-2026) | Liga |
|---|---|---|
| **Finkok** (recomendado) | $150 + IVA/mes de 0 a 500 timbres; del 501 en adelante $0.30 + IVA c/u. Sin anualidad. Tel. (55) 4624 0181 | https://www.finkok.com/ |
| SW Sapien | 1,200 timbres $2,266 · 5,000 $5,530 · 10,000 $8,230 (paquetes “para Odoo”: confirma que sirvan por API) | https://tienda.sw.com.mx/shop |

Precios cambian: confírmalos al contratar.

## Atajos (F1 dentro de la app los muestra todos)
| Tecla | Hace |
|---|---|
| F2 | Nueva factura desde cualquier pantalla |
| Ctrl + Enter | Timbrar |
| Ctrl + K | Buscar pantalla o acción (cambiar de RFC, ir a clientes…) |
| F9 | Consola de depuración |
| Alt + C / Alt + A | Ir al cliente / agregar concepto |
| Alt + 1…4 | Factura · Público en general · Nota de crédito · Traslado |
| Enter en conceptos | Siguiente campo; al final crea otra fila (como Excel) |
| ↑ ↓ | Misma columna, fila de arriba o abajo |
| Ctrl + D / Ctrl + Supr | Duplicar / borrar concepto |
| =14500/1.16 | En precio: haz la cuenta ahí mismo (quitar IVA) |
| Alt + I (en Clientes) | Importar clientes de Excel |

## Importar tus clientes
Clientes → **Importar de Excel** (o Alt + I). Copia tu tabla en Excel con la fila de encabezados y pégala. Tus columnas
`NOMBRE, RFC, CP, DIRECCION, REGIMEN_FISCAL, CORREO_O_CONTACTO` funcionan tal cual; opcionales al final:
`USO_CFDI, FORMA_PAGO, METODO_PAGO, NOTAS`. El régimen puede ir en texto o clave; "correo | teléfono" se separa solo;
el CP al que Excel le quitó el cero se corrige. Antes de guardar te muestra fila por fila qué está mal.
Si son pacientes de un consultorio elige "D01 Honorarios médicos" como uso por defecto.

## Cuando algo falle
Presiona **F9**: la consola muestra cada paso (sellar, PAC, respaldo, correo) con su tiempo y el error exacto con traza.
Cada error en pantalla trae "Ver detalle" que te lleva directo a su registro. **Copiar** lo deja listo para pegárselo a
Claude Code. En *Servicios* ves si la BD, el PAC, el correo y los CSD están bien. Todo queda también en
`backend\datos\logs\timbra.log`.

## IVA 16%, 8% frontera, 0% y exento
- En *Emisores y CSD* marca **Región fronteriza** al RFC que esté en el padrón del estímulo (prorrogado al 31/12/2026).
  Sus conceptos nuevos salen con IVA 8% y "Pasar mi catálogo a 8%" convierte sus productos.
- En cada concepto eliges la combinación: IVA 16%, 8%, 0%, exento, honorarios/arrendamiento PF→PM (ret. ISR 10% + IVA 2/3),
  RESICO→PM (ret. ISR 1.25% + IVA 2/3), honorarios médicos exentos (ret. ISR 10%) y fletes.
- La retención de IVA siempre es 2/3 del IVA: **10.6667% con 16%** y **5.3333% con 8%**. Si las mezclas, no te deja timbrar.
- **Calculadora** (menú o Ctrl+K): pones lo que tienes (sin IVA, con IVA o lo que te depositan) y te da el precio exacto
  al centavo; "Facturar esto" manda los conceptos a Facturar. Dentro de Facturar, **F4** en el precio hace lo mismo por concepto.

## Uso diario
- **F2** en cualquier pantalla → Facturar. **Ctrl+Enter** → Timbrar.
- Escribe RFC o nombre del cliente; si no existe, se da de alta al facturar.
- Escribe la descripción y elige del catálogo (ya trae servicios contables, honorarios, arrendamiento, consultas médicas, etc.).
- **Plantillas**: arma la iguala o renta mensual una vez → "Guardar como plantilla" → el mes siguiente eliges la plantilla y timbras.
- **Complementos de pago**: elige cliente, captura lo que te pagó por factura, timbra.
- **Facturas**: PDF, XML, reenviar, clonar, guardar como plantilla, cancelar (motivos 01–04), ZIP de XML del mes y reporte para Excel.

Cada XML timbrado se guarda también en `backend\datos\respaldo_xml\RFC\AAAA-MM\`.

## Seguir mejorándolo con Claude Code
1. Instala Claude Code (guía oficial: https://docs.claude.com/en/docs/claude-code/overview).
2. Abre una terminal en la carpeta de Timbra y escribe `claude`.
3. Claude Code lee **CLAUDE.md** solito: ahí está la memoria del proyecto (arquitectura, reglas de oro, reglas SAT, backlog). Cuando termine algo, pídele que actualice el backlog de CLAUDE.md.
4. Comandos listos:
   - `/probar` → corre todas las pruebas y arregla lo que falle.
   - `/nueva-funcion importar clientes desde Excel` → implementa siguiendo las reglas.
5. Si cambió el front: **COMPILAR_FRONT.bat** (requiere Node.js LTS).
