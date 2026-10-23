/** Spotify via PKCE, só no navegador. Sem segredo, sem backend. Defina NEXT_PUBLIC_SPOTIFY_CLIENT_ID. */
export const CLIENT_ID = process.env.NEXT_PUBLIC_SPOTIFY_CLIENT_ID ?? "";
const SCOPES = "streaming user-read-email user-read-private user-read-playback-state user-modify-playback-state";
const K = { verifier: "hic.sp.verifier", token: "hic.sp.token" } as const;

type Token = { access: string; refresh: string; exp: number };

const b64 = (buf: ArrayBuffer) => btoa(String.fromCharCode(...new Uint8Array(buf))).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
const redirect = () => `${window.location.origin}/`;

export async function login() {
  const verifier = b64(crypto.getRandomValues(new Uint8Array(48)).buffer);
  localStorage.setItem(K.verifier, verifier);
  const challenge = b64(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(verifier)));
  const q = new URLSearchParams({ response_type: "code", client_id: CLIENT_ID, scope: SCOPES, redirect_uri: redirect(), code_challenge_method: "S256", code_challenge: challenge });
  window.location.href = `https://accounts.spotify.com/authorize?${q}`;
}

async function tokenRequest(body: Record<string, string>): Promise<Token> {
  const r = await fetch("https://accounts.spotify.com/api/token", { method: "POST", headers: { "Content-Type": "application/x-www-form-urlencoded" }, body: new URLSearchParams({ client_id: CLIENT_ID, ...body }) });
  if (!r.ok) throw new Error("spotify token " + r.status);
  const j = await r.json();
  const t: Token = { access: j.access_token, refresh: j.refresh_token ?? body.refresh_token ?? "", exp: Date.now() + j.expires_in * 1000 - 30_000 };
  localStorage.setItem(K.token, JSON.stringify(t));
  return t;
}

/** Chame ao carregar: troca ?code= por token e limpa a URL. */
export async function handleRedirect() {
  const code = new URLSearchParams(window.location.search).get("code");
  const verifier = localStorage.getItem(K.verifier);
  if (!code || !verifier) return;
  await tokenRequest({ grant_type: "authorization_code", code, redirect_uri: redirect(), code_verifier: verifier });
  localStorage.removeItem(K.verifier);
  window.history.replaceState({}, "", "/");
}

export async function getToken(): Promise<string | null> {
  try {
    const raw = localStorage.getItem(K.token);
    if (!raw) return null;
    let t: Token = JSON.parse(raw);
    if (Date.now() >= t.exp && t.refresh) t = await tokenRequest({ grant_type: "refresh_token", refresh_token: t.refresh });
    return t.access;
  } catch { return null; }
}

export const logout = () => localStorage.removeItem(K.token);
