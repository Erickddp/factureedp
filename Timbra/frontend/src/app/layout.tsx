import type { Metadata } from "next";
import { Schibsted_Grotesk } from "next/font/google";
import { Toaster } from "sonner";
import "./globals.css";

const schibsted = Schibsted_Grotesk({ subsets: ["latin"], variable: "--font-schibsted", display: "swap" });

export const metadata: Metadata = { title: "Timbra · EDDP", description: "Facturación CFDI 4.0" };

// Tema antes de pintar (sin parpadeo): "claro" | "oscuro" | sin valor = el del sistema
const TEMA = `try{var t=localStorage.getItem("timbra_tema");if(t==="oscuro")document.documentElement.dataset.theme="dark";else if(t==="claro")document.documentElement.dataset.theme="light"}catch(e){}`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="es-MX" className={schibsted.variable} suppressHydrationWarning>
      <head><script dangerouslySetInnerHTML={{ __html: TEMA }} /></head>
      <body className="font-sans min-h-screen">
        {children}
        <Toaster position="bottom-right" richColors closeButton />
      </body>
    </html>
  );
}
