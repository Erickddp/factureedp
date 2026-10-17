import type { Metadata } from "next";
import Link from "next/link";
import { Dato, PaginaLegal } from "@/components/legal";
import { RESPONSABLE } from "@/lib/legal";

export const metadata: Metadata = { title: "Términos de uso · Timbra" };

/** Términos de uso del servicio. Precios y paquetes viven en la página de inicio (/inicio#precios); aquí sólo las reglas. */
export default function Terminos() {
  const r = RESPONSABLE;
  return (
    <PaginaLegal titulo="Términos de uso">
      <p>
        Estos términos son el acuerdo entre tú y <Dato v={r.nombre} /> (RFC <Dato v={r.rfc} />), que opera {r.marca} bajo el nombre comercial
        EDDP Servicios, con domicilio en <Dato v={r.domicilio} />. Al crear una cuenta o usar {r.marca} los aceptas. Si no estás de acuerdo, no uses
        el servicio.
      </p>

      <h2>1. Qué es {r.marca}</h2>
      <p>
        {r.marca} es un programa en internet para emitir comprobantes fiscales digitales (CFDI 4.0) a nombre de uno o varios emisores, llevar
        clientes, productos, cobranza y nómina, y descargar tus XML del SAT. El timbrado lo hace un proveedor de certificación (PAC) autorizado por el
        SAT. {r.marca} no es el SAT ni un PAC.
      </p>

      <h2>2. Tu cuenta</h2>
      <ul>
        <li>Debes ser mayor de edad y tener capacidad para contratar, o actuar en nombre de una empresa que te lo autorice.</li>
        <li>Eres responsable de lo que se haga con tu usuario y contraseña. Avísanos de inmediato si sospechas que alguien más entró.</li>
        <li>Sólo puedes dar de alta emisores para los que tengas autorización: el tuyo propio o el de tus clientes que te lo hayan encargado.</li>
      </ul>

      <h2>3. Lo que te toca a ti</h2>
      <ul>
        <li><b>La información fiscal es tuya.</b> Tú decides qué facturar, a quién, por cuánto y con qué datos. {r.marca} valida muchas reglas del
          SAT antes de timbrar, pero esa validación es una ayuda y no sustituye tu revisión ni la de tu contador.</li>
        <li><b>No es asesoría fiscal.</b> Las notas y sugerencias de claves, impuestos o regímenes son orientación general.</li>
        <li><b>Tu CSD y tu e.firma.</b> Eres responsable de que estén vigentes y de que quien los sube tenga derecho a usarlos. La e.firma es personal e
          intransferible: si la usas para descargar los XML de un cliente, debes contar con su autorización por escrito. {r.marca} la usa sólo en memoria durante la
          descarga y no la guarda, pero el uso que le des es tu responsabilidad y la de su titular.</li>
        <li><b>Modo de pruebas.</b> Los comprobantes que se generan con el PAC «Demo» o en ambiente de pruebas no tienen validez fiscal.</li>
        <li><b>Datos de terceros.</b> Si capturas datos de tus clientes o empleados, te toca tener su consentimiento cuando la ley lo pida (ver el{" "}
          <Link className="underline" href="/legal/privacidad/">Aviso de privacidad</Link>).</li>
        <li><b>Uso lícito.</b> Prohibido usar {r.marca} para emitir comprobantes de operaciones inexistentes o simuladas, para suplantar a otra persona,
          o para intentar vulnerar el sistema o las cuentas de otros.</li>
      </ul>

      <h2>4. Timbres y pagos</h2>
      <ul>
        <li>Cada factura, nota de crédito, complemento de pago o recibo de nómina timbrado consume un timbre de tu saldo. Los precios vigentes están
          en la <Link className="underline" href="/inicio/#precios">página de precios</Link>.</li>
        <li>Los timbres se pagan por adelantado a través de Mercado Pago y se abonan cuando el pago se confirma. No hay renta mensual.</li>
        <li>Los timbres comprados vencen a los 12 meses de la compra; primero se usan los que vencen antes.</li>
        <li>Un timbre usado no se devuelve, aunque después canceles la factura: el PAC y el SAT ya lo procesaron. Los timbres no usados no son reembolsables
          salvo que la ley lo exija o que {r.marca} deje de prestar el servicio.</li>
        <li>Si usas tu propio PAC, el consumo y el pago de timbres son entre tú y ese PAC.</li>
      </ul>

      <h2>5. Disponibilidad y respaldos</h2>
      <p>
        Hacemos lo razonable para que {r.marca} esté disponible y respaldamos la información todos los días. Aun así, el servicio puede detenerse
        por mantenimiento, fallas de internet, del PAC o del SAT, que no controlamos. Te recomendamos descargar periódicamente tus XML y PDF. Los
        CFDI timbrados siempre se pueden recuperar con el SAT.
      </p>

      <h2>6. Hasta dónde respondemos</h2>
      <p>
        En la medida que la ley lo permita, {r.marca} no responde por multas, recargos o pérdidas derivadas de datos que tú capturaste, de decisiones
        fiscales tuyas, ni de fallas del PAC, del SAT o de tu conexión. Si {r.marca} falla por causa propia, nuestra responsabilidad total se limita a
        lo que nos hayas pagado en los 12 meses anteriores al hecho. Nada de esto limita los derechos que te da la Ley Federal de Protección al
        Consumidor cuando seas consumidor.
      </p>

      <h2>7. Suspensión y cierre de cuenta</h2>
      <ul>
        <li>Puedes cerrar tu cuenta cuando quieras escribiendo a <a className="underline" href={`mailto:${r.correo}`}>{r.correo}</a>. Antes te damos
          la oportunidad de descargar tus XML y PDF.</li>
        <li>Podemos suspender una cuenta que viole estos términos o ponga en riesgo a otras cuentas, avisándote el motivo salvo que la ley lo impida.</li>
      </ul>

      <h2>8. Propiedad</h2>
      <p>
        {r.marca}, su código, diseño y marca son de su titular. Tus datos y tus comprobantes son tuyos: no adquirimos ningún derecho sobre ellos
        más allá de lo necesario para darte el servicio.
      </p>

      <h2>9. Cambios a estos términos</h2>
      <p>
        Si cambian en algo de fondo te los pediremos aceptar de nuevo al entrar. Si no los aceptas puedes cerrar tu cuenta y, en su caso, pedir el
        reembolso proporcional de los timbres no usados.
      </p>

      <h2>10. Ley aplicable</h2>
      <p>
        Estos términos se rigen por las leyes federales de México. Para cualquier controversia, las partes se someten a los tribunales competentes
        del domicilio del titular de {r.marca}, sin perjuicio de que como consumidor puedas acudir a la Procuraduría Federal del Consumidor (PROFECO).
        Para avisos y notificaciones escríbenos a {r.correo}; a ti te avisamos al correo de tu cuenta.
      </p>
    </PaginaLegal>
  );
}
