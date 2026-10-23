# HIC OS · interface

Painel de foco em Next.js 15, TypeScript, Tailwind v4, Framer Motion, React Three Fiber e componentes no estilo shadcn/ui.
Sem o daemon, roda em **modo demo** com dados fictícios (é o que a demo na Vercel mostra).

```bash
cd web
npm install
npm run dev        # http://127.0.0.1:3000
```

## Dados

A interface lê `GET /api/state`, validado com zod em `src/lib/state.ts`. Quando existe um daemon respondendo nessa rota
(hoje o `hic.py`, servindo na porta 7777), ela mostra os dados reais; senão cai no demo. O contrato é a fronteira entre
interface e daemon, então o daemon pode ser reescrito sem mexer aqui.

## Temas

Um tema é um bloco de variáveis CSS em `src/app/globals.css` (`[data-theme="ember"]`, `[data-theme="mono"]`).
Para criar um, copie um bloco, troque os valores e adicione a opção no seletor do rodapé.
Previstos: japonês, clean, techno, cyberpunk.

## Layouts

- `painel`: moldura, trilho, três cards, fita do dia e fila de triagem em leque.
- `lâmpada`: um objeto 3D que muda de cor com o estado e acelera o pulso conforme a cobrança sobe.

## Spotify

Login por PKCE direto no navegador, sem segredo e sem backend. Copie `.env.example` para `.env.local`, preencha o
`NEXT_PUBLIC_SPOTIFY_CLIENT_ID` e cadastre o Redirect URI. O player (Web Playback SDK) exige conta **Premium**.

## Deploy na Vercel

Importe o repositório e defina **Root Directory = `web`**. Para o login do Spotify funcionar na demo, defina a variável
`NEXT_PUBLIC_SPOTIFY_CLIENT_ID` no projeto e cadastre a URL da Vercel como Redirect URI.
