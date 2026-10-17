# Pendientes de Timbra: camino a producción

Lista compartida. Cada tarea dice quién la hace: **[Claude]** o **[Rick]**.
Para tacharla, cambia `[ ]` por `[x]`. Claude la tacha cuando la termina y la comprueba.

Meta: Timbra en producción el **16 de octubre de 2026**, facturando con Finkok productivo.

Cada fase tiene cinco pasos: **aprender** (revisar qué hay), **mejorar** (corregir lo que falla), **hacer** (lo operativo), **construir** (lo nuevo) y **guiar** (los pasos para Rick).

---

## Lo que te toca a ti, Rick (lista viva)

Claude agrega aquí cada cosa que sólo tú puedes hacer, en orden de urgencia, y la tacha cuando le confirmas.
Las mismas tareas siguen en su fase abajo, con su contexto.

**Ya, para arrancar (fase 1)**
- [ ] Llenar la solicitud de Finkok, poner tu RFC en el borrador, adjuntar solicitud y Constancia, y enviarlo
- [ ] Crear cuenta en resend.com, verificar el dominio erickddp.com (DNS) y poner `RESEND_API_KEY` en Railway
- [ ] Cambiar la contraseña del administrador en el servidor por una nueva y segura
- [ ] Subir el CSD vigente de cada emisor real
- [ ] Corregir el emisor con región fronteriza y un correo en «Registro patronal»
- [ ] Con las credenciales de Finkok: Ajustes → PAC → nuevo Finkok productivo, «Usar este PAC para todas las cuentas», Probar
- [ ] Timbrar tu primera factura real y revisarla en el SAT
- [ ] Primera factura real de un cliente, junto con él
- [ ] Sólo en tu PC: contraseña de aplicación de Gmail en Ajustes → Correo

**Esta semana (fase 2)**
- [ ] Decidir si pasamos a Postgres de Railway (ver «Base de datos» en fase 2); si es sí: agregar el servicio Postgres en Railway
- [ ] Poner `RESPALDO_CORREO` en Railway (cuando Resend esté listo)
- [ ] Hacer una restauración de prueba siguiendo la guía
- [ ] Poner las variables de Google en Railway y probar «Entrar con Google» en factura.erickddp.com

**Constancia fiscal y deducibles (PLAN_DEDUCIBLES.md)**
- [ ] Mandarme una constancia de situación fiscal real en PDF (sin ella no construyo el lector)
- [ ] Revisar las reglas de deducibilidad (sección 5 del plan) como contador
- [ ] Decidir «Mis facturas» sin cuenta: ¿borrado a las 24 h? ¿abierto a cualquiera o sólo con liga tuya?

**Antes de vender (fase 3)**
- [ ] Llenar nombre legal, RFC y domicilio en `frontend/src/lib/legal.ts` (hoy salen en amarillo en los avisos)
- [ ] Crear el buzón privacidad@erickddp.com (o cambiarlo en `lib/legal.ts`)
- [ ] Revisar términos y aviso de privacidad con abogado; confirmar borrado en 90 días y política de reembolso
- [ ] Decidir precios de los paquetes de timbres
- [ ] Abrir la cuenta de Mercado Pago y poner las llaves en Railway
- [ ] Dar de alta a tu primer cliente de paga

---

## Fase 1: arrancar en producción (13 al 16 de octubre)

Objetivo: tú facturas tus emisores con timbres reales, y los clientes con recarga manual.

### Aprender
- [x] [Claude] Correr todas las pruebas automáticas con la versión 2.13.0 (89 pasan)
- [x] [Claude] Recorrer una cuenta nueva de principio a fin en una copia de tus datos: alta de cuenta, emisor, CSD, factura con el PAC de Timbra, PDF, cancelación, saldo de timbres (40 revisiones contra Finkok pruebas, todas bien)
- [x] [Claude] Revisar qué pasa el día del cambio a producción: PAC productivo, facturas de prueba que ya existen, folios y avisos

### Mejorar
- [x] [Claude] Corregir lo que salga del recorrido y de la revisión: los emisores de los clientes se quedaban en modo demo al cambiar de PAC; «Probar» no servía en producción; el error 708 al cancelar salía sin explicación

### Hacer
- [x] [Rick] Decir «push» para subir la 2.13.0 al servidor (subida el 13 de octubre)
- [x] [Claude] Dejar listo el correo de respuesta a Finkok (borrador en tu Gmail, en el hilo «Kit de Pruebas»)
- [ ] [Rick] Llenar la solicitud de Finkok, poner tu RFC en el borrador, adjuntar solicitud y Constancia, y enviarlo
- [x] [Claude] Correo desde el servidor: Railway bloquea SMTP en el plan Hobby; Timbra ahora puede enviar por la API de Resend
- [ ] [Rick] Crear cuenta en resend.com, verificar el dominio erickddp.com (registros DNS) y poner `RESEND_API_KEY` en Railway
- [ ] [Rick] Revisar que la contraseña del administrador en el servidor sea una nueva y segura
- [ ] [Rick] Subir el CSD vigente de cada emisor real
- [ ] [Rick] Corregir el emisor que quedó con región fronteriza y con un correo en «Registro patronal» (quitar lo que no aplique)
- [ ] [Rick] Sólo en tu PC: contraseña de aplicación de Gmail en Ajustes → Correo (en el servidor se usa Resend)

### Construir
- [x] [Claude] Aviso en el Resumen cuando ya hay PAC productivo pero un emisor tuyo sigue con el de pruebas, y botón «Comprobar y dar de alta el RFC» para probar Finkok productivo sin gastar timbres

### Guiar
- [x] [Claude] Escribir la guía del día del arranque (`DESPLEGAR.md` → «Día del arranque»): dar de alta el PAC productivo, probarlo y timbrar la primera factura real
- [ ] [Rick] Con las credenciales de Finkok: Ajustes → PAC → nuevo Finkok, quitar «Ambiente de pruebas», marcar «Usar este PAC para todas las cuentas», Probar
- [ ] [Rick] Timbrar tu primera factura real y revisarla en el SAT
- [ ] [Rick] Hacer la primera factura real de un cliente junto con él

---

## Fase 2: estabilidad y datos (semana del 19 de octubre)

Objetivo: que nada se pierda y que aguante a varios clientes a la vez.

### Aprender
- [x] [Claude] Prueba de carga: 10 cuentas timbrando y descargando XML al mismo tiempo sobre SQLite. Salieron «base de datos ocupada» después de timbrar (timbre cobrado y no guardado), pantallas congeladas al subir XML o lotes, y riesgo de quedarse sin memoria con muchos PDF. Corregido: 0 errores en la segunda corrida
- [ ] [Claude] Revisar los registros del servidor de la primera semana real

### Mejorar
- [x] [Claude] Límites por cuenta: máximo 3 descargas del SAT a la vez por cuenta y 8 en todo el servidor (los timbres ya los limita el saldo)
- [ ] [Claude] Investigar por qué Finkok rechaza la nómina (NOM111) y corregirlo. Pregunta ya incluida en tu borrador a Ricardo; sigo cuando conteste

### Base de datos: SQLite → Postgres de Railway
- [x] [Claude] Evaluación (14-oct): la suite completa corre contra Postgres 16: 94 de 96 pasan. Se corrigieron 3 cosas que SQLite
  escondía (comodín «\0» al crear usuario daba 500; limpiezas de prueba que violaban llaves foráneas: SQLite no las revisa)
- [ ] [Claude] Respaldo con Postgres: hoy el respaldo diario NO incluye la base si es Postgres (sólo XML). Exportación propia de
  todas las tablas dentro del mismo zip cifrado, sin depender de `pg_dump` (las 2 pruebas que faltan)
- [ ] [Claude] Mudanza: script que copia la base SQLite del volumen a Postgres, cuenta registros de cada tabla y no borra el origen
- [ ] [Claude] `psycopg` en requirements (driver de Postgres; hoy no viene)
- [ ] [Rick] Agregar Postgres en Railway y pasar su `DATABASE_URL` al servicio (yo te guío; no lo hagas antes de la mudanza)

### Hacer
- [ ] [Rick] Poner las variables de Google en Railway (con el prompt que ya tienes)
- [ ] [Rick] Probar «Entrar con Google» en factura.erickddp.com

### Construir
- [x] [Claude] Respaldo automático fuera del servidor: diario, por correo, cifrado con tu SECRET_KEY
- [ ] [Rick] Poner en Railway la variable `RESPALDO_CORREO` con tu correo (funciona cuando Resend ya esté listo)
- [ ] [Claude] Segundo paso de seguridad para la cuenta de administrador (Google obligatorio o código)
- [ ] [Claude] Subir a Drive desde la web (hoy sólo funciona en tu PC)

### Guiar
- [x] [Claude] Guía para restaurar un respaldo si algo sale mal (DESPLEGAR.md → «Restaurar un respaldo»)
- [ ] [Rick] Hacer una restauración de prueba siguiendo la guía

---

## Fase 3: vender a terceros (finales de octubre)

Objetivo: que un cliente se dé de alta, pague y facture sin que intervengas.

### Aprender
- [x] [Claude] Revisar cuánto te cuesta cada timbre y proponer precios (tabla abajo)
- [ ] [Rick] Decidir precios de los paquetes de timbres (hoy: 30 por $50, 100 por $130, 300 por $330, 1,000 por $900, IVA incluido)

Lo que te queda por paquete, ya sin la comisión aproximada de Mercado Pago (3.49% + $4 + IVA):

| Paquete | Precio | Te queda | Por timbre |
|---|---|---|---|
| 30 | $50 | ≈ $43 | ≈ $1.44 |
| 100 | $130 | ≈ $120 | ≈ $1.20 |
| 300 | $330 | ≈ $312 | ≈ $1.04 |
| 1,000 | $900 | ≈ $859 | ≈ $0.86 |

Finkok te cuesta $174 al mes (IVA incluido) hasta 500 timbres en total, contando los tuyos, y $0.35 cada uno después.
Con unos 120 timbres vendidos al mes en paquetes chicos ya se paga la cuota mínima. Del precio, el 16% es IVA que declaras.

### Mejorar
- [ ] [Claude] Panel de inicio y bienvenida para cuentas nuevas: te propongo el plan antes de tocar código (así lo pediste)

### Hacer
- [ ] [Rick] Abrir la aplicación de Mercado Pago y poner las llaves en Railway (CONECTAR.md, punto 3)
- [x] Aviso de privacidad y términos de uso dentro de la app (/legal/terminos, /legal/privacidad; cada cuenta los acepta).
  Los borradores de `legal/*.md` quedan como referencia: lo que se publica y se acepta es lo de las pantallas.
- [ ] [Rick] Llenar nombre legal, RFC y domicilio del responsable en `frontend/src/lib/legal.ts` (hoy salen resaltados en amarillo)
- [ ] [Rick] Crear el buzón privacidad@erickddp.com (o cambiarlo en `lib/legal.ts`)
- [ ] [Rick] Revisar los textos con abogado antes de abrir el registro; confirmar plazo de borrado (90 días) y la política de reembolso

### Construir
- [x] [Claude] Compra de timbres con Mercado Pago: el cliente elige paquete, paga y los timbres se abonan solos, una sola vez, después de confirmar el pago con Mercado Pago (no se activa hasta que pongas la llave)
- [x] [Claude] Caducidad de timbres a 12 meses: se gastan primero los que vencen antes; los 3 de regalo no vencen
- [x] [Claude] Pantalla «Mis timbres» para clientes: saldo, cuándo vencen, paquetes, movimientos y compras
- [x] [Claude] Borradores de aviso de privacidad y términos de uso (`legal/`)
- [ ] [Claude] Publicar aviso y términos como páginas, con casilla de aceptación al crear cuenta (cuando los revises)
- [ ] [Claude] Manifiesto de Finkok por emisor (opcional según Finkok)
- [x] [Claude] Registro abierto: crear cuenta con correo y contraseña o con Google, confirmar correo (3 timbres de regalo), «olvidé mi contraseña» (2.15)

### Guiar
- [x] [Claude] Guía para conectar todo: `CONECTAR.md`
- [ ] [Claude] Guía para tus clientes: cómo entrar, dar de alta su CSD y facturar
- [ ] [Rick] Dar de alta a tu primer cliente de paga

---

# Fases para conectar (Rick conecta, Claude prueba)

Guía paso a paso de todo en `CONECTAR.md`. Cuando termines un punto, avísame y yo lo pruebo de punta a punta.

## Fase 4: lo básico para operar (esta semana)
- [x] [Claude] Exportar/importar emisores entre Timbras (Ajustes → «Pasar mis emisores a otra Timbra»), con simulacro, y panel con el resultado de «leer carpeta» (CONECTAR.md, punto 0)
- [ ] [Rick] Subir en la web el CSD REAL de cada emisor (Emisores → emisor → CSD): en tu PC no hay ninguno real
- [ ] [Rick] Mandar a Finkok el borrador con RFC, solicitud y Constancia (CONECTAR.md, punto 1)
- [x] [Rick] Resend: cuenta, dominio verificado y `RESEND_API_KEY` + `RESPALDO_CORREO` en Railway (punto 2)
- [ ] [Rick] Gmail: abrir **Spam** en cperickd@gmail.com, buscar `from:facturas@erickddp.com`, «No es spam» y crear un filtro «nunca enviar a spam»
- [ ] [Rick] En Resend, crear una llave aparte para tu PC (y dejar la actual sólo para Railway), con permiso de envío limitado a erickddp.com
- [ ] [Claude] Probar el correo: prueba, factura con el nombre del emisor y respaldo del día siguiente
- [ ] [Rick] Credenciales de Finkok producción → Ajustes → PAC (DESPLEGAR.md, «Día del arranque»)
- [ ] [Claude] Comprobar el PAC productivo sin gastar timbres y acompañarte en la primera factura real
- [ ] [Claude] Nómina: cuando Ricardo conteste qué valida «NOM111», corregirla y probarla en Finkok pruebas

## Fase 5: cobrar (siguiente semana)
- [ ] [Rick] Mercado Pago en modo prueba: aplicación, `MP_ACCESS_TOKEN` (TEST-) y webhook con `MP_WEBHOOK_SECRET` (punto 3)
- [ ] [Claude] Compra de prueba completa con cuenta de prueba de Mercado Pago: pago, aviso, timbres abonados, sin duplicar
- [ ] [Rick] Pasar Mercado Pago a producción y comprar tú el paquete de $50
- [ ] [Claude] Facturar tus ventas de timbres desde Timbra (CFDI a tus clientes por cada compra)

## Fase 6: abrir a clientes (finales de octubre)
- [ ] [Rick] Variables de Google en Railway y URI de redirección (punto 4)
- [ ] [Claude] Probar «Entrar con Google» y la carpeta de Drive desde la web
- [ ] [Rick] Aviso de privacidad y términos revisados
- [x] [Claude] Publicarlos, casilla de aceptación y bienvenida para cuentas nuevas
- [ ] [Rick] Probar crear una cuenta tuya con otro correo (revisa Spam) y entrar sin Google; luego `REGISTRO_ABIERTO=true` y tu primer cliente de paga
- [ ] [Claude] Revisar los registros del servidor de las primeras semanas y lo que vaya saliendo

---

## Lo que ya está hecho (13 de octubre)

- 2.14.0 (14 de octubre): compra de timbres con Mercado Pago, vencimiento a 12 meses, «Mis timbres», borradores legales y CONECTAR.md
- Timbrado para terceros (2.13.0, en el servidor): PAC de la plataforma, alta automática del RFC en Finkok, saldo de timbres por cuenta con recarga manual
- XML del SAT dentro de Timbra, con la e.firma sólo en memoria y el Excel de 65 columnas
- Modo soporte, endurecimiento de seguridad, persistencia del servidor comprobada

### Legal y fiscal (revisión del 17-oct-2026)
- [x] [Claude] Textos corregidos contra lo que hace la app, versión legal 2026-10-17, domicilio general y completo aparte
- [x] [Claude] Centro legal, guía fiscal, aviso corto y casilla de novedades en el registro, «Mis datos» y cierre de cuenta
- [ ] [Rick] Domicilio de despacho u oficina virtual para notificaciones (si lo hay, cambiar `domicilioCompleto` en `lib/legal.ts`)
- [ ] [Rick + contador] Validar la guía fiscal (`lib/fiscal.ts`, poner `VALIDADO = true`): números de regla de la RMF, plazo de cancelación, vigencia del IVA 8% fronterizo
- [ ] [Rick + abogado] Retracto del consumidor en timbres no usados, cláusulas de encargado para datos de nómina, plazos ARCO de la ley de 2025
- [ ] [Rick + contador] Régimen e IVA propios, CFDI por cada recarga y esquema de reventa con Finkok
- [ ] [Rick] Borrar a mano, antes de 90 días, los datos de cuentas que cierran (aviso «CIERRE DE CUENTA» en el registro y en el correo de respaldo)
