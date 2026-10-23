"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";
import { Pause, Play, SkipBack, SkipForward } from "lucide-react";
import { CLIENT_ID, getToken, handleRedirect, login } from "@/lib/spotify";
import { Button } from "@/components/ui/button";

type Track = { title: string; artist: string; art: string; paused: boolean };
const DEMO: Track = { title: "Nada tocando", artist: "Conecte o Spotify (Premium)", art: "", paused: true };

/* Tipos mínimos do Web Playback SDK, para não depender de @types externos. */
type SpPlayer = {
  connect(): Promise<boolean>; disconnect(): void; togglePlay(): Promise<void>; previousTrack(): Promise<void>; nextTrack(): Promise<void>;
  addListener(ev: "player_state_changed", cb: (s: SpState | null) => void): void;
};
type SpState = { paused: boolean; track_window: { current_track: { name: string; artists: { name: string }[]; album: { images: { url: string }[] } } } };
declare global { interface Window { Spotify?: { Player: new (o: { name: string; getOAuthToken: (cb: (t: string) => void) => void; volume: number }) => SpPlayer }; onSpotifyWebPlaybackSDKReady?: () => void } }

export function Player() {
  const [track, setTrack] = useState<Track>(DEMO);
  const [connected, setConnected] = useState(false);
  const player = useRef<SpPlayer | null>(null);

  const start = useCallback(async () => {
    if (!(await getToken())) return;
    const boot = () => {
      const p = new window.Spotify!.Player({ name: "HIC OS", volume: 0.5, getOAuthToken: async (cb) => cb((await getToken()) ?? "") });
      p.addListener("player_state_changed", (s) => {
        if (!s) return;
        const c = s.track_window.current_track;
        setTrack({ title: c.name, artist: c.artists.map((a) => a.name).join(", "), art: c.album.images[0]?.url ?? "", paused: s.paused });
      });
      p.connect().then(setConnected);
      player.current = p;
    };
    if (window.Spotify) return boot();
    window.onSpotifyWebPlaybackSDKReady = boot;
    const sc = document.createElement("script"); sc.src = "https://sdk.scdn.co/spotify-player.js"; document.body.appendChild(sc);
  }, []);

  useEffect(() => { handleRedirect().then(start).catch(() => {}); return () => player.current?.disconnect(); }, [start]);

  return (
    <motion.header
      initial={{ y: -24, opacity: 0 }} animate={{ y: 0, opacity: 1 }} transition={{ type: "spring", stiffness: 160, damping: 22 }}
      className="sticky top-[env(safe-area-inset-top)] z-20 mx-auto mt-3 flex max-w-[1100px] items-center gap-3 rounded-full border border-[var(--glass-line)] bg-[var(--glass)] p-2 pr-3 shadow-[0_18px_50px_-24px_rgba(0,0,0,.8),inset_0_1px_0_rgba(255,255,255,.08)] backdrop-blur-2xl backdrop-saturate-150"
      aria-label="Spotify"
    >
      <div className="size-10 flex-none rounded-full bg-gradient-to-br from-[var(--work)] to-[var(--dark)] bg-cover" style={track.art ? { backgroundImage: `url(${track.art})` } : undefined} />
      <div className="min-w-0 flex-1">
        <div className="truncate text-[13px] font-semibold">{track.title}</div>
        <div className="truncate font-mono text-[11px] text-[var(--mute)]">{track.artist}</div>
      </div>
      {connected ? (
        <div className="flex flex-none gap-1">
          <Button variant="ghost" size="icon" aria-label="Anterior" onClick={() => player.current?.previousTrack()}><SkipBack size={16} /></Button>
          <Button variant="glass" size="icon" aria-label={track.paused ? "Tocar" : "Pausar"} onClick={() => player.current?.togglePlay()}>{track.paused ? <Play size={16} /> : <Pause size={16} />}</Button>
          <Button variant="ghost" size="icon" aria-label="Próxima" onClick={() => player.current?.nextTrack()}><SkipForward size={16} /></Button>
        </div>
      ) : (
        <Button variant="glass" disabled={!CLIENT_ID} onClick={login} title={CLIENT_ID ? "" : "Defina NEXT_PUBLIC_SPOTIFY_CLIENT_ID"}>Conectar Spotify</Button>
      )}
    </motion.header>
  );
}
