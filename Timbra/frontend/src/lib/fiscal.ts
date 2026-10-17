/**
 * Guía fiscal de facturación (página /legal/fiscal). Cada punto lleva su fuente. Es orientación general, no asesoría.
 * REVISION: la última vez que se revisó contra la normativa. Los números de regla de la Resolución Miscelánea Fiscal (RMF)
 * cambian cada año: antes de cambiar `VALIDADO` a true, un contador o abogado debe confirmarlos con la RMF y el Anexo 20 vigentes.
 */
export const REVISION = "17 de octubre de 2026";
export const VALIDADO = false;

export type Punto = { t: string; r: string; f: string };
export type Grupo = { titulo: string; puntos: Punto[] };

export const GUIA: Grupo[] = [
  {
    titulo: "Comprobantes (CFDI 4.0)",
    puntos: [
      { t: "Qué lleva una factura",
        r: "Debe cumplir los requisitos del Código Fiscal y la estructura del CFDI 4.0. Los datos del receptor deben coincidir con su Constancia de Situación Fiscal: RFC, nombre o razón social (sin régimen societario), código postal del domicilio fiscal, régimen fiscal y uso del CFDI. Si no coinciden, el PAC rechaza el timbrado.",
        f: "CFF arts. 29 y 29-A · Anexo 20 de la RMF (CFDI 4.0)" },
      { t: "Público en general y extranjeros",
        r: "Para ventas a público en general se usa el RFC XAXX010101000, el nombre PÚBLICO EN GENERAL, régimen 616 y uso S01, y la factura global con su periodicidad, mes y año. Para extranjeros sin RFC, XEXX010101000.",
        f: "Anexo 20 de la RMF · reglas de factura global de la RMF vigente" },
      { t: "Pago de contado o en parcialidades (PUE / PPD)",
        r: "PUE: el pago se hace en una sola exhibición al emitir. PPD: pago diferido o en parcialidades, y por cada pago se emite un complemento de pago, normalmente a más tardar el quinto día natural del mes siguiente al pago.",
        f: "RMF vigente, reglas del complemento para recepción de pagos · Anexo 20" },
      { t: "Cancelar una factura",
        r: "Se cancela indicando un motivo (01 con relación, 02 sin relación, 03 operación no realizada, 04 global nominativa). En la mayoría de los casos el receptor debe aceptar la cancelación en su buzón tributario; si no responde en tres días hábiles se tiene por aceptada. Un timbre usado no se recupera aunque cancelas. Consulta el plazo máximo para cancelar en la regla vigente.",
        f: "CFF art. 29 · reglas de cancelación de la RMF vigente" },
      { t: "Cuánto tiempo conservar",
        r: "La contabilidad y los comprobantes se conservan 5 años, y más si hay una revisión de la autoridad en curso. Tus CFDI siempre se pueden volver a bajar del SAT.",
        f: "CFF art. 30" },
      { t: "Nómina",
        r: "Quien paga sueldos retiene el ISR y expide un CFDI de nómina por cada pago, con el complemento de nómina y los datos del empleado (RFC, CURP, número de seguridad social, régimen).",
        f: "LISR art. 99 · complemento de nómina del Anexo 20" },
    ],
  },
  {
    titulo: "Impuestos en la factura",
    puntos: [
      { t: "Tasas de IVA",
        r: "16% general, 0% para lo que la ley señala (por ejemplo ciertos alimentos y medicinas, exportación) y exento para lo que la ley exenta. En la región fronteriza puede aplicar 8% si estás inscrito en el padrón del estímulo y el decreto sigue vigente: confirma su vigencia en el Diario Oficial.",
        f: "LIVA arts. 1, 2-A, 9, 15, 20 y 25 · decreto de estímulos fiscales de la región fronteriza" },
      { t: "Retenciones",
        r: "Cuando una persona moral recibe servicios personales independientes o arrendamiento de una persona física, retiene dos terceras partes del IVA (10.6667% sobre el 16%; 5.3333% sobre el 8%) y, en honorarios, el 10% de ISR.",
        f: "LIVA art. 1-A · LISR art. 106" },
      { t: "Gastos deducibles",
        r: "Para deducir un gasto debe ser estrictamente indispensable, estar amparado con un CFDI a tu nombre y estar efectivamente pagado. Los pagos de más de $2,000 deben hacerse con transferencia, cheque o tarjeta, no en efectivo.",
        f: "LISR arts. 27 y 28" },
    ],
  },
  {
    titulo: "e.firma, sello digital y PAC",
    puntos: [
      { t: "e.firma",
        r: "Identifica a su titular, que responde de su uso. Es personal: si la usas para descargar XML de un cliente, necesitas su autorización por escrito. Timbra la usa sólo en memoria mientras dura la descarga y no la guarda.",
        f: "CFF arts. 17-D y 17-E" },
      { t: "Certificado de sello digital (CSD)",
        r: "Es lo que firma tus facturas; no es la e.firma. El SAT puede restringirlo temporalmente o dejarlo sin efectos, y entonces no puedes timbrar hasta aclararlo.",
        f: "CFF arts. 17-D, 17-H y 17-H Bis" },
      { t: "Qué es un PAC",
        r: "El proveedor autorizado por el SAT que valida y timbra el comprobante. Timbra arma tu factura y la envía a un PAC; Timbra no es el SAT ni un PAC.",
        f: "CFF art. 29, fracción IV" },
    ],
  },
];
