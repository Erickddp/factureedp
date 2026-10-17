import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Timbra · Facturación CFDI 4.0 para despachos y negocios",
  description: "Timbra valida RFC, régimen, uso del CFDI y claves SAT antes de timbrar, convierte tu tabla de Excel en un lote de facturas y trae cobranza, pagos y nómina. Pagas sólo los timbres que usas.",
  openGraph: { title: "Timbra · Facturación CFDI 4.0", description: "Factura en segundos y no gastes timbres en errores.", type: "website", locale: "es_MX", siteName: "Timbra" },
};

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
