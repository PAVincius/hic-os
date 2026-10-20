import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = { title: "HIC OS", description: "Um painel de foco para quem trabalha em frente ao computador. Código aberto." };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="pt-BR" data-theme="ember">
      <head>
        <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Archivo:wdth,wght@75..100,400..800&family=IBM+Plex+Mono:wght@400;500&display=swap" />
      </head>
      <body>{children}</body>
    </html>
  );
}
