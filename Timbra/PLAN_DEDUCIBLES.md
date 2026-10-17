# Plan: constancia fiscal, gastos deducibles y «Mis facturas» sin cuenta

Estado: **plan, sin construir** (16-oct-2026). Lo único aplicado de este pedido es que la e.firma dura 2 horas.
Nada de aquí cambia lo que ya funciona: todo va en tablas nuevas, rutas nuevas y una sección nueva de la pantalla XML del SAT.

---

## 1. Qué se quiere

1. Subir la **Constancia de Situación Fiscal (CSF)** del contribuyente.
2. Al bajar las **facturas recibidas**, que Timbra **sugiera** si cada gasto es deducible o no, usando la CSF (régimen,
   actividades, código postal) y los datos del XML.
3. Separar **Deducibles / No deducibles / Por revisar**. La sugerencia **nunca es definitiva**: una persona la confirma o la
   cambia, y queda quién y cuándo.
4. Todo **dentro de la pantalla XML del SAT** (no una página nueva para quien tiene cuenta).
5. Una entrada **sin cuenta** para bajar XML y PDF con la e.firma y subir la CSF.

---

## 2. Dónde se ve (sin páginas nuevas para quien tiene cuenta)

Pantalla `/sat` (XML del SAT), pestañas que ya existen:

| Pestaña | Qué se agrega |
|---|---|
| **Descargar** | Nada en el flujo. En la tabla de comprobantes, los **recibidos** llevan una pastilla: `Deducible` · `No deducible` · `Revisar`, con «sugerido» o «confirmado». |
| **Datos** | 1) Tarjeta **«Tu constancia fiscal»** arriba: subir PDF, ver régimen, actividades, CP y fecha de la constancia; aviso si tiene más de 3 meses. 2) Sección **«Gastos»** con tres columnas o pestañas: Deducibles, No deducibles, Por revisar; totales por mes; filtros; confirmar en bloque. |

Excel y «Copiar»: el **formato maestro de 65 columnas no se toca**. La clasificación va **al final del Excel**, igual que
«Estatus SAT» y «Cancelado el»: `Deducible (sugerido)`, `Motivo`, `Deducible (confirmado)`, `Confirmó`.

---

## 3. La constancia (CSF): cómo se sube y qué se guarda

**Cómo se sube:** botón en la tarjeta «Tu constancia fiscal» (pestaña Datos). Acepta el PDF que da el SAT. Máximo 2 MB.

**Cómo se lee:** el PDF del SAT trae texto; se lee con `pypdf` (ya instalado) y se sacan:
- RFC, nombre o razón social, CURP (si es persona física), código postal del domicilio fiscal
- **Regímenes** (clave, nombre, fecha de inicio y fin)
- **Actividades económicas** (orden, nombre, porcentaje, fechas)
- Obligaciones, fecha de emisión de la constancia, idCIF

**Candados al subirla:**
- El RFC de la constancia debe ser el del emisor activo. Si no, se rechaza con el motivo.
- **Nunca pisa en silencio** los datos del emisor (régimen y CP): si difieren, se muestra «La constancia dice X, tú tienes
  Y» y el usuario decide (misma regla que la importación de clientes).
- Si el PDF no tiene texto (escaneado o foto), se pide el PDF original del SAT. No se adivina.

**Dónde se guarda:**
- PDF: `datos/csf/{emisor_id}/AAAAMMDD_{idCIF}.pdf` (junto a sus XML; entra al respaldo diario cifrado).
- Datos leídos: tabla nueva **`constancia_fiscal`** (con `emisor_id` → queda aislada por cuenta sola, por `db.py`).
  Se guarda el historial; la vigente es la más reciente.

```
constancia_fiscal
  id, emisor_id (FK), rfc, nombre, curp, cp, id_cif, emitida_el,
  regimenes JSON [{clave, nombre, desde, hasta}], actividades JSON [{orden, nombre, porcentaje, desde, hasta}],
  obligaciones JSON, archivo, subida_por (usuario_id), creado
```

---

## 4. Cómo se guarda la clasificación de cada factura

Tabla nueva **`xml_deduccion`**, aparte de `xml_cfdi`. Así, volver a leer o volver a bajar un XML **nunca borra** la decisión
de una persona.

```
xml_deduccion                                  único (emisor_id, uuid)
  id, emisor_id (FK), uuid
  sugerencia      deducible | no_deducible | revisar | parcial
  motivos         JSON  [{regla, texto, peso}]   ← por qué lo sugirió, en palabras
  reglas_version  qué versión del motor lo sugirió (para recalcular sin tocar lo confirmado)
  decision        deducible | no_deducible | null   ← lo que dice la persona; null = sin revisar
  porcentaje      opcional, para parciales (p. ej. restaurantes 8.5 %)
  decidido_por, decidido_el, nota
```

- **Resultado que se muestra** = `decision` si existe; si no, `sugerencia` con la etiqueta «sugerido».
- Cuándo se sugiere: al indexar cada CFDI **recibido** (bajado o subido) y, de nuevo, para todos, cuando se sube o cambia la
  constancia. El recálculo **sólo toca `sugerencia` y `motivos`**, jamás `decision`.
- Las decisiones se pueden deshacer («volver a la sugerencia»).

---

## 5. El motor de sugerencias (reglas, no adivinanzas)

Archivo nuevo `services/deducibles.py`. Cada regla da un motivo legible. Orden: lo que **descarta** primero, luego lo que
**limita**, y lo que no se puede saber va a **Revisar**. Siempre se aclara que es orientación y se confirma con el contador.

**No deducible (casi seguro):**
- CFDI **cancelado** en el SAT.
- RFC receptor distinto al de la constancia (factura a nombre de otro).
- Uso **S01** «sin efectos fiscales».
- **Nómina** recibida (es tu recibo de sueldo, no un gasto) y **complementos de pago** (no son gasto; sólo liquidan una PPD).
- Pago en **efectivo (forma 01) por más de $2,000** (art. 27 fr. III LISR); combustible pagado en efectivo, por cualquier monto.
- Proveedor en la **lista 69-B** (definitivos). Timbra ya baja esa lista (`clientes_io.listado_69b`).

**Revisar (falta un dato o un criterio):**
- Régimen o CP del receptor en el CFDI distintos a los de la constancia.
- Contribuyente en **RESICO persona física (625)**: el ISR se paga sobre ingresos y **no tiene deducciones**; el gasto
  sirve para **IVA acreditable**. Se marca aparte y se explica.
- **PPD sin complemento de pago**: para quien tributa en flujo (612, 625 y personas físicas) es deducible hasta que se paga.
- Forma de pago **99** (por definir) sin complemento.
- Gasto que no parece de la actividad de la constancia (por las claves de producto del XML). Es una pista, no un juicio.

**Parcial:**
- Consumos en **restaurantes**: 8.5 % (art. 28 fr. XX LISR).
- **Automóviles** y su arrendamiento: con tope (art. 36 LISR).

**Deducciones personales** (usos **D01–D10**, sólo personas físicas): van a su propio grupo «Personales (anual)», no se
mezclan con los gastos del negocio.

**Deducible:** lo que pasó todas las reglas anteriores con uso G01/G02/G03 o I01–I08 y régimen compatible.

---

## 6. Revisión humana

- En «Por revisar» cada renglón muestra el motivo y dos botones: **Deducible** / **No deducible** (más una nota opcional).
- Selección múltiple → «Confirmar como sugerido» para avanzar rápido.
- Atajos: `D` deducible, `N` no deducible, `Enter` siguiente (regla 11: todo sin mouse).
- Queda registrado quién confirmó y cuándo. El contador puede revisar lo que confirmó su cliente.

---

## 7. «Mis facturas» sin cuenta

**La idea:** una página pública, por ejemplo `/mis-facturas` (fuera del menú, como `/autofactura`), donde alguien sin
cuenta pone su e.firma, elige el periodo, opcionalmente sube su constancia y baja **XML + PDF** en un ZIP, con la vista de
deducibles.

**Cómo, sin reescribir nada:** reusar todo el flujo que ya existe con una **cuenta temporal invisible**:
- Al empezar se crea un `Usuario` marcado `temporal` con su emisor (el RFC sale de la e.firma) y un token que vive sólo en
  ese navegador. El aislamiento por cuenta de `db.py` lo protege igual que a una cuenta normal.
- Ese token **sólo abre** las rutas de XML del SAT, constancia y deducibles. No puede timbrar, ni ver PAC, timbres ni
  ajustes.
- **Se borra sola** a las 24 horas: el programador elimina la cuenta temporal, sus XML, PDF y constancia.
- Al final: «¿Quieres guardar esto? Crea tu cuenta» → la cuenta temporal se vuelve normal con correo y contraseña, sin
  perder lo bajado.

**Candados obligatorios (si no, no sale):**
- Aceptar el aviso de privacidad antes de subir la e.firma (casilla, queda constancia como en las cuentas).
- Límite por IP: pocas sesiones por hora y una descarga a la vez por sesión; respeta los topes de 3 por cuenta y 8 en todo
  el servidor que ya existen.
- La e.firma sigue sin guardarse nunca (2 horas en memoria, como ahora).
- Tamaño máximo del periodo (por ejemplo, 12 meses) y del ZIP.
- Aviso de privacidad: agregar la sección de la cuenta temporal y su borrado a las 24 h.

---

## 8. Fases (cada una se sube sola y con sus pruebas)

| Fase | Qué | Riesgo para lo que ya existe |
|---|---|---|
| 0 | e.firma 2 horas | **Hecha** |
| 1 | Constancia: tabla, lectura del PDF, tarjeta en Datos, comparación con el emisor | Nulo: tabla y ruta nuevas |
| 2 | Motor de sugerencias + tabla `xml_deduccion` + recálculo; pastilla en Comprobantes | Bajo: sólo se llama al indexar; si falla, se registra y el XML se guarda igual |
| 3 | Sección Gastos en Datos: tres grupos, confirmar, atajos, columnas al final del Excel | Bajo: el formato de 65 columnas no se toca |
| 4 | «Mis facturas» sin cuenta | Medio: es una puerta pública nueva. Va al final y con revisión de seguridad |

**Reglas para no romper nada:**
- Migraciones nuevas (0013, 0014…), nunca `create_all`.
- El índice de XML (`xml_indice.indexar`) sólo **llama** al motor dentro de un `try`: un error del motor nunca impide guardar
  un XML.
- Pruebas nuevas por fase (`tests/test_x1_constancia.py`, `test_x2_deducibles.py`, `test_x3_sin_cuenta.py`), con casos de
  cada regla y uno que compruebe que recalcular no pisa decisiones.
- La suite completa en verde antes de cada push.

---

## 9. Lo que necesito de ti, Rick

1. **Una constancia real en PDF** (la tuya o la de un cliente con su permiso). Sin una real no construyo el lector: el
   formato del SAT tiene detalles que no voy a adivinar.
2. **Revisar las reglas de la sección 5** como contador: ¿falta alguna que uses?, ¿alguna que no aplique a tus clientes?
3. **Sin cuenta:** ¿24 horas te parece bien para el borrado? ¿Se ofrece a cualquiera o sólo con una liga que tú compartes?
