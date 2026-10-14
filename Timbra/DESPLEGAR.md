# Subir Timbra a la web

Hay dos formas. Empieza por la **A**: es un solo servicio y una sola dirección.

| | A. Sólo Railway | B. Railway + Vercel |
|---|---|---|
| Qué corre dónde | Railway sirve todo: servidor y pantallas | Railway el servidor, Vercel las pantallas |
| Direcciones | Una | Dos (hay que enlazarlas) |
| Cuándo conviene | Para empezar y para uso propio | Cuando quieras dominio y despliegue de pantallas por separado |

> **Antes de subirla:** en web cualquiera puede llegar a la pantalla de entrada. Timbra no arranca en un servidor si las
> llaves o la contraseña son las de ejemplo (ver variables abajo). Hoy todos los usuarios ven todos los emisores: no des
> acceso a terceros hasta separar las cuentas.

## A. Railway (servidor + pantallas)

1. En railway.com: **New Project → Deploy from GitHub repo →** `factureedp`.
2. En el servicio → **Settings → Root Directory:** `Timbra/backend`. Railway detecta el `Dockerfile`.
3. **Volumes → New Volume**, montado en `/data`. **Sin volumen se pierden la base de datos y los XML en cada despliegue.**
   (El disco se crea en el panel de Railway; el Dockerfile no lo declara porque Railway rechaza la instrucción `VOLUME`.)
   **No agregues** las variables `DATA_DIR`, `DATABASE_URL` ni `DEBUG` que Railway sugiere: sobreescriben las del Dockerfile y sacan la base del volumen.
4. **Variables** (pestaña Variables):

   | Variable | Valor |
   |---|---|
   | `SECRET_KEY` | cadena aleatoria de 40+ caracteres. **Guárdala aparte**: sin ella no se descifran los CSD |
   | `JWT_SECRET` | otra cadena aleatoria de 40+ caracteres |
   | `ADMIN_EMAIL` | tu correo de acceso |
   | `ADMIN_PASSWORD` | contraseña inicial de 10+ caracteres (cámbiala después en Mi perfil) |
   | `CORS_ORIGINS` | sólo para la opción B: la dirección de Vercel, p. ej. `https://timbra.vercel.app` |

   Para generar cadenas aleatorias en tu PC: `python -c "import secrets;print(secrets.token_urlsafe(48))"`
5. **Settings → Networking → Generate Domain.** Abre esa dirección: debe salir la pantalla de entrada.
6. Entra, da de alta el PAC, el emisor y su CSD (los datos de tu PC **no** se copian solos; ver "Llevar mis datos").

## B. Agregar Vercel para las pantallas (opcional)

1. En vercel.com: **Add New → Project →** `factureedp`.
2. **Root Directory:** `Timbra/frontend`. Framework: Next.js (lo detecta).
3. **Environment Variables:** `NEXT_PUBLIC_API_URL` = la dirección de Railway, sin diagonal al final
   (p. ej. `https://timbra-production.up.railway.app`).
4. Deploy. Luego, en Railway, pon esa dirección de Vercel en `CORS_ORIGINS` y vuelve a desplegar.

## Llevar mis datos de la PC al servidor

La base de datos y los CSD están cifrados con la `SECRET_KEY` de tu `backend/.env`. Para llevarlos:
usa en Railway **la misma** `SECRET_KEY` de tu PC y copia `datos/timbra.db` y `datos/respaldo_xml` al volumen `/data`.
Si prefieres empezar limpio, sólo vuelve a subir el CSD en el servidor.

## Qué cambia respecto a la PC

- **PDF:** se generan con Chromium dentro del servidor (mismo resultado que con Edge en Windows).
- **Base de datos:** el mismo archivo SQLite, en el volumen. Sirve bien para una sola instancia; para muchos usuarios
  simultáneos habrá que pasar a Postgres.
- **Carpeta de Drive (G:\)** y respaldos locales: no existen en el servidor; ahí Drive tendrá que ir por la API de Google.
- **Google (inicio de sesión):** agrega en Google Cloud la dirección web como origen y como URI de redirección
  (`https://TU-DIRECCION/api/auth/google/callback`), y pon `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` y `GOOGLE_REDIRECT_URI`
  en las variables de Railway. Con Vercel aparte, pon también `FRONT_URL` con la dirección de Vercel.
- **Cuentas:** cada usuario ve sólo sus emisores. Las cuentas las crea el administrador; `REGISTRO_ABIERTO=true` deja que
  cualquiera con Google cree la suya (no lo actives hasta tener cobro y términos de servicio).

## Día del arranque: pasar a Finkok de producción

Cuando Finkok te mande el usuario y la contraseña de producción, en `https://factura.erickddp.com`:

1. **Ajustes → PAC → Agregar PAC.** Proveedor Finkok, tu usuario y contraseña de producción.
   Quita la palomita de «Ambiente de pruebas» y pon la de «Usar este PAC para todas las cuentas». Guarda.
   - Los emisores de tus clientes que timbraban con el de pruebas se pasan solos al nuevo.
   - Los tuyos no se mueven solos (algunos son RFC de prueba): el Resumen de cada uno te avisa en rojo si sigue en pruebas.
2. **Comprueba las credenciales sin gastar timbres.** En la tarjeta del PAC nuevo elige un emisor y pulsa
   «Comprobar y dar de alta el RFC». Debe decir «Credenciales correctas». Si dice que Finkok rechazó el usuario o la
   contraseña, edita el PAC y vuelve a escribirla.
3. **Emisores → Editar** cada emisor tuyo que vaya a facturar de verdad: en «PAC» elige el de producción. Revisa que su CSD
   esté vigente (el Resumen avisa si no).
4. **Primera factura real:** una factura chica a un cliente de confianza. Al timbrar ya no aparece el aviso amarillo de
   «ambiente de pruebas». Búscala en el portal del SAT (Verificación de CFDI) con su UUID.
5. **Clientes con cuenta propia:** cada cuenta trae 3 timbres. Para recargar: Ajustes → Cuentas → «Recargar».
   La primera factura real de cada cliente, hazla junto con él.

Si algo sale mal, desmarca «Usar este PAC para todas las cuentas»: los emisores de los clientes quedan sin PAC
(no timbran) y los tuyos siguen como los dejaste.

## Estado

En producción en `https://factura.erickddp.com` (Railway, despliegue automático con cada push a `main`).
Persistencia del volumen comprobada en varios despliegues (`/api/health` → `almacen`).
