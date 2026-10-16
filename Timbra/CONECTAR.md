# Conectar Timbra: paso a paso para Rick

Todo lo que Timbra necesita de afuera. Cada bloque dice qué haces tú y qué compruebo yo después.
Las llaves y contraseñas **nunca** van en el chat ni en el repositorio: las pegas tú en Railway.

Railway → tu proyecto → el servicio de Timbra → **Variables** → «New Variable». Al guardar, Railway vuelve a desplegar solo.

---

## 1. Finkok productivo (para timbrar de verdad)

1. Manda el borrador que está en tu Gmail (hilo «FINKOK | Kit de Pruebas») con tu RFC, la solicitud firmada y tu Constancia.
2. Cuando Finkok te dé el usuario y la contraseña de producción, sigue `DESPLEGAR.md` → «Día del arranque».

**Yo compruebo:** que el botón «Comprobar y dar de alta el RFC» diga «Credenciales correctas» y que tu primera factura
real aparezca en el SAT.

---

## 2. Correo (Resend) — para mandar facturas y recibir el respaldo diario

1. Entra a **resend.com** y crea tu cuenta (con Google es lo más rápido).
2. **Domains → Add Domain** → escribe `erickddp.com` → región la que proponga.
3. Resend te muestra 3 o 4 registros (TXT y MX). Cópialos **en el lugar donde configuraste `factura.erickddp.com`**
   (el panel de tu dominio: donde lo compraste, o Cloudflare si lo usas). Tipo, nombre y valor, tal cual.
4. Regresa a Resend y pulsa **Verify**. Puede tardar de minutos a unas horas.
5. **API Keys → Create API Key** → permiso «Sending access» → cópiala.
6. En Railway agrega:
   - `RESEND_API_KEY` = la llave
   - `RESPALDO_CORREO` = tu correo (ahí llega el respaldo cifrado de cada día)
7. En Timbra → Ajustes → Correo de envío → **Enviar prueba**.

**Yo compruebo:** que llegue la prueba, que una factura enviada llegue con el nombre del emisor, y que al día siguiente
te llegue `timbra_AAAAMMDD.timbra` y se abra con `restaurar_respaldo.py`.

---

## 3. Mercado Pago — para que tus clientes compren timbres solos

**Primero en modo prueba (no se cobra nada):**
1. Entra a **mercadopago.com.mx/developers** con tu cuenta de Mercado Pago (la que recibirá el dinero).
2. **Tus integraciones → Crear aplicación** → nombre «Timbra» → producto **Checkout Pro** → pagos en línea.
3. En la aplicación, **Credenciales de prueba** → copia el **Access Token** (empieza con `TEST-`).
4. En Railway agrega `MP_ACCESS_TOKEN` = ese token de prueba.
5. En la aplicación, **Webhooks → Configurar notificaciones**:
   - URL de producción: `https://factura.erickddp.com/api/pagos/aviso`
   - Evento: **Pagos**
   - Guarda y copia la **clave secreta** → en Railway `MP_WEBHOOK_SECRET` = esa clave.
6. Avísame: hago una compra de prueba con una cuenta de prueba de Mercado Pago y reviso que se abonen los timbres.

**Después, para cobrar de verdad:**
7. En la aplicación, **Credenciales de producción** (Mercado Pago puede pedirte datos de tu negocio).
8. Cambia en Railway `MP_ACCESS_TOKEN` por el de producción (empieza con `APP_USR-`).
9. Haz tú una compra real del paquete más chico ($50) y confirma que te llegan los timbres.

**Precios:** están en `backend/app/services/pagos.py`. Para cambiarlos sin tocar código, agrega en Railway
`PAQUETES_TIMBRES` con algo así: `[{"clave":"p30","timbres":30,"precio":50},{"clave":"p100","timbres":100,"precio":130}]`

---

## 4. Google — entrar con Google en la web y guardar en Drive

1. Usa el prompt que ya tienes para Claude en Chrome, o en Google Cloud (proyecto `timbra-eddp`):
   **APIs y servicios → Credenciales → tu cliente OAuth → URIs de redireccionamiento autorizados** → agrega
   `https://factura.erickddp.com/api/auth/google/callback`.
2. En Railway agrega `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` (con `python google_env.py copiar secreto`) y
   `GOOGLE_REDIRECT_URI` = `https://factura.erickddp.com/api/auth/google/callback`.
3. Prueba «Entrar con Google» en factura.erickddp.com.

**Ojo:** mientras la pantalla de consentimiento esté en modo «Prueba», sólo pueden entrar los correos que agregues como
usuarios de prueba. Para abrirlo a todos hay que publicarla (y Google revisa los permisos de Drive).

---

## 5. Abrir Timbra a clientes nuevos

1. Revisa y llena los borradores de `legal/AVISO_DE_PRIVACIDAD.md` y `legal/TERMINOS_DE_USO.md` (lo que está entre
   corchetes). Avísame y los publico como páginas dentro de Timbra.
2. Cuando Mercado Pago esté en producción y los textos publicados: en Railway `REGISTRO_ABIERTO=true` (cualquiera con
   Google crea su cuenta con 3 timbres de regalo).

---

## Resumen de variables en Railway

| Variable | Para qué | Ya está |
|---|---|---|
| `SECRET_KEY`, `JWT_SECRET`, `ADMIN_PASSWORD` | Arranque seguro | Sí |
| `RESEND_API_KEY` | Mandar correos | |
| `RESPALDO_CORREO` | Respaldo diario fuera del servidor | |
| `MP_ACCESS_TOKEN` | Cobrar timbres | |
| `MP_WEBHOOK_SECRET` | Firmar los avisos de pago | |
| `PAQUETES_TIMBRES` | Cambiar precios (opcional) | |
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REDIRECT_URI` | Entrar con Google | |
| `REGISTRO_ABIERTO` | Que cualquiera cree su cuenta | Al final |
