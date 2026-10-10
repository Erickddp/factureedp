# Poner a Timbra a timbrar de verdad (paso a paso)

**Tu app no se certifica ante el SAT.** El único autorizado es el PAC. Lo que sí piden los PAC es que hagas pruebas en su
ambiente de pruebas antes de darte acceso de producción. Timbra ya trae el botón **Probar timbrado** para eso.

## Lo que necesitas por cada RFC que va a facturar
1. **CSD** (Certificado de Sello Digital): `.cer`, `.key` y su contraseña. No es la e.firma. Se tramita gratis en el SAT con la e.firma.
   Un CSD recién tramitado puede tardar de 24 a 72 horas en funcionar.
2. Que ese RFC esté **dado de alta en tu cuenta del PAC**.

## Finkok (recomendado: pagas al mes lo que timbraste)
- Costo: $150 + IVA al mes de 0 a 500 timbres; del 501 en adelante $0.30 + IVA c/u. Sin anualidad ni plazo forzoso.
- Te asignan un asesor de integración (viene en el Kit de Pruebas que te mandan por correo).

### A. Cuenta demo (10 min)
1. Regístrate en https://demo-facturacion.finkok.com/cuentas/registrar/?upr=S . **Ese correo y contraseña son los que pones en Timbra.**
2. Activa la cuenta con el correo que te llega (revisa SPAM; **caduca en 14 días** si no la activas).
3. Entra, llena el asistente de datos fiscales (en demo pueden ser ficticios) y acepta el contrato.

### B. RFC y CSD de pruebas
4. Entra a la wiki de Finkok con el usuario/contraseña que vienen en tu Kit de Pruebas → sección *Certificados*:
   baja el .cer, .key, contraseña y datos (nombre, régimen, CP) de un RFC de pruebas, por ejemplo EKU9003173C9.
5. En el panel demo: **Clientes → Agregar → Persona Moral** → RFC de pruebas, correo, tipo **OnDemand** → Agregar.

### C. En Timbra
6. *Emisores y CSD* → **+ RFC emisor** con los datos EXACTOS del RFC de pruebas de la wiki (nombre, régimen, CP) → **Subir CSD** de prueba.
7. *PAC, addendas y usuarios* → **+ PAC** → Finkok → usuario = correo de la cuenta demo, contraseña = la de la cuenta demo → deja **pruebas** marcado.
8. Edita el emisor y asígnale ese PAC.
9. En la tarjeta del PAC: **Probar timbrado**. Debe regresarte un UUID.
   **Probar ciclo completo** hace de un jalón timbrar → cancelar (motivo 02) → consultar estatus: es justo lo que Finkok revisa (pasos 10-12).

### D. Pruebas que Finkok revisa para darte producción
10. **Timbrar**: haz una factura normal en *Facturar* (cliente cualquiera con RFC de pruebas, p. ej. KIJ0906199R1).
11. **Cancelar**: en *Facturas* → ⋯ → Cancelar ante el SAT (motivo 02). Finkok espera respuesta 201 o 202.
12. **Consultar estatus**: ⋯ → **Consultar estatus en el SAT** (usa su método `get_sat_status`).
13. Escríbele a tu asesor de integración: le dices que ya timbraste, cancelaste y consultaste estatus, con el correo de tu cuenta demo.
    Él revisa y te pide la documentación para tu cuenta de producción; te mandan el pase por correo.

### E. Producción
14. En https://facturacion.finkok.com da de alta **cada RFC real** (Clientes → Agregar, OnDemand).
15. En Timbra: crea los emisores reales con su CSD real, edita el PAC con el usuario/contraseña de producción y **desmarca "pruebas"**.

## SW Sapien (alternativa prepago)
- Tienda en línea: 1,200 timbres $2,266 · 5,000 $5,530 · 10,000 $8,230 (https://tienda.sw.com.mx/shop).
  Los paquetes publicados dicen "para Odoo": confirma con ventas que sirvan por API antes de pagar.
1. Pide tu usuario de pruebas gratis (developers.sw.com.mx).
2. En Timbra: **+ PAC** → SW Sapien → usuario y contraseña (o token) → pruebas marcado → **Probar timbrado**.
3. Compra timbres, cambia a credenciales de producción y desmarca "pruebas".

## Facturama no sirve con Timbra
Facturama sella con sus propios servicios y no acepta el XML ya sellado por tu sistema. Por eso no aparece en la lista.

Precios consultados en septiembre de 2026; confírmalos al contratar.
