import type { Metadata } from "next";

export const metadata: Metadata = { title: "Entrar · Timbra", description: "Entra a tu cuenta de Timbra." };

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
