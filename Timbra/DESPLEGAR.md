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
- **Google (inicio de sesión):** agrega en Google Cloud la dirección web como origen y como URI de redirección, y pon
  `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` y `GOOGLE_REDIRECT_URI` en las variables de Railway.

## Estado

Preparado pero **no probado en un despliegue real**: esta PC no tiene Docker. Cuenta con una ronda de ajustes en el primer intento.
