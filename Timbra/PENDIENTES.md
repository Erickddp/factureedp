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
- [ ] [Claude] Revisar cuánto te cuesta cada timbre con Finkok ($150 + IVA hasta 500 al mes, $0.30 + IVA después) y proponer precios de paquetes
- [ ] [Rick] Decidir precios de los paquetes de timbres

### Mejorar
- [ ] [Claude] Panel de inicio y bienvenida para cuentas nuevas (ver nota de memoria «panel de inicio y onboarding»)

### Hacer
- [ ] [Rick] Abrir la cuenta de Mercado Pago y darme las llaves (las pones tú en Railway)
- [x] Aviso de privacidad y términos de uso redactados y conectados (/legal/terminos, /legal/privacidad; cada cuenta los acepta)
- [ ] [Rick] Llenar nombre legal, RFC y domicilio del responsable en `frontend/src/lib/legal.ts` (hoy salen resaltados en amarillo)
- [ ] [Rick] Crear el buzón privacidad@erickddp.com (o cambiarlo en `lib/legal.ts`)
- [ ] [Rick] Revisar los textos con abogado antes de abrir el registro; confirmar plazo de borrado (90 días) y la política de reembolso

### Construir
- [ ] [Claude] Recargas con Mercado Pago (paga y el saldo sube solo)
- [ ] [Claude] Caducidad de timbres a 12 meses
- [ ] [Claude] Manifiesto de Finkok por emisor (opcional según Finkok)
- [ ] [Claude] Registro abierto con Google para clientes nuevos

### Guiar
- [ ] [Claude] Guía para tus clientes: cómo entrar, dar de alta su CSD y facturar
- [ ] [Rick] Dar de alta a tu primer cliente de paga

---

## Lo que ya está hecho (13 de octubre)

- Timbrado para terceros (2.13.0, en el servidor): PAC de la plataforma, alta automática del RFC en Finkok, saldo de timbres por cuenta con recarga manual
- XML del SAT dentro de Timbra, con la e.firma sólo en memoria y el Excel de 65 columnas
- Modo soporte, endurecimiento de seguridad, persistencia del servidor comprobada
