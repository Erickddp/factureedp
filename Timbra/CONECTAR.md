# Conectar Timbra: paso a paso para Rick

Todo lo que Timbra necesita de afuera. Cada bloque dice qué haces tú y qué compruebo yo después.
Las llaves y contraseñas **nunca** van en el chat ni en el repositorio: las pegas tú en Railway.

Railway → tu proyecto → el servicio de Timbra → **Variables** → «New Variable». Al guardar, Railway vuelve a desplegar solo.

---

## 0. Tus emisores en la web (exportar de tu PC e importar en la web)

Ajustes → **«Pasar mis emisores a otra Timbra»** (está en tu PC y en la web).

1. **En tu PC** (INICIAR.bat): palomea los emisores que quieres llevar. Los de pruebas del SAT (EKU, IVD, XIQB…) vienen
   sin palomear: no valen ante el SAT. Deja «Incluir las facturas timbradas» si quieres el historial, escribe una
   contraseña de 10 o más caracteres (dos veces) y pulsa **Exportar**. Se baja un archivo `.timbracuenta`.
2. **En factura.erickddp.com**, misma pantalla, lado derecho: **Elegir archivo**, la contraseña, **Revisar archivo**.
   Te dice qué entraría y no guarda nada. Si todo está bien, **Importar**.
3. En **Emisores**, elige el PAC de cada uno cuando tengas el de producción, y revisa que su CSD no esté vencido.
4. **Desde ese día factura sólo desde la web.** Si sigues timbrando el mismo emisor en las dos, los folios se repiten.
5. Borra el archivo `.timbracuenta` (trae tus llaves privadas, aunque va cifrado).

Qué se lleva: el emisor, su CSD (cer, key y contraseña), series y folios, clientes, productos, terceros, empleados,
perfiles de lote, plantillas y, si lo pides, las facturas con su XML. Qué NO se lleva: el PAC, la e.firma, los XML que
bajaste del SAT (se vuelven a leer o a bajar) ni los lotes.

**Ojo con lo que hay hoy en tu PC:** EKU, IVD y XIQB usan el CSD de PRUEBAS del SAT (su número empieza con 30001…), y
FODA y RAQUEL HILARIO son contribuyentes que sólo creaste al leer XML (no tienen CSD). **Ningún emisor de tu PC tiene un
CSD real.** Los CSD reales de tus emisores hay que subirlos en la web: Emisores → emisor → CSD (el .cer, el .key y su
contraseña, del portal del SAT).

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
2. Cuando Mercado Pago esté en producción y los textos publicados: en Railway `REGISTRO_ABIERTO=true`. Cualquiera crea su cuenta
   con correo y contraseña, o con Google (no hace falta Google para entrar). Recibe 3 timbres de regalo al confirmar su correo:
   por eso `RESEND_API_KEY` tiene que estar puesta **antes** de abrir el registro (los enlaces usan `URL_PUBLICA`, que ya trae
   `https://factura.erickddp.com` por defecto).
   Prueba tú primero: crea una cuenta con otro correo tuyo, confirma el enlace (revisa Spam) y entra de nuevo sin Google.

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
| `URL_PUBLICA` | Base de los enlaces de confirmar correo y recuperar contraseña | Trae el valor correcto por defecto |
| `REGISTRO_ABIERTO` | Que cualquiera cree su cuenta | Al final |
