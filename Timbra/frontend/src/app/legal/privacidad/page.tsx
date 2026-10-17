import type { Metadata } from "next";
import Link from "next/link";
import { Dato, PaginaLegal } from "@/components/legal";
import { RESPONSABLE } from "@/lib/legal";

export const metadata: Metadata = { title: "Aviso de privacidad · Timbra" };

/**
 * Aviso de privacidad integral conforme a la Ley Federal de Protección de Datos Personales en Posesión de los Particulares
 * (DOF 20-mar-2025). Si agregas un proveedor que reciba datos (otro PAC, otro correo, otro hosting), agrégalo en «Con quién».
 */
export default function Privacidad() {
  const r = RESPONSABLE;
  return (
    <PaginaLegal titulo="Aviso de privacidad">
      <h2>1. Quién es responsable de tus datos</h2>
      <p>
        <Dato v={r.nombre} /> (RFC <Dato v={r.rfc} />), que opera {r.marca} bajo el nombre comercial EDDP Servicios, con domicilio en{" "}
        <Dato v={r.domicilio} />, es responsable del uso y protección de los datos personales que nos das al usar {r.marca}.
        Contacto para todo lo relacionado con tus datos: <a className="underline" href={`mailto:${r.correo}`}>{r.correo}</a>.
      </p>

      <h2>2. Qué datos usamos</h2>
      <ul>
        <li><b>De tu cuenta:</b> nombre, correo, nombre de usuario, contraseña (guardada sólo como huella cifrada, nunca en texto) y, si la conectas, tu identidad de Google (correo e identificador).</li>
        <li><b>Fiscales de cada emisor que des de alta:</b> RFC, nombre o razón social, régimen fiscal, código postal, logotipo y datos de contacto.</li>
        <li><b>Certificado de sello digital (CSD):</b> archivos .cer y .key y su contraseña. Se guardan cifrados y sólo se usan para sellar las facturas que tú ordenas.</li>
        <li><b>e.firma:</b> sólo para descargar tus XML del SAT. Se usa en memoria mientras dura la descarga y <b>no se guarda</b> en ningún disco, base de datos ni respaldo.</li>
        <li><b>De tus clientes y empleados</b> (receptores de tus facturas y recibos de nómina): RFC, nombre, régimen, código postal, correo, teléfono y, en nómina, CURP, número de seguridad social y percepciones.</li>
        <li><b>Técnicos:</b> dirección IP, fecha y hora de acceso y registro de errores, para seguridad y soporte.</li>
      </ul>
      <p>
        No pedimos datos sensibles. Los datos de nómina se tratan con el mismo cuidado que si lo fueran.
      </p>

      <h2>3. Para qué los usamos</h2>
      <p><b>Finalidades necesarias</b> para darte el servicio:</p>
      <ul>
        <li>Crear y proteger tu cuenta, y verificar tu identidad al entrar.</li>
        <li>Armar, sellar y timbrar tus CFDI a través de un proveedor de certificación (PAC) autorizado por el SAT, y cancelarlos cuando lo pidas.</li>
        <li>Generar PDF, enviar facturas por correo a quien tú indiques y descargar tus XML del SAT.</li>
        <li>Llevar tu saldo de timbres, tu cobranza y tus plantillas.</li>
        <li>Hacer respaldos cifrados y recuperar tu información si algo falla.</li>
        <li>Darte soporte. El acceso de soporte a tu cuenta dura 2 horas, queda registrado y lo puedes ver en tu perfil.</li>
        <li>Cumplir obligaciones legales y atender requerimientos de autoridad.</li>
      </ul>
      <p>
        <b>Finalidad adicional:</b> avisarte de novedades y cambios de {r.marca}. Si no la quieres, escríbenos a {r.correo}; negarte no afecta el
        servicio. No vendemos tus datos ni los usamos para publicidad de terceros.
      </p>

      <h2>4. Datos de tus clientes y empleados</h2>
      <p>
        Cuando capturas datos de tus clientes o empleados, <b>tú eres el responsable</b> de ellos frente a sus titulares y {r.marca} actúa como encargado:
        sólo los usa para hacer las facturas, recibos y envíos que tú ordenas. Te toca contar con su aviso de privacidad y su consentimiento cuando la ley
        lo pida. Si alguno de ellos nos busca para ejercer sus derechos, te lo canalizamos.
      </p>

      <h2>5. Con quién los compartimos</h2>
      <ul>
        <li><b>El PAC</b> (hoy Finkok) y <b>el SAT</b>: reciben el CFDI para timbrarlo, validarlo o cancelarlo. Es obligatorio por ley para facturar.</li>
        <li><b>Proveedores que nos dan infraestructura</b>, sólo para operar {r.marca} y bajo obligación de confidencialidad: alojamiento del servidor
          (Railway), envío de correos (Resend), cobro de timbres (Mercado Pago; Timbra no ve ni guarda los datos de tu tarjeta) e inicio de sesión (Google, sólo si lo usas). Algunos tienen sus servidores fuera de México, por ejemplo
          en Estados Unidos.</li>
        <li><b>Autoridades</b>, cuando lo exija la ley o una orden fundada.</li>
      </ul>
      <p>Estas comunicaciones no requieren tu consentimiento porque son necesarias para el servicio que contratas o las exige la ley.</p>

      <p>
        <b>Inicio de sesión con Google.</b> Si eliges «Continuar con Google», {r.marca} pide sólo los permisos básicos de identidad (openid, correo y perfil) y
        recibe tu correo, tu nombre y un identificador de tu cuenta de Google, únicamente para reconocerte y abrir o crear tu cuenta. {r.marca} no accede a tu
        Gmail, Drive, Calendario, contactos ni a ningún otro dato de tu cuenta de Google, y no usa esta información para publicidad ni la vende o transfiere a
        terceros. El uso de la información recibida de las API de Google se apega a la Política de datos de usuario de los servicios de API de Google, incluidos
        sus requisitos de uso limitado. Puedes desconectar tu cuenta de Google en Mi perfil, o revocar el acceso desde la configuración de seguridad de tu cuenta de Google.
      </p>

      <h2>6. Cómo los protegemos</h2>
      <ul>
        <li>Conexión cifrada (HTTPS) en todo momento.</li>
        <li>CSD, contraseñas de PAC y respaldos cifrados con llave propia del servidor.</li>
        <li>Cada cuenta ve sólo sus emisores; el acceso de soporte es temporal y queda registrado.</li>
        <li>Freno automático a intentos repetidos de entrar con contraseña equivocada.</li>
      </ul>

      <h2>7. Cuánto tiempo los guardamos</h2>
      <p>
        Mientras tengas cuenta. Si la cierras, borramos tus datos en un plazo máximo de 90 días, salvo los CFDI y la información que la ley fiscal
        obliga a conservar (5 años, artículo 30 del Código Fiscal de la Federación), que se guardan bloqueados sólo para ese fin.
      </p>

      <h2>8. Tus derechos (ARCO) y cómo ejercerlos</h2>
      <p>
        Puedes <b>acceder</b> a tus datos, <b>rectificarlos</b>, <b>cancelarlos</b> u <b>oponerte</b> a su uso, y también revocar tu consentimiento o
        limitar su uso. Escribe a <a className="underline" href={`mailto:${r.correo}`}>{r.correo}</a> desde el correo de tu cuenta con:
      </p>
      <ul>
        <li>Tu nombre y el correo de tu cuenta.</li>
        <li>Una identificación oficial (o la de tu representante y el documento que lo acredite).</li>
        <li>Qué derecho quieres ejercer y sobre qué datos.</li>
      </ul>
      <p>
        Te respondemos en un máximo de 20 días hábiles y, si procede, lo aplicamos dentro de los 15 días hábiles siguientes. Muchos datos los puedes
        corregir tú mismo desde {r.marca} (Mi perfil, Emisores, Clientes). Si consideras que no atendimos tu solicitud, puedes acudir a la autoridad
        de protección de datos personales (Secretaría Anticorrupción y Buen Gobierno).
      </p>

      <h2>9. Almacenamiento en tu navegador</h2>
      <p>
        {r.marca} no usa cookies de publicidad ni de rastreo. Guarda en tu navegador sólo lo necesario para funcionar: tu sesión, el tema (claro u
        oscuro) y cómo dejaste el menú.
      </p>

      <h2>10. Cambios a este aviso</h2>
      <p>
        Si cambia algo de fondo, te lo pediremos aceptar de nuevo al entrar a {r.marca}. La versión vigente siempre está en esta página. Consulta
        también los <Link className="underline" href="/legal/terminos/">Términos de uso</Link>.
      </p>
    </PaginaLegal>
  );
}
