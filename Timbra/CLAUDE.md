# Timbra — memoria del proyecto para Claude Code

Facturación CFDI 4.0 multi-emisor para el despacho de Rick (C.P., EDDP Servicios). Un contador factura
a nombre de varios RFC (sus clientes). Prioridades, en orden: **1) no quemar timbres ni perder UUIDs,
2) cumplir reglas SAT, 3) facturar en el menor número de clics.** Habla con Rick en español mexicano,
directo y breve.

## Stack
- `backend/` Python 3.12 · FastAPI · SQLAlchemy 2 · Alembic · **satcfdi** (arma, sella, calcula,
  catálogos SAT y clientes de PACs). SQLite en `backend/datos/` (Postgres opcional vía `DATABASE_URL`).
- `frontend/` Next.js 15 (App Router, export estático) · Tailwind 4 · SWR · sonner · lucide.
  Se compila a `frontend/out` y se copia a `backend/static`; FastAPI lo sirve. Rick solo necesita Python.

## Comandos
- Instalador para cualquier PC: `CONSTRUIR_INSTALADOR.bat` → pytest + PyInstaller (`backend/timbra.spec`, entrada
  `backend/timbra_app.py`) + Inno Setup (`instalador/timbra.iss`). Datos y .env del instalado viven en
  `%LOCALAPPDATA%\Timbra` (no en la carpeta del programa). Ícono junto al reloj: abrir, respaldar, importar versión anterior.
- Arrancar sin instalar (desarrollo): `INICIAR.bat` → http://localhost:8000
- Pruebas: `cd backend && .venv\Scripts\python -m pytest -q tests` (o `PRUEBAS.bat`)
- Dev con recarga: `DESARROLLO.bat` (API :8000 + web :3000)
- Tras cambiar el front: `COMPILAR_FRONT.bat` (o `cd frontend && npm run build` y copiar `out/` → `backend/static/`)
- Migración nueva tras tocar `app/models.py`:
  `cd backend && .venv\Scripts\python -m alembic revision --autogenerate -m "que cambió"` → revisar el archivo → se aplica solo al arrancar.
- Tipos del front: `cd frontend && npx tsc --noEmit`

## Mapa
```
backend/app/
  models.py            Pac, Emisor(+CSD cifrado), Serie, Cliente, Producto, Addenda, Factura, Plantilla, Usuario
  schemas.py           Pydantic de entrada/salida (FacturaIn es el payload central)
  services/cfdi.py     construir()/construir_pago(): FacturaIn -> satcfdi Comprobante
  services/facturacion.py  emitir / emitir_pago / cancelar / enviar / recuperar  ← flujo crítico
  services/pac.py      get_pac(): demo|finkok|swsapien|facturama|prodigia|diverza|comerciodigital|mysuite
  services/signer.py   carga/valida CSD (rechaza FIEL, RFC distinto, vencido)
  services/addenda.py  plantillas Jinja2 inyectadas DESPUÉS del timbre (no van en la cadena original)
  services/respaldo.py cada XML timbrado se escribe a disco antes de tocar la BD
  services/semillas.py catálogo base de productos al crear emisor
  services/validacion.py  REGLAS CFDI 4.0 antes de timbrar (uso↔régimen, PUE≠99, CP, claves, tasas, 72 h…)
  services/importar.py    importador de clientes (Excel/CSV/pegado; régimen por texto o clave; correo|tel)
  logs.py                 bitácora: memoria (consola en vivo) + datos/logs/timbra.log; paso() mide y traza
  routers/debug.py        /api/debug/logs · /servicios (BD, PAC, SMTP, CSD) · /cliente (errores del navegador)
  services/timbres.py     control de timbres: paquete local (Pac.timbres_*) + saldo en vivo de SW; bloquea antes de timbrar si llegó a 0
  services/recurrentes.py plantillas recurrentes (día del mes, {MES}/{año} en descripciones); avanza en la MISMA transacción que la factura
  services/nomina.py      nómina 1.2: recetas (sueldo, asimilados, aguinaldo…), validaciones SAT, arma el CFDI (ISR lo captura el contador)
  services/descarga_sat.py descarga masiva SAT con e.firma (Emisor.fiel_*; nunca sella); XML y Metadata → tabla cfdi_sat
  services/cobranza.py    antigüedad de saldos PPD por Cliente.dias_credito, estado de cuenta, recordatorios (lunes si Emisor.cobranza_auto)
  services/programador.py cada 10 min: recurrentes automáticas, solicitudes SAT, cobranza; respaldo ZIP diario (14) en ../Respaldos
  services/pdf.py         PDF de satcfdi + encabezado/colores del emisor (logo_b64, color)
  services/lotes.py       FACTURAS EN LOTE desde tabla: perfil de importación (columnas, fórmulas de conceptos, forma_map, políticas),
                          resolver() por fila, cuadrar() = solver del centavo, ejecución en hilo, registro CSV y ZIP PDF+XML
  routers/lotes.py        /api/lotes (+ /perfiles). Modelos: PerfilLote, Lote, LoteFila; Factura.referencia = folio de la hoja
  services/claves.py      CLAVES SAT: búsqueda con índice invertido (ms), sin acentos/plural/género, SINONIMOS del día a día, jerarquía
                          por prefijo, NOTAS fiscales breves y alertas (familia 51 = medicamentos, bloqueadas por emisor)
  services/productos_io.py catálogos sugeridos por giro (semillas.PACKS) e importación de productos (vista previa + clave sugerida)
  routers/claves.py       /api/claves (buscar, detalle, frecuentes, unidades); /api/catalogos/buscar/* usa el mismo motor
  services/clientes_io.py clientes en masa: confirmar importación con CONFLICTOS (hoja vs guardado, decide el usuario), auditoría de guardados
                          con arreglos seguros, duplicados + fusión (sólo mismo RFC), lista 69-B del SAT
  services/pendientes.py  bandeja global (lotes por corregir, clientes, facturas con detalle, cancelaciones, recurrentes, cobranza vencida,
                          CSD/e.firma/timbres) → /api/pendientes (+ /resumen para el globo del menú)
  app/__init__.py         catálogo SAT de satcfdi seguro para hilos (una conexión de sólo lectura POR HILO; ver "Estabilidad")
  services/errores_pac.py catálogo de errores comunes PAC/SAT → título + "Qué hacer" + acción automática segura:
                          reintentar (mismo XML sellado), recuperar ("previamente timbrado" → Finkok.stamped), refechar (re-arma y re-sella)
  services/config_facturar.py barra de Facturar por emisor: nivel simple/estandar/completo, campos, defaults, perfiles rápidos
  routers/terceros.py     catálogo "a cuenta de terceros" (nodo ACuentaTerceros); validación en validacion._terceros_predial_aduana
  routers/portal.py       autofactura PÚBLICA /api/portal/{clave} (sin login; ticket 1 uso, mes en curso, límite por IP, descarga HMAC) + /api/tickets
  routers/             auth, pacs, emisores, clientes, productos, plantillas, addendas, facturas, catalogos, dashboard,
                       nomina, sat, cobranza, portal
backend/tests/test_flujo.py  flujo completo con PAC demo y CSD de prueba SAT (EKU9003173C9 / 12345678a)
frontend/src/app/(app)/facturar/page.tsx  pantalla estrella: cuadrícula de conceptos tipo Excel (data-cell="fila-col"),
                                          ticket lateral ≥940px de contenedor, barra inferior en móvil
frontend/src/components/atajos.tsx       atajos globales (F1/?, F2, Ctrl+K paleta, F9 consola) — agrega aquí los nuevos
frontend/src/components/consola.tsx      consola de depuración (registro, servicios, red del navegador)
frontend/src/lib/tema.ts                 tema sistema/claro/oscuro (Ctrl+Shift+L); tokens en globals.css (bg-primario/text-sobre-primario)
frontend/src/app/autofactura/page.tsx    página pública del portal (fuera del layout con login)
frontend/src/lib/sat.ts                  espejo en el navegador de reglas SAT (uso↔régimen) y evaluarMonto (=1160/1.16)
```

## Reglas de oro (no negociables)
1. **Nunca** cambies `services/cfdi.py`, `facturacion.py`, `pac.py` o `signer.py` sin correr `pytest` y que pase.
2. Todo lo que pueda fallar se valida **antes** de `pac_svc.timbrar()` (addenda, receptor, CSD). Después del timbre ya se gastó el timbre.
3. Después de timbrar: `respaldo.guardar()` primero, BD después. No quites eso.
4. Errores de timbrado → `db.rollback()` para regresar el folio. No consumir folios en fallos.
5. `SECRET_KEY` de `.env` cifra los CSD. Si cambia, los CSD guardados quedan inservibles. Nunca la regeneres en un `.env` existente.
6. Nada de montos en float: `Decimal` en backend, strings en el payload.
7. Textos de UI en español, voz activa, sin disculpas; el botón y el toast usan el mismo verbo ("Timbrar" → "Timbrada").
8. Modelos cambian → migración Alembic, nunca `create_all`.
9. Toda regla SAT nueva va en `services/validacion.py` (y su espejo en `lib/sat.ts` si ayuda a guiar en pantalla) con prueba.
10. Responsivo con **container queries** (`@container` + `@min-[Npx]:`), no con breakpoints de ventana; probar 360, 768, 1024, 1440.
11. Todo flujo nuevo debe poder hacerse sin mouse (Enter avanza, Esc cierra, atajo documentado en `components/atajos.tsx`).
12. Errores al usuario con `mostrarError(e)`: muestra el mensaje y liga a la consola con el folio (X-Request-ID).
13. Cada paso importante en servicios con `log`/`paso()` para que se vea en la consola.

## Versión del CFDI
La versión vigente es **CFDI 4.0** (Anexo 20; en 2026 el SAT sólo actualizó catálogos, no la estructura).
No existe "4.4". Los catálogos vienen en satcfdi: `ACTUALIZAR_CATALOGOS.bat` cuando el SAT publique cambios.

## Lotes (no los rompas)
- Total del CFDI == monto cobrado SIEMPRE. `cuadrar()` mueve hasta `ajuste_centavos` por concepto (el menor movimiento, el servicio
  grande primero) y lo deja visible en `resumen.ajuste`; si no cuadra, la fila no se timbra. Caso de oro: tests/test_lotes.py (900 y 2000).
- Folio de la hoja = folio real (`folio_modo: hoja`). Una fila con folio válido lo APARTA mientras su estado sea listo/error/timbrando
  (`folios.APARTAN`): `folios.siguiente` lo salta y `folios.tomar` exige exactitud. Omitir la fila libera el folio.
- Una fila con error NO frena el lote: queda "Por corregir" y se rescata con PUT fila + ejecutar (mismo folio).
- Idempotencia por fila: `referencia` ya timbrada → fila "omitida" (puedes volver a pegar la hoja completa). `recuperar_interrumpidas`
  al arrancar: filas "timbrando" huérfanas pasan a error para revisión manual (nunca se reintentan solas).
- Fórmulas: sólo + − × ÷ y nombres de columna (`lotes.evaluar`, AST con lista blanca; nada de eval).
- Políticas por perfil: `iva_permitido` y `claves_bloqueadas` (medicamentos) bloquean la fila antes de timbrar.

## Claves SAT (no las rompas)
- Todo lo que busca claves usa `services/claves.py` (ClaveSearch, Claves SAT, importador, perfiles de lote). Un sinónimo nuevo va en
  `SINONIMOS` como FRASE tal como la escribe el catálogo; la palabra sola de un solo término no recibe el bono de frase.
- `Emisor.config_facturar.claves_bloqueadas` (8 dígitos) se aplica en `validacion.validar` a CUALQUIER factura (manual o lote).
  La familia 51 sólo avisa. Un lote muestra esos avisos UNA vez arriba (`alertas_lote`), no fila por fila.
- Cada clave de `semillas.PACKS` se verifica contra el catálogo en tests/test_v4_claves.py; los nombres de un pack no deben coincidir
  con otro pack de distinto IVA (el "ya lo tienes" compara descripción + clave).
- La orientación fiscal de `NOTAS` es ayuda, no asesoría: siempre dice que se confirme con el contador.

## Clientes en masa y pendientes (no los rompas)
- Datos fiscales (nombre, CP, régimen) NUNCA se pisan en silencio: importación → fila "conflicto" → el usuario elige hoja/guardado;
  sin decisión no se toca (`sin_decidir`). Filas idénticas = "igual" (no se reimportan).
- Fusionar clientes sólo con el MISMO RFC; las facturas/plantillas se mudan al conservado. Mismo nombre + otro RFC sólo se avisa.
- `auditar()` oculta a quien sólo carece de correo salvo `incluir_info`; la bandeja cuenta sólo errores y avisos.
- Lista 69-B: `clientes_io.listado_69b()` (satcfdi la baja y la guarda en disco). Siempre con degradación: sin internet → 503/aviso, nunca 500.

## Barra de Facturar, impuestos y menú (2.5, no los rompas)
- IEPS: `cfdi._impuestos` fija base e importe a mano cuando hay IEPS trasladado: cuota → base = cantidad; el IVA va sobre
  valor + IEPS. satcfdi solo NO lo hace bien (trata la cuota como importe). `lib/impuestos.ts` replica el cálculo. Prueba: tests/test_v7.
- Retención de IVA: error sólo si retiene más de lo que traslada; 2/3, 6% (servicios especializados) y total pasan; otra tasa = aviso.
- Combinaciones en `lib/format.ts` (`GRUPOS_IMPUESTOS`). NO renombres llaves: perfiles y configuración las guardan por nombre.
  Sólo IEPS de tasa estable; tabaco/refrescos/combustibles cambian cada año → `EditorImpuestos` («Otro impuesto o tasa…»).
- `GET /clientes/recientes` y `GET /productos/sugerencias` (catálogo + ya facturados + catálogo SAT) alimentan los botones
  Clientes (Alt+G), Mis conceptos (Alt+I) y la lista de la descripción (`components/facturar-listas.tsx`).
- Modo demo: `Emisor.modo_demo` (sin PAC o PAC demo) y `FacturaOut.demo` (`pdf.es_demo`: SelloSAT="DEMO"). Aviso en Facturar,
  etiqueta en Facturas y banda roja en el PDF. No lo quites: una factura demo NO vale ante el SAT.
- Addendas básicas: `addenda.SEMILLAS`; al arrancar se agregan las que falten por nombre (no pisa las editadas).
- Menú (`shell.tsx`, `NAV`): Resumen primero, luego lo diario y 4 grupos (Emitir, Cobrar y revisar, Catálogos, Configuración).
  En riel cada grupo es UN icono con menú flotante al pasar el mouse (así cabe en pantallas de 720 px); lo diario lleva etiqueta.
  Se pliega a riel con el botón o Ctrl+B (`timbra_barra`), grupos plegables (`timbra_grupos`), perfil abajo
  (`GET/PUT /auth/yo`). Descarga SAT queda como está: se conectará a la app externa DESCARGA XML SAT del usuario (falta el link).

## PDF (no lo rompas)
- `services/pdf.py`: facturas, notas de crédito y traslados usan plantilla PROPIA (`_propia`); nómina y pagos, la de satcfdi con marca.
- Requisitos fiscales de la representación impresa (regla 2.7.1.7 RMF, art. 29-A CFF) listados en `pdf.REQUISITOS` y vigilados por
  tests/test_v8_pdf.py: QR, UUID, certificados emisor y SAT, RFC del PAC, sellos, cadena original del timbre, fechas, leyenda, etc.
  Si cambias la plantilla, esa prueba debe seguir pasando. Importe con letra: `pdf.con_letra`.
- PDF real: weasyprint si hay GTK; si no, Edge/Chrome sin ventana (`_pdf_navegador`, ~4 s por PDF; Edge regresa ANTES de escribir el
  archivo, por eso se espera; la carpeta temporal va con ruta larga, no `ERICKD~1`). Varios a la vez: `pdf_varios` (ZIP de lotes).

## Antes de producción (no lo rompas)
- Fecha del CFDI: `cfdi.ahora_mx(cp)` usa el huso del CP de expedición (catálogo c_CodigoPostal → `HUSOS`), no siempre CDMX;
  si el reloj de la PC va hasta 2 h atrás del huso oficial se usa el de la PC (nunca queda en el futuro: el PAC la rechazaría).
- Facturas de práctica: `POST /emisores/{id}/practica/borrar` quita SÓLO las del PAC demo (`pdf.es_demo`), mueve sus XML a
  `datos/practica_xml` y regresa cada serie al folio siguiente a la última factura real. tests/test_v9_produccion.py.
- `ClaveSearch` (catalogo.tsx): el blur corre 150 ms tarde; usa refs y la bandera `elegido` para no pisar la clave recién elegida.
  En la descripción del concepto, Enter sólo elige una sugerencia si la marcaste con flechas (`act` empieza en -1).

## Web y correo (2.6, no los rompas)
- Despliegue: `DESPLEGAR.md`. `backend/Dockerfile` (Chromium para PDF, datos en el volumen `/data`), `backend/railway.toml`,
  `frontend/vercel.json`. El front llama a `API` de `lib/api.ts` (usa `NEXT_PUBLIC_API_URL` si las pantallas viven aparte).
  NO probado en un despliegue real todavía.
- Candados en `config.py` (`EN_WEB`): en servidor no arranca con SECRET_KEY/JWT_SECRET/ADMIN_PASSWORD de ejemplo. Login con freno
  de 6 intentos por correo en 10 min (`routers/auth.py`). Pendiente antes de dar acceso a terceros: separar emisores por cuenta.
- Correo: `services/mailer.py` + `routers/correo.py`; cuenta en `datos/correo.json` con contraseña cifrada (Gmail = contraseña de
  aplicación de 16 letras). Google OAuth: `GOOGLE_*` en `.env` vía `google_env.py`; el inicio de sesión aún no está construido.
- Diseño: tokens en `globals.css` (marino + `acento`), tipografía Geist, `select` y barras con estilo global. El único botón
  sólido del menú es Nueva factura; la pantalla actual va con tinte suave. `Menu` (⋯) usa posición fija para no recortarse.

## Cuentas separadas y Google (2.7, no lo rompas)
- Cada cuenta ve SÓLO sus emisores y todo lo que cuelga de ellos. La separación vive en `app/db.py` (eventos de la sesión), no en
  cada ruta: lecturas filtradas por dueño (`Emisor.usuario_id`, `Pac.usuario_id`, y toda tabla con `emisor_id`) y 403 al escribir
  en lo ajeno. Una tabla nueva queda protegida si tiene `emisor_id`; si no lo tiene, NO lo está: agrégalo o filtra a mano.
  El administrador y las sesiones del sistema (`SessionLocal()` directo: lotes, programador, portal público) no tienen filtro.
- Sólo administrador (`Depends(solo_admin)`): usuarios, consola de depuración, configurar correo, editar addendas, recuperar XML.
- Entrada con usuario o correo (`Usuario.usuario`). `crear_admin.py` crea la cuenta de pruebas admin/admin; en servidor (`EN_WEB`)
  las contraseñas de práctica no entran.
- Google (`routers/auth.py`): `/auth/google/entrar` y `/vincular` devuelven la URL; `/callback` canjea el código y regresa a
  `/login/#token=…` (fragmento, nunca query). Sólo entra quien ya tiene cuenta, salvo `REGISTRO_ABIERTO=true`. Permisos pedidos:
  openid, email, profile; Drive y Sheets se pedirán aparte cuando se construyan. tests/test_w1_cuentas.py.

## Estabilidad (no la rompas)
- `satcfdi.catalogs.conn` es UNA conexión SQLite compartida: con peticiones simultáneas fallaba (~16% de consultas, «API misuse», 500).
  `app/__init__.py` la reemplaza por una conexión de sólo lectura por hilo. tests/test_v6_catalogo_hilos.py lo vigila. Nunca uses
  `sqlite3` de satcfdi desde un hilo con una conexión creada en otro.
- Idempotency-Key en POST /facturas y /facturas/pagos: misma llave = misma factura, nunca doble timbre (Facturar la manda).
- Folios con UPDATE atómico (`folios.siguiente`): pantalla y programador nunca toman el mismo folio.
- Tras timbrar: `_respaldar()` no truena si el disco falla; `_guardar()` recupera del respaldo si la BD falla y adelanta el folio;
  si ni así, `TimbradoSinGuardar` bloquea el reintento (409) para no duplicar el timbre.
- SQLite en WAL + busy_timeout (db.py). Respaldo diario con la API de backup de SQLite (copia consistente).
- Errores nuevos de PAC: agrega su patrón en `errores_pac.REGLAS` con prueba en tests/test_v3.py.

## Reglas SAT ya implementadas (no las rompas)
- TasaOCuota SIEMPRE con 6 decimales (`cfdi._tasa`): "0.16" lo rechaza el PAC, "0.160000" no.
- IVA traslado sólo 16%, 8% (frontera) o 0%; exento sin tasa. Retención de IVA = 2/3 del IVA (0.106667 con 16%,
  0.053333 con 8%); fletes 4% aparte. Exento/0% no admiten retención de IVA. ISR sólo se retiene.
- IVA 8% sin `Emisor.region_fronteriza` → aviso. Estímulo prorrogado al 31/12/2026 (DOF 31-dic-2025) → aviso después.
- PPD ⇒ FormaPago 99 automático. REP solo para PPD, con parcialidad y saldo anterior correctos.
- Público en general: XAXX010101000, "PUBLICO EN GENERAL", régimen 616, uso S01, CP = lugar de expedición, InformacionGlobal.
- Extranjero XEXX010101000: DomicilioFiscalReceptor = lugar de expedición.
- Traslado: moneda XXX, sin impuestos ni forma/método de pago, uso S01.
- Cancelación: motivo 01 exige UUID sustituto; no se cancela un ingreso con REP vivos.
- Cancelación: sólo 201/202 son aceptados (`pac.CANCEL_OK`); cualquier otro código truena con su texto. 201 NO es "cancelada":
  se confirma con estatus SAT (`pac.estado_sat`); si no se puede confirmar queda `cancelacion_pendiente`.
- `tzdata` es obligatorio en requirements: Windows no trae America/Mexico_City y sin eso no se arma ningún CFDI.
- Addenda automática del cliente solo en tipo I; en E/P solo si se manda explícita.
- Impuestos locales: máximo uno de traslado y uno de retención (limitación de satcfdi implocal10).
- A cuenta de terceros: RFC válido no genérico, distinto del emisor, régimen acorde a persona, CP del catálogo, nombre sin societario.
- Cuenta predial alfanumérica (varias con coma). Pedimento: 15 dígitos, se normaliza solo a "AA  AA  AAAA  AAAAAAA".

## Backlog (en orden)
- [ ] Probar contra sandbox real de Finkok y SW con credenciales de Rick (botón "Probar timbrado"); ajustar mensajes por PAC.
- [ ] Facturama: satcfdi sólo soporta `issue()` (ellos sellan con CSD subido); hoy está bloqueado a propósito.
- [x] Control de timbres (paquete local + saldo SW) con avisos.
- [ ] Nota de crédito PPD: descontar del saldo de la factura relacionada.
- [ ] Cancelar REP y regresar saldo a la factura origen.
- [x] Nómina 1.2: empleados, recetas, lote por periodo. Pendiente: cálculo automático de ISR/IMSS con tablas, separación/jubilación.
- [ ] Carta Porte 3.1 (satcfdi: `cartaporte31`) — solo si un cliente la necesita.
- [x] Logo/colores del emisor en el PDF.
- [x] Facturas recurrentes y favoritas (Alt+Shift+1…9).
- [x] Descarga masiva SAT + conciliación + CSV para COI. Pendiente: probar con e.firma real (no hay sandbox del SAT).
- [x] Portal de autofactura con tickets. Para internet: túnel (Cloudflare Tunnel) o servidor con HTTPS.
- [x] Cobranza: antigüedad, estado de cuenta, recordatorios.
- [x] Instalador Windows (PyInstaller + Inno Setup) con respaldo diario.
- [x] Resumen con cobranza, timbres y recurrentes. Ícono propio (instalador/timbra.ico).
- [x] Errores comunes con solución y autocorrección segura; idempotencia; recuperación tras fallo de BD/disco.
- [x] A cuenta de terceros + predial + pedimentos; barra de Facturar configurable con perfiles y "repetir la última" (Alt+U).
- [x] Fase 1 de facturación masiva: lotes desde tabla pegada/CSV/XLSX (ver memoria plan-facturacion-masiva-timbra).
- [x] Fase 2: módulo Claves SAT (Alt+K), catálogos sugeridos por giro, importar productos de tabla, claves bloqueadas por emisor.
- [x] Fase 3: clientes masivos (conflictos, auditoría, duplicados/fusión, lista 69-B) y bandeja de pendientes (Alt+J).
- [ ] Fase 4: entrega automática a carpeta destino por emisor/mes (G:\...) y envío por correo desde el lote.
- [ ] Fase 5: Google Sheets en vivo, carpeta vigilada y API con llave.
- [ ] Fase 6: reescribir la skill /facturacion para operar Timbra y migrar GMH de Facturama.
- [ ] Firmar el instalador con certificado de código (evita el aviso de SmartScreen).
- [ ] Cancelar REP y regresar saldo; nota de crédito PPD que descuente saldo.
- [x] Importar clientes desde Excel/CSV/pegado.
- [ ] Importar productos desde Excel (mismo patrón que services/importar.py).
- [ ] Validar addendas retail contra el XSD oficial de cada cadena.

## Limitaciones conocidas
- PDF directo requiere weasyprint + GTK; sin eso el botón PDF abre HTML con diálogo de impresión.
- Recuperación desde respaldo no reconstruye parcialidades de REP.
- Auth simple (JWT 7 días, sin roles finos). Pensado para uso local o LAN, no expuesto a internet sin HTTPS.

## Lo que enseñó el PAC real (Finkok pruebas, 10-oct-2026)
- El PAC demo NO valida decimales. Todo importe que vaya al XML debe llevar los decimales de la moneda: `Descuento` (CFDI40112) y
  `ImpSaldoAnt`/`ImpPagado` del complemento de pago (CRP20240) se redondean en `services/cfdi.py`. La BD guarda dinero con 6
  decimales (`Money`): nunca lo pases directo al CFDI. tests/test_w2_pac_real.py.
- Probado de verdad en pruebas: ingreso PUE y PPD, descuento, factura global, nota de crédito relacionada, complemento de pago
  parcial, cancelación motivo 02 y estatus SAT ("Cancelado"). Sin probar contra PAC: nómina, traslado, IEPS, impuestos locales.
- Antes de dar algo por bueno, pruébalo con el emisor EKU9003173C9 y el PAC de Finkok en pruebas (no gasta timbres reales).
- Segunda ronda en Finkok pruebas (11-oct-2026), todo aceptado: retenciones ISR/IVA, IEPS + IVA, impuesto local ISH, IVA exento
  y 0%, traslado, dólares con tipo de cambio, sustitución (relación 04 + cancelación motivo 01, queda «pendiente» hasta que el SAT
  confirma), cancelación motivos 02 y 03, y recurrentes automáticas (al día, tarde, atrasada, sin duplicar).
  PENDIENTE: nómina la rechaza Finkok con «NOM111 - Error no clasificado» en cinco variantes (con/sin subsidio, ObjetoImp 01/03,
  asimilados). Falta que su asesor diga qué valida ese código; no usar nómina en producción hasta resolverlo.
- Recurrentes: el periodo es el programado (`p.proxima`), nunca se salta un mes; `MAX_ATRASO_AUTO` días de margen para timbrar
  sola; candado contra doble timbrado. tests/test_w3_recurrentes.py.
- Tercera ronda (11-oct-2026, 2.8.0): lote real con el formato de la skill /facturacion (15 columnas) contra Finkok pruebas:
  11 CFDI, total = MONTO al centavo, folio de la hoja, pendientes rescatados, ZIP `C-#_UUID`, re-pegar no duplica.
  Bug que destapó: el lote usaba el uso guardado en el cliente (G03) en vez del del perfil (D01). Ahora `FacturaIn.uso_cfdi`
  manda sobre el del cliente (lote y pantalla de Facturar). Una fila cuya factura se canceló ya no se «omite»: pide folio nuevo
  (modo hoja) o se reemite (consecutivo). tests/test_w4_skill.py.

## Lo de 2.8 (no lo rompas)
- **Carpeta de entrega** (`carpeta` en el perfil de lote, sólo fuera de `EN_WEB`): al terminar el lote deja XML+PDF
  `{folio hoja}_{UUID}` en la ruta (tokens {AAAA} {MM} {Mes} {MES} {RFC}, por fecha de emisión). Nunca pisa archivos, nunca
  afecta lo timbrado, y el estado se lee del disco (`lotes.entrega`). En web está prohibida: sería escribir rutas arbitrarias.
- **Persistencia a la vista**: `services/almacen.py` cuenta arranques en `datos/almacen.json`; `/api/health` dice
  `almacen.{desde,arranques,permanente}`. En web, `permanente` exige volumen montado y la base dentro de DATA_DIR.
- El resumen sólo muestra advertencias del emisor activo. `DELETE /emisores/{id}?confirmar=RFC` borra un emisor con lo suyo
  (XML a `datos/eliminados`); se niega si timbró con PAC de producción.
- `/api/<ruta inexistente>` responde 404 JSON (antes devolvía la pantalla de inicio con 200).
- Las columnas `creado` llevan `default=datetime.now` (hora local; el contenedor fija TZ México). El valor por omisión de SQLite
  es UTC y de noche las pantallas mostraban la fecha de mañana.

## Seguridad para producción (2.9, no la rompas)
- Las plantillas de addenda corren en `SandboxedEnvironment` y sólo el administrador crea, edita y prueba addendas. Antes,
  `/addendas/probar` dejaba a cualquier cuenta ejecutar código en el servidor con una plantilla Jinja.
- Todo XML ajeno se lee sin entidades ni DTD (`addenda._SEGURO`; `importar-xml` rechaza `<!DOCTYPE`/`<!ENTITY`).
- El token lleva la huella de la contraseña (`k`): cambiarla cierra las demás sesiones. `/auth/password` devuelve token nuevo.
- Intentos de acceso: tope por (equipo, cuenta), por equipo y por cuenta. Nunca sólo por cuenta: dejaría fuera al dueño.
- En web: sin `/docs` ni `/openapi.json`, CSP y Permissions-Policy en las pantallas, `no-store` en `/api`, tope de 25 MB por
  envío, y NO se guarda la e.firma (`/sat/fiel` responde 409). gzip y caché inmutable para `/_next/static`.
- **Modo soporte (2.10):** el administrador ve SÓLO lo suyo. Para ayudar a una cuenta entra con `POST /auth/soporte/{id}`
  (2 horas, queda en `accesos_soporte` y el dueño lo ve en su perfil); las peticiones llevan `X-Soporte` y `db._identificar`
  exige un acceso vigente. Lo que soporte crea queda a nombre de la cuenta atendida. tests/test_w1_cuentas.py.
- tests/test_w5_seguridad.py.

## XML del SAT (2.11, no lo rompas)
- Sustituye al módulo SAT anterior (`routers/sat.py`, `services/descarga_sat.py`: borrados). Pantalla `/sat` con dos pestañas:
  Descargar (e.firma → periodo → avance → tabla) y Datos (gráficas). Rutas en `routers/xml.py`, prefijo `/api/xml`.
- **La e.firma NO se guarda. Nunca.** `services/xml_firma.py` la valida y la deja abierta sólo en memoria (20 min sin usar,
  3 h máximo); se pide cada vez. La migración 0009 borró lo que hubiera guardado. Las columnas `Emisor.fiel_*` quedan vacías.
  No agregues «recordar e.firma», ni la escribas a disco, base, registro o respaldo. tests/test_w6_xml.py lo vigila.
- `app/xmlsat/` es el núcleo de la app de escritorio DESCARGA XML EDDP (lector, flujo con el SAT, PDF de una hoja, Excel),
  copiado sin cambiar su comportamiento. Lo de Timbra vive en `services/xml_{firma,indice,trabajos,tareas}.py`.
- **Formato maestro: 65 columnas** (`lector.COLUMNAS_COPIADO`), en ese orden y con ese texto exacto (números con `.0`, fecha
  sin T, fecha de timbrado con T). Es la hoja maestra del despacho: no se mueve, renombra ni «corrige» nada. Un pago da un
  renglón por documento pagado. El Excel lleva las 73 de siempre y, AL FINAL, «Estatus SAT» y «Cancelado el».
- Los XML viven en `datos/xml/{emisor}/{AAAAMM} {RFC4}/{emitidos|recibidos}/UUID.xml`; `xml_cfdi` es su índice. El historial
  de solicitudes al SAT (`datos/xml_estado/`) evita repetir solicitudes: el SAT limita cuántas veces se pide el mismo periodo.
- Cancelados: tramos `meta_*` piden la lista (Metadata) del SAT; se vuelve a pedir pasadas 24 h. Un fallo ahí es aviso, no
  error. Lo que Timbra canceló se marca solo (`al_dia_con_timbra`). Por omisión la tabla y «Copiar» traen sólo vigentes.
- Sin probar contra el SAT real desde Timbra (sólo SAT simulado): la descarga usa el mismo flujo que sí se probó en escritorio;
  la lista de cancelados es nueva y no se ha probado en real. La nómina no se lee a detalle.
- Capturas: si usas Chrome por CDP, NO uses el puerto 9333 (otra sesión de Claude lo usa en esta PC); usa 9477.
