# Pendientes de Timbra: camino a producción

Lista compartida. Cada tarea dice quién la hace: **[Claude]** o **[Rick]**.
Para tacharla, cambia `[ ]` por `[x]`. Claude la tacha cuando la termina y la comprueba.

Meta: Timbra en producción el **16 de octubre de 2026**, facturando con Finkok productivo.

Cada fase tiene cinco pasos: **aprender** (revisar qué hay), **mejorar** (corregir lo que falla), **hacer** (lo operativo), **construir** (lo nuevo) y **guiar** (los pasos para Rick).

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
- [ ] [Rick] Revisar y llenar los borradores en `legal/` (aviso de privacidad y términos)

### Construir
- [x] [Claude] Compra de timbres con Mercado Pago: el cliente elige paquete, paga y los timbres se abonan solos, una sola vez, después de confirmar el pago con Mercado Pago (no se activa hasta que pongas la llave)
- [x] [Claude] Caducidad de timbres a 12 meses: se gastan primero los que vencen antes; los 3 de regalo no vencen
- [x] [Claude] Pantalla «Mis timbres» para clientes: saldo, cuándo vencen, paquetes, movimientos y compras
- [x] [Claude] Borradores de aviso de privacidad y términos de uso (`legal/`)
- [ ] [Claude] Publicar aviso y términos como páginas, con casilla de aceptación al crear cuenta (cuando los revises)
- [ ] [Claude] Manifiesto de Finkok por emisor (opcional según Finkok)
- [ ] [Claude] Registro abierto con Google para clientes nuevos (ya existe `REGISTRO_ABIERTO`; falta la bienvenida)

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
- [ ] [Claude] Publicarlos, casilla de aceptación y bienvenida para cuentas nuevas
- [ ] [Rick] `REGISTRO_ABIERTO=true` y tu primer cliente de paga
- [ ] [Claude] Revisar los registros del servidor de las primeras semanas y lo que vaya saliendo

---

## Lo que ya está hecho (13 de octubre)

- 2.14.0 (14 de octubre): compra de timbres con Mercado Pago, vencimiento a 12 meses, «Mis timbres», borradores legales y CONECTAR.md
- Timbrado para terceros (2.13.0, en el servidor): PAC de la plataforma, alta automática del RFC en Finkok, saldo de timbres por cuenta con recarga manual
- XML del SAT dentro de Timbra, con la e.firma sólo en memoria y el Excel de 65 columnas
- Modo soporte, endurecimiento de seguridad, persistencia del servidor comprobada
