#!/usr/bin/env python3
"""
HIC OS — sistema de disciplina de foco para macOS.
Autor: escrito para Nebuloz (Vinicius Prates Araujo).

Um unico arquivo. Sem dependencias externas. Roda com o python3 do sistema.

Comandos:
    hic tick        # 1 amostra (chamado pelo launchd a cada 60s)
    hic status      # resumo do dia no terminal
    hic dash        # abre o mini-app no navegador
    hic serve       # sobe o servidor do dashboard (launchd cuida disso)
    hic plan        # ritual matinal 3/3/3
    hic frog [min]  # inicia um bloco de deep work (default 90min)
    hic done        # encerra o bloco atual
    hic pause [min] # silencia o monitor (default 30min)
    hic resume      # religa o monitor
    hic focus on|off
    hic doctor      # testa todas as permissoes do macOS
    hic report [n]  # ultimos n dias
"""

import datetime as dt
import json
import os
import re
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HOME = Path.home()
ROOT = HOME / ".hic"
CFG_PATH = ROOT / "config.json"
STATE_PATH = ROOT / "state.json"
PLAN_DIR = ROOT / "plans"
LOG_DIR = ROOT / "logs"

DEFAULT_CFG = {
    "work_days": [1, 2, 3, 4, 5],
    # ATENCAO: work_start/work_end sao a janela de COBRANCA, nao de contagem.
    # Com count_all_day ligado, todo minuto de trabalho conta — inclusive 3h da
    # manha. O que muda aqui e apenas onde o sistema tem direito de te cobrar.
    "work_start": "07:30",
    "work_end": "20:00",
    "count_all_day": True,
    # Empurrao invertido: depois destes horarios o sistema para de te empurrar
    # PARA o trabalho e passa a te empurrar para FORA dele.
    "late_nudge_enabled": True,
    "late_nudge_1": "22:00",
    "late_nudge_2": "23:00",
    "late_nudge_madrugada_end": "05:00",
    # --- modulo fim de semana: teto com parada dura ---
    # Nao e uma copia do dia util. Dia util protege o tempo do empregador de
    # deriva; fim de semana protege VOCE do proprio excesso. Por isso o alvo e
    # um teto, nao um piso: bateu, o sistema manda parar — e escala se insistir.
    "weekend_enabled": True,
    "weekend_days": [6, 7],
    "weekend_start": "09:00",
    "weekend_end": "20:00",
    "weekend_target_min": 180,
    "weekend_nag_after_min": 30,
    # Sabado e domingo tem TETO, nao piso. Cobrar para COMECAR no fim de
    # semana e o oposto do que a banda existe para fazer. Com isso desligado
    # o sistema NUNCA pede que voce va trabalhar no sabado — e continua
    # mandando parar se voce passar do teto. Sao dois eixos, nao um.
    "weekend_nag_enabled": False,
    "weekend_prompt_time": "10:00",
    "weekend_overrun_1_min": 60,
    "weekend_overrun_2_min": 120,
    "lunch_start": "12:00",
    "lunch_end": "14:00",
    "nag_after_min": 20,
    "escalate_2_after_min": 25,
    "escalate_3_after_min": 30,
    "renag_every_min": 10,
    "block_nag_after_min": 5,
    "distraction_grace_sec": 90,
    "away_after_min": 45,
    # A meta virou BANDA. Piso e teto, nao so piso: um numero que voce bate
    # 2,7x todo dia parou de informar qualquer coisa. Verde dentro, ambar
    # abaixo, vermelho acima — e o streak conta dias DENTRO.
    "band_min_min": 300,
    "band_max_min": 480,
    "streak_target_min": 180,
    "daily_target_min": 240,
    "pomodoro_chime_every_min": 25,
    "work_apps": [
        "Cursor", "Figma", "Brave Browser", "Ghostty", "iTerm2", "iTerm",
        "Terminal", "Warp", "Code", "Visual Studio Code", "Zed", "Xcode",
        "Windsurf", "Antigravity", "Claude", "Docker Desktop", "TablePlus",
        "Postico 2", "pgAdmin 4", "Obsidian", "Linear", "Notion", "Preview",
        "Numbers",
        # JVM: o macOS reporta varias IDEs da JetBrains simplesmente como "java"
        "java", "IntelliJ IDEA", "DataGrip", "PyCharm", "WebStorm",
        "Android Studio", "Rider", "GoLand",
        # comunicacao de trabalho — o app, nao so o dominio
        "Slack", "WhatsApp", "Discord", "Microsoft Teams", "zoom.us", "Gather",
        # utilitarios
        "Wispr Flow", "Postman", "Insomnia", "Sequel Ace", "Rectangle",
        "GitHub Desktop", "GitKraken", "Fork", "Tower",
        "Raycast", "Notion Calendar", "Numbers", "Keynote", "Pages"
    ],
    # Apps que sao distracao explicita — cobram rapido, como dominio bloqueado.
    "blocked_apps": [
        "Steam", "Epic Games Launcher", "Battle.net", "Minecraft",
        "Netflix", "Prime Video", "Disney+", "TV", "Photo Booth",
        "Instagram", "Twitter", "X"
    ],
    "neutral_apps": ["Spotify", "Music", "Calendar", "Reminders",
                     "System Settings", "Ajustes do Sistema", "Finder",
                     "Activity Monitor", "Monitor de Atividade",
                     # auxiliares do macOS que piscam em primeiro plano por um
                     # minuto e so poluem a fila de triagem
                     "UserNotificationCenter", "System Events",
                     "Eventos do Sistema", "Nudge", "Dock", "SystemUIServer",
                     "Control Center", "Central de Controle", "Spotlight",
                     "CoreServicesUIAgent", "universalAccessAuthWarn",
                     "Atalhos", "Shortcuts", "Notification Centre"],
    # Allowlist. Semeada com o que o daemon realmente viu no Brave dele mais o
    # obvio para um tech lead de MLOps em saude. Casa por sufixo: "google.com"
    # NAO esta aqui de proposito — so os subdominios de trabalho entram.
    "work_domains": [
        # dev e infra
        "github.com", "gitlab.com", "bitbucket.org", "stackoverflow.com",
        "stackexchange.com", "localhost", "127.0.0.1", "0.0.0.0",
        "vercel.com", "netlify.com", "supabase.com", "railway.app",
        "render.com", "neon.tech", "fly.io", "planetscale.com",
        "docker.com", "kubernetes.io", "terraform.io", "hashicorp.com",
        "npmjs.com", "pypi.org", "crates.io", "pkg.go.dev", "readthedocs.io",
        "developer.mozilla.org", "web.dev", "caniuse.com", "regex101.com",
        "excalidraw.com", "draw.io", "sentry.io", "datadoghq.com",
        # nuvem
        "cloud.google.com", "console.cloud.google.com", "aws.amazon.com",
        "console.aws.amazon.com", "portal.azure.com", "azure.microsoft.com",
        # ML / pesquisa
        "huggingface.co", "arxiv.org", "paperswithcode.com", "paperswithcode.co",
        "kaggle.com", "wandb.ai", "langfuse.com", "modal.com", "replicate.com",
        "ollama.com", "pytorch.org", "tensorflow.org", "scikit-learn.org",
        "numpy.org", "pandas.pydata.org", "deep-ml.com", "distill.pub",
        "openreview.net", "semanticscholar.org", "colab.research.google.com",
        "mlflow.org", "dvc.org", "ray.io", "vllm.ai", "langchain.com",
        "llamaindex.ai", "crewai.com", "weaviate.io", "pinecone.io", "qdrant.tech",
        # IA
        "claude.ai", "anthropic.com", "chatgpt.com", "openai.com",
        "gemini.google.com", "aistudio.google.com", "perplexity.ai",
        "cursor.com", "cursor.sh", "windsurf.com", "v0.dev", "bolt.new",
        # ferramentas de trabalho (nao sao "tech", sao trabalho)
        "mail.google.com", "meet.google.com", "calendar.google.com",
        "docs.google.com", "drive.google.com", "sheets.google.com",
        "slides.google.com", "chat.google.com", "groups.google.com",
        "linear.app", "notion.so", "figma.com", "slack.com", "discord.com",
        "atlassian.net", "miro.com", "loom.com", "zoom.us",
        "teams.microsoft.com", "calendly.com",
        # carreira (LinkedIn e a sua excecao) e preparo tecnico
        "linkedin.com", "leetcode.com", "neetcode.io", "hackerrank.com",
        "levels.fyi",
        # o trabalho dele: escritorio virtual do time e os apps da MaCall
        "gather.town", "macall.com.br", "search.brave.com", "duckduckgo.com",
        # admin de trabalho no Brasil
        "gov.br", "registrocivil.org.br", "fazenda.gov.br", "bcb.gov.br",
        # saude — o dominio que voce quer dominar
        "datasus.gov.br", "saude.gov.br", "anvisa.gov.br", "cfm.org.br",
        "ncbi.nlm.nih.gov", "who.int", "hl7.org", "fhir.org", "scielo.br"
    ],
    "blocked_domains": [
        # redes e video
        "youtube.com", "x.com", "twitter.com", "instagram.com", "reddit.com",
        "twitch.tv", "tiktok.com", "facebook.com", "pinterest.com",
        "snapchat.com", "tumblr.com", "kwai.com",
        "netflix.com", "primevideo.com", "disneyplus.com", "max.com",
        "hbomax.com", "crunchyroll.com", "globoplay.globo.com", "9gag.com",
        # noticias e portais
        "globo.com", "uol.com.br", "r7.com", "terra.com.br", "ig.com.br",
        "estadao.com.br", "cnnbrasil.com.br", "metropoles.com",
        # compras
        "mercadolivre.com.br", "amazon.com.br", "kabum.com.br",
        "aliexpress.com", "shopee.com.br", "magazineluiza.com.br", "temu.com",
        "americanas.com.br", "olx.com.br", "enjoei.com.br",
        # games e apostas
        "store.steampowered.com", "steamcommunity.com", "epicgames.com",
        "xbox.com", "playstation.com", "bet365.com", "betano.com", "blaze.com",
        # delivery e viagem
        "ifood.com.br", "rappi.com.br", "booking.com", "airbnb.com",
        "decolar.com", "latamairlines.com",
        # estudo da faculdade — voce marcou como nao-trabalho no expediente
        "ufg.br"
    ],
    # Dominios privados: NAO sao registrados. O host nem chega ao log, nao
    # entram na triagem, nao aparecem em lugar nenhum do dashboard e nao
    # geram cobranca. O sistema simplesmente nao olha.
    "private_domains": [
        "pornhub.com", "xvideos.com", "xnxx.com", "redtube.com",
        "youporn.com", "xhamster.com", "spankbang.com", "eporner.com",
        "porntrex.com", "tnaflix.com", "txxx.com", "hqporner.com",
        "brazzers.com", "onlyfans.com", "fansly.com", "privacy.com.br",
        "chaturbate.com", "stripchat.com", "bongacams.com", "cam4.com",
        "livejasmin.com", "fapello.com", "erome.com", "rule34.xxx",
        "nhentai.net", "e-hentai.org", "hanime.tv", "redgifs.com"
    ],
    # Sufixos e padroes que tambem entram no modo privado, sem lista nominal.
    "private_patterns": [r"\.xxx$", r"\.porn$", r"\.sex$", r"\.adult$",
                         r"porno", r"pornô"],
    # O que fazer com dominio que nunca foi visto: "log" registra como UNKNOWN
    # sem cobrar (voce tria no dashboard), "block" cobra, "allow" libera.
    "unknown_domain_policy": "log",
    "unknown_app_policy": "log",
    # Registra tambem fora da janela, como OFFHOURS. Nao cobra, nao conta como
    # foco — mas guarda o dado bruto. Assim, se voce mudar o horario depois,
    # 'hic reclassify' recupera o passado em vez de perde-lo para sempre.
    "log_offhours": True,
    "browser_app": "Brave Browser",
    "focus_shortcut_on": "HIC Focus On",
    "focus_shortcut_off": "HIC Focus Off",
    "voice": "",
    "dashboard_port": 7777,
    "plan_prompt_time": "07:30",
    "messages": {
        "l1": [
            "20 minutos fora do trabalho. Volta pro Cursor.",
            "Parkinson esta te comendo. Volta pro bloco.",
            "Fora de foco ha 20min. Qual era a tarefa mesmo?"
        ],
        "l2": [
            "25 minutos. Isso ja e meio pomodoro jogado fora.",
            "Segunda chamada. Fecha a aba e volta.",
            "Voce disse que queria ser referencia mundial. Nao e assim."
        ],
        "l3": [
            "30 MINUTOS FORA. MODO FOCO LIGADO. VOLTA PRO TRABALHO.",
            "TRINTA MINUTOS. Ativando Focus. Sem desculpa.",
            "Isso aqui e o terceiro aviso. O dia esta escoando."
        ],
        "distraction": [
            "Isso e distracao pura. Fecha.",
            "Site bloqueado durante o horario de trabalho.",
            "Voce abriu isso no automatico. Fecha a aba."
        ]
    }
}

# ---------------------------------------------------------------- utilidades


def sh(args, timeout=8):
    """Roda um comando e devolve stdout limpo, ou string vazia."""
    try:
        out = subprocess.run(
            args, capture_output=True, text=True, timeout=timeout
        )
        return out.stdout.strip()
    except Exception:
        return ""


def osa(script, timeout=8):
    return sh(["osascript", "-e", script], timeout=timeout)


def detach(args):
    """Dispara um comando sem bloquear o tick."""
    try:
        subprocess.Popen(
            args,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except Exception:
        pass


def ensure_dirs():
    for d in (ROOT, LOG_DIR, PLAN_DIR, ROOT / "bin"):
        d.mkdir(parents=True, exist_ok=True)


def load_cfg():
    ensure_dirs()
    cfg = dict(DEFAULT_CFG)
    if CFG_PATH.exists():
        try:
            user = json.loads(CFG_PATH.read_text())
            cfg.update(user)
        except Exception:
            pass
    else:
        CFG_PATH.write_text(json.dumps(DEFAULT_CFG, indent=2, ensure_ascii=False))
    return cfg


def load_state():
    ensure_dirs()
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text())
        except Exception:
            pass
    return {}


def save_state(st):
    ensure_dirs()
    tmp = STATE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(st, indent=2, ensure_ascii=False))
    tmp.replace(STATE_PATH)


def today_key(now=None):
    now = now or dt.datetime.now()
    return now.strftime("%Y-%m-%d")


def log_path(now=None):
    return LOG_DIR / (today_key(now) + ".jsonl")


def hhmm_to_min(s):
    try:
        h, m = s.split(":")
        return int(h) * 60 + int(m)
    except Exception:
        return 0


def pick(seq, salt):
    if not seq:
        return ""
    return seq[salt % len(seq)]


# ------------------------------------------------------------ sondas macOS


# Alguns apps trazem marcas invisiveis no nome (o WhatsApp vem com U+200E na
# frente). Sem normalizar, "WhatsApp" nunca casa com a lista e vira OFF.
_INVISIVEIS = dict.fromkeys(
    map(ord, "​‌‍‎‏‪‫‬‭‮﻿"),
    None)


def norm_app(nome):
    return (nome or "").translate(_INVISIVEIS).strip()


def app_matches(app, lista):
    alvo = norm_app(app).lower()
    if not alvo:
        return False
    return any(norm_app(x).lower() == alvo for x in (lista or []))


def app_class(app, cfg):
    """Mesma logica de tres classes dos dominios, um nivel acima.
    App que ninguem classificou NAO e 'fora do trabalho' — e 'nao sei'."""
    if app_matches(app, cfg.get("work_apps")):
        return "WORK"
    if app_matches(app, cfg.get("blocked_apps")):
        return "DIST"
    if app_matches(app, cfg.get("neutral_apps")):
        return "NEUTRAL"
    politica = cfg.get("unknown_app_policy", "log")
    if politica == "block":
        return "OFF"
    if politica == "allow":
        return "WORK"
    return "UNKNOWN"


def frontmost_app():
    """Nome do app em primeiro plano. lsappinfo primeiro (sem permissao),
    System Events como fallback (precisa de Acessibilidade)."""
    asn = sh(["lsappinfo", "front"], timeout=4)
    if asn:
        info = sh(["lsappinfo", "info", "-only", "name", asn], timeout=4)
        m = re.search(r'"LSDisplayName"\s*=\s*"([^"]+)"', info)
        if m:
            return norm_app(m.group(1))
    name = osa(
        'tell application "System Events" to get name of first '
        "application process whose frontmost is true",
        timeout=5,
    )
    return norm_app(name)


def idle_seconds():
    """Segundos desde o ultimo input de teclado/mouse."""
    out = sh(["ioreg", "-c", "IOHIDSystem"], timeout=6)
    m = re.search(r'"HIDIdleTime"\s*=\s*(\d+)', out)
    if not m:
        return 0
    return int(int(m.group(1)) / 1_000_000_000)


def browser_host(cfg):
    """Host da aba ativa do navegador. Precisa de permissao de Automacao."""
    app = cfg.get("browser_app", "Brave Browser")
    url = osa(
        'tell application "%s" to get URL of active tab of front window' % app,
        timeout=6,
    )
    if not url:
        return ""
    m = re.match(r"https?://([^/:]+)", url)
    if not m:
        return ""
    return m.group(1).lower().lstrip("www.")


# Apps que o macOS reporta em primeiro plano quando a tela esta travada ou
# em descanso. Sao sinal inequivoco de "nao esta na maquina".
LOCK_APPS = {"loginwindow", "ScreenSaverEngine", "LockScreen", "SecurityAgent"}


def screen_locked():
    out = sh(["ioreg", "-n", "Root", "-d1", "-r"], timeout=6)
    return '"CGSSessionScreenIsLocked" = Yes' in out


# ------------------------------------------------------------------- avisos


def notify(title, msg, sound="Submarine"):
    safe_t = title.replace('"', "'")
    safe_m = msg.replace('"', "'")
    tn = sh(["which", "terminal-notifier"], timeout=3)
    if tn:
        detach([tn, "-title", title, "-message", msg, "-sound", sound,
                "-group", "hic"])
        return
    detach([
        "osascript", "-e",
        'display notification "%s" with title "%s" sound name "%s"'
        % (safe_m, safe_t, sound),
    ])


def speak(msg, cfg):
    voice = cfg.get("voice") or ""
    args = ["say"]
    if voice:
        args += ["-v", voice]
    args.append(msg)
    detach(args)


def modal(title, msg, button="Voltando agora"):
    safe_t = title.replace('"', "'")
    safe_m = msg.replace('"', "'")
    script = (
        'tell application "System Events"\n'
        "  activate\n"
        '  display dialog "%s" with title "%s" buttons {"%s"} '
        'default button 1 with icon caution giving up after 45\n'
        "end tell" % (safe_m, safe_t, button)
    )
    detach(["osascript", "-e", script])


FOCUS_LOG = ROOT / "focus.jsonl"


def set_focus(cfg, on, source="?"):
    """Roda o atalho e SEMPRE deixa evidencia em focus.jsonl.

    Arquivo proprio (nao state.json) porque o tick segura um `st` em memoria
    e sobrescreveria qualquer chave gravada aqui no meio do caminho.
    """
    name = cfg["focus_shortcut_on"] if on else cfg["focus_shortcut_off"]
    rec = {"ts": dt.datetime.now().isoformat(timespec="seconds"),
           "on": bool(on), "shortcut": name, "source": source}
    try:
        r = subprocess.run(["shortcuts", "run", name],
                           capture_output=True, text=True, timeout=15)
        rec["rc"] = r.returncode
        if r.returncode != 0:
            rec["err"] = (r.stderr or r.stdout or "").strip()[:200]
    except Exception as e:
        rec["rc"] = -1
        rec["err"] = ("%s: %s" % (type(e).__name__, e))[:200]
    rec["ok"] = rec["rc"] == 0
    try:
        ensure_dirs()
        with FOCUS_LOG.open("a") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        pass
    return rec["ok"]


def focus_evidence(n=200):
    """Ultimas chamadas de Focus: (total, oks, ultimo_on, ultimo_off)."""
    try:
        linhas = FOCUS_LOG.read_text().splitlines()[-n:]
    except Exception:
        return 0, 0, None, None
    recs = []
    for l in linhas:
        try:
            recs.append(json.loads(l))
        except Exception:
            pass
    ult_on = next((r for r in reversed(recs) if r.get("on")), None)
    ult_off = next((r for r in reversed(recs) if not r.get("on")), None)
    return len(recs), sum(1 for r in recs if r.get("ok")), ult_on, ult_off


# --------------------------------------------------------------- classificar


def classify_from(app, host, idle, cfg, locked=False, fora_da_janela=False):
    """Pura: decide a classe a partir de (app, host, idle). Usada tanto pelo
    tick ao vivo quanto pelo 'hic reclassify', para que os dois NUNCA divirjam.
    Classes: WORK, DIST, OFF, AWAY, LOCKED, NEUTRAL, BLIND, UNKNOWN, OFFHOURS."""
    app = norm_app(app)
    if fora_da_janela:
        # Guarda o que estava acontecendo sem julgar. Se a janela mudar,
        # o reclassify converte isto em WORK retroativamente.
        return "OFFHOURS", app, host

    # Tela travada e sinal inequivoco: ele nao esta na maquina. Nao precisa
    # esperar os 45 min de ociosidade — cobrar uma tela de bloqueio e o
    # falso positivo mais caro que existe.
    if app in LOCK_APPS or locked:
        return "LOCKED", app, ""
    if idle >= cfg["away_after_min"] * 60:
        return "AWAY", app, ""
    if not app:
        # Sonda cega. Sem permissao de Acessibilidade o macOS nao devolve o app
        # em primeiro plano, e a string vem vazia. Isso NAO significa "fora do
        # trabalho" — significa "nao sei".
        return "BLIND", "", ""

    if app == norm_app(cfg.get("browser_app")):
        if not host:
            # Sem URL (Automacao ausente, ou janela sem aba): nao penaliza.
            return "WORK", app, ""
        if host_privado(host, cfg):
            # O host e descartado aqui e nunca chega ao log.
            return "PRIVATE", app, ""
        if host_matches(host, cfg.get("blocked_domains", [])):
            return "DIST", app, host
        if host_matches(host, cfg.get("work_domains", [])):
            return "WORK", app, host
        politica = cfg.get("unknown_domain_policy", "log")
        if politica == "block":
            return "DIST", app, host
        if politica == "allow":
            return "WORK", app, host
        return "UNKNOWN", app, host

    return app_class(app, cfg), app, ""


def classify(cfg):
    """Le as sondas do macOS e delega a decisao para classify_from."""
    idle = idle_seconds()
    app = frontmost_app()
    host = ""
    if app == norm_app(cfg.get("browser_app")):
        host = browser_host(cfg)
    travada = (not app) and screen_locked()
    k, app, host = classify_from(app, host, idle, cfg, locked=travada)
    return k, app, host, idle


def cmd_scrub(argv):
    """Apaga dominios privados do historico ja gravado. O host e removido da
    linha e a classe vira PRIVATE — nao da para recuperar depois, de proposito."""
    cfg = load_cfg()
    dias = int(argv[0]) if argv and argv[0].isdigit() else 400
    total = 0
    arquivos = 0
    for i in range(dias):
        d = (dt.date.today() - dt.timedelta(days=i)).strftime("%Y-%m-%d")
        f = LOG_DIR / (d + ".jsonl")
        if not f.exists():
            continue
        linhas = [l for l in f.read_text().splitlines() if l.strip()]
        novas, mud = [], 0
        for l in linhas:
            try:
                r = json.loads(l)
            except Exception:
                novas.append(l)
                continue
            if r.get("host") and host_privado(r["host"], cfg):
                r["host"] = ""
                r["class"] = "PRIVATE"
                mud += 1
            novas.append(json.dumps(r, ensure_ascii=False))
        if mud:
            f.write_text("\n".join(novas) + "\n")
            total += mud
            arquivos += 1
        # Backups tambem contem os hosts. Sobrescreve PRIMEIRO (o dado some
        # mesmo sem permissao de apagar), depois tenta remover o arquivo.
        bak = f.with_suffix(".jsonl.bak")
        if bak.exists():
            try:
                if any(host_privado(json.loads(l).get("host", ""), cfg)
                       for l in bak.read_text().splitlines()
                       if l.strip().startswith("{")):
                    bak.write_text("")
            except Exception:
                bak.write_text("")
            try:
                bak.unlink()
            except OSError:
                pass
    # limpa tambem das listas de config, se alguem tiver triado antes
    mexeu = False
    for chave in ("blocked_domains", "work_domains"):
        antes = list(cfg.get(chave, []))
        cfg[chave] = [x for x in antes if not host_privado(x, cfg)]
        if len(cfg[chave]) != len(antes):
            mexeu = True
    if mexeu:
        save_cfg(cfg)
    print("\n  %d registro(s) limpos em %d arquivo(s). Backups apagados."
          % (total, arquivos))
    print("  Dominios privados nao voltam a ser gravados.\n")


def cmd_reclassify(argv):
    """Reprocessa os logs com o config atual. Depois de triar um dominio ou
    app, o passado tambem estava errado — isto conserta o historico."""
    cfg = load_cfg()
    dias = int(argv[0]) if argv and argv[0].isdigit() else 1
    print("\n  HIC — reclassificando %d dia(s) com o config atual" % dias)
    print("  " + "-" * 54)
    total_mud = 0
    for i in range(dias):
        d = (dt.date.today() - dt.timedelta(days=i)).strftime("%Y-%m-%d")
        f = LOG_DIR / (d + ".jsonl")
        if not f.exists():
            continue
        linhas = [l for l in f.read_text().splitlines() if l.strip()]
        novas, antes, depois, mud = [], {}, {}, 0
        for l in linhas:
            try:
                r = json.loads(l)
            except Exception:
                novas.append(l)
                continue
            velho = r.get("class", "OFF")
            antes[velho] = antes.get(velho, 0) + 1
            fora = False
            if not r.get("block") and not cfg.get("count_all_day", True):
                try:
                    ok_j, _ = in_work_window(
                        cfg, dt.datetime.fromisoformat(r["ts"]))
                    fora = not ok_j
                except Exception:
                    fora = False
            k, _, _ = classify_from(r.get("app"), r.get("host"),
                                    int(r.get("idle") or 0), cfg,
                                    fora_da_janela=fora)
            if k != velho:
                mud += 1
                r["class"] = k
            depois[k] = depois.get(k, 0) + 1
            novas.append(json.dumps(r, ensure_ascii=False))
        if not mud:
            print("  %s  sem mudanca (%d linhas)" % (d, len(linhas)))
            continue
        f.with_suffix(".jsonl.bak").write_text("\n".join(linhas) + "\n")
        f.write_text("\n".join(novas) + "\n")
        total_mud += mud
        print("  %s  %d linha(s) corrigida(s)" % (d, mud))
        print("      antes:  %s" % dict(sorted(antes.items())))
        print("      depois: %s" % dict(sorted(depois.items())))
        print("      %sfoco: %d -> %d min%s"
              % (C["g"], antes.get("WORK", 0), depois.get("WORK", 0), C["0"]))
    if not total_mud:
        print("\n  Nada mudou — o historico ja estava certo.\n")
    else:
        print("\n  %d linha(s) no total. Backups em *.jsonl.bak\n" % total_mud)


def host_privado(host, cfg):
    """True se o dominio nao deve ser registrado de forma alguma."""
    h = (host or "").lower().lstrip(".")
    if not h:
        return False
    if host_matches(h, cfg.get("private_domains", [])):
        return True
    for pat in cfg.get("private_patterns", []):
        try:
            if re.search(pat, h):
                return True
        except re.error:
            continue
    return False


def host_matches(host, padroes):
    """Casa por sufixo de dominio: 'google.com' NAO casa 'notgoogle.com'."""
    host = (host or "").lower().lstrip(".")
    for p in padroes:
        p = str(p).lower().strip().lstrip(".")
        if not p:
            continue
        if host == p or host.endswith("." + p):
            return True
    return False


def save_cfg(cfg):
    ensure_dirs()
    tmp = CFG_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(cfg, indent=2, ensure_ascii=False))
    tmp.replace(CFG_PATH)


def day_mode(cfg, now=None):
    """weekday | weekend | off. 'off' e dia protegido: silencio absoluto."""
    now = now or dt.datetime.now()
    wd = now.isoweekday()
    if wd in cfg.get("work_days", []):
        return "weekday"
    if cfg.get("weekend_enabled", True) and wd in cfg.get("weekend_days", []):
        return "weekend"
    return "off"


def in_work_window(cfg, now=None):
    now = now or dt.datetime.now()
    modo = day_mode(cfg, now)
    cur = now.hour * 60 + now.minute
    if modo == "off":
        return False, "dia protegido"
    if modo == "weekend":
        if cur < hhmm_to_min(cfg.get("weekend_start", "09:00")):
            return False, "fim de semana (cedo)"
        if cur >= hhmm_to_min(cfg.get("weekend_end", "20:00")):
            return False, "fim de semana (fim do dia)"
        return True, "fim de semana"
    if cur < hhmm_to_min(cfg["work_start"]):
        return False, "antes do expediente"
    if cur >= hhmm_to_min(cfg["work_end"]):
        return False, "depois do expediente"
    ls, le = hhmm_to_min(cfg["lunch_start"]), hhmm_to_min(cfg["lunch_end"])
    if ls <= cur < le:
        return False, "almoco"
    return True, "expediente"


# ------------------------------------------------------------------- o tick


def append_log(rec):
    ensure_dirs()
    with log_path().open("a") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def cmd_tick():
    cfg = load_cfg()
    st = load_state()
    now = dt.datetime.now()
    ts = now.isoformat(timespec="seconds")

    # Virada do dia: contadores diarios precisam zerar. Sem isso
    # work_min_today e nags_today somavam entre dias, para sempre.
    hoje = today_key(now)
    if st.get("day") != hoje:
        st["day"] = hoje
        for k in ("work_min_today", "nags_today", "blocks_done_today",
                  "away_min", "weekend_capped", "late_nudged"):
            st.pop(k, None)

    # pausa manual
    until = st.get("paused_until")
    if until and now.timestamp() < until:
        return

    block = st.get("block")
    in_block = bool(block and now.timestamp() < block.get("ends_at", 0))
    if block and not in_block:
        finish_block(cfg, st, completed=True)
        st = load_state()
        block, in_block = None, False

    # Batimento cardiaco: gravado em TODO tick, inclusive fora do expediente.
    # Sem ele, "daemon saudavel em silencio" e "daemon morto" ficam identicos
    # no disco — e o doctor acusa falha quando esta tudo certo.
    ok, why = in_work_window(cfg, now)
    modo = day_mode(cfg, now)
    conta = bool(cfg.get("count_all_day", True))
    st["mode"] = modo
    st["enforcing"] = bool(ok or in_block)
    st["window"] = ("bloco ativo" if in_block else
                    why if ok else
                    (why + " · contando, sem cobrar") if conta else why)
    st["last_tick"] = ts
    st["sampling"] = bool(ok or in_block or conta)

    if not ok and not in_block:
        st["off_streak"] = 0
        st["dist_streak"] = 0
        st["nag_level"] = 0
        if conta:
            # Fora da janela de cobranca, mas dentro da contagem: classifica de
            # verdade, credita o minuto, e NAO cobra nada. Contar e cobrar sao
            # eixos independentes.
            klass, app, host, idle = classify(cfg)
            append_log({"ts": ts, "class": klass, "app": app, "host": host,
                        "idle": idle, "block": False})
            st["last_class"] = klass
            st["last_app"] = app
            st["last_host"] = host
            st["last_idle"] = idle
            if klass == "WORK":
                atribui_minuto_de_trabalho(cfg, st, now)
                checa_hora_tardia(cfg, st, now)
                if modo == "weekend":
                    checa_teto_fim_de_semana(cfg, st, now)
        elif cfg.get("log_offhours", True):
            idle_f = idle_seconds()
            app_f = frontmost_app()
            host_f = (browser_host(cfg)
                      if app_f == norm_app(cfg.get("browser_app")) else "")
            append_log({"ts": ts, "class": "OFFHOURS", "app": app_f,
                        "host": host_f, "idle": idle_f, "block": False})
            st["last_class"] = "OFFHOURS"
            st["last_app"] = app_f
            st["last_host"] = host_f
            st["last_idle"] = idle_f
        save_state(st)
        return

    # ---- convite matinal para montar o plano (1x por dia)
    hora_plano = hhmm_to_min(
        cfg.get("weekend_prompt_time", "10:00") if modo == "weekend"
        else cfg.get("plan_prompt_time", "08:45"))
    agora_min = now.hour * 60 + now.minute
    if (ok and agora_min >= hora_plano
            and st.get("plan_prompt_day") != today_key(now)
            and not (modo == "weekend"
                     and not cfg.get("weekend_nag_enabled", False))
            and not (load_plan() or {}).get("tasks")):
        st["plan_prompt_day"] = today_key(now)
        if modo == "weekend":
            notify("HIC — fim de semana",
                   "Escolhe UM sapo e para em %dh. Abra localhost:%d ou rode: "
                   "hic frog" % (cfg["weekend_target_min"] // 60,
                                 cfg["dashboard_port"]), "Glass")
        else:
            notify("HIC — monte o dia",
                   "Sem plano 3/3/3 hoje. Abra localhost:%d ou rode: hic plan"
                   % cfg["dashboard_port"], "Glass")

    klass, app, host, idle = classify(cfg)
    append_log({
        "ts": ts, "class": klass, "app": app, "host": host,
        "idle": idle, "block": bool(in_block),
    })

    st["last_sample"] = ts
    st["last_class"] = klass
    st["last_app"] = app
    st["last_host"] = host
    st["last_idle"] = idle

    # ---- ausente ou tela travada: nao se julga tempo que ele nao esta ali.
    # O contador tambem ZERA — sem isso, 50 min ausente viravam 50 min de
    # divida, e ele levava modal de nivel 3 no primeiro clique ao voltar.
    if klass in ("AWAY", "LOCKED"):
        st["away_min"] = st.get("away_min", 0) + 1
        st["off_streak"] = 0
        st["nag_level"] = 0
        save_state(st)
        return
    if st.get("away_min", 0) >= 5:
        gone = st["away_min"]
        st["away_min"] = 0
        notify("HIC — de volta",
               "Voce ficou %d min longe da maquina. Retoma o bloco." % gone,
               "Glass")

    # ---- sonda cega: nunca escalona em cima de "nao sei"
    if klass == "BLIND":
        st["blind_streak"] = st.get("blind_streak", 0) + 1
        if (st["blind_streak"] >= 5
                and now.timestamp() - st.get("last_blind_nag", 0) > 3600):
            notify("HIC — sem visao",
                   "Nao consigo ler o app em primeiro plano ha %d min. Falta "
                   "permissao de Acessibilidade. Rode: hic doctor"
                   % st["blind_streak"], "Funk")
            st["last_blind_nag"] = now.timestamp()
        save_state(st)
        return
    st["blind_streak"] = 0

    # ---- distracao explicita: cobra rapido E segue escalonando ate o modal
    if klass == "DIST":
        st["dist_streak"] = st.get("dist_streak", 0) + 1
        if st["dist_streak"] * 60 >= cfg["distraction_grace_sec"]:
            last = st.get("last_dist_nag", 0)
            if now.timestamp() - last > 300:
                msg = pick(cfg["messages"]["distraction"], now.minute)
                notify("HIC — distracao", "%s (%s)"
                       % (msg, host or app), "Basso")
                speak(msg, cfg)
                st["last_dist_nag"] = now.timestamp()
                st["nags_today"] = st.get("nags_today", 0) + 1
    else:
        st["dist_streak"] = 0

    # ---- trabalho de verdade
    if klass == "WORK":
        st["off_streak"] = 0
        st["nag_level"] = 0
        atribui_minuto_de_trabalho(cfg, st, now)
        checa_hora_tardia(cfg, st, now)

        if modo == "weekend":
            checa_teto_fim_de_semana(cfg, st, now)

        if in_block:
            block["work_min"] = block.get("work_min", 0) + 1
            st["block"] = block
            every = cfg["pomodoro_chime_every_min"]
            if every and block["work_min"] % every == 0:
                left = int((block["ends_at"] - now.timestamp()) / 60)
                notify("HIC — pomodoro",
                       "%d min de foco. %d min restantes no bloco."
                       % (block["work_min"], max(left, 0)), "Glass")
        save_state(st)
        return

    # ---- dominio nunca visto no navegador: congela o contador e vai para a
    # triagem. Estar no Brave ja e estar na maquina; nao da para julgar a aba.
    if klass in ("NEUTRAL", "PRIVATE") or (klass == "UNKNOWN" and host):
        save_state(st)
        return

    # ---- OFF / DIST / app desconhecido: acumula e escalona
    st["off_streak"] = st.get("off_streak", 0) + 1
    off = st["off_streak"]
    level = st.get("nag_level", 0)

    # Teto de escalonamento. Modal que rouba o foco e Focus forcado sao a opcao
    # nuclear — ficam so para o que VOCE marcou como distracao. App que ninguem
    # classificou para no nivel 2: cobra, mas nao invade a tela por um palpite.
    teto = 2 if klass == "UNKNOWN" else 3
    if modo == "weekend":
        if not cfg.get("weekend_nag_enabled", False):
            # Sabado nao tem piso. O sistema nao tem nada a dizer sobre voce
            # NAO estar trabalhando — so sobre voce estar trabalhando demais,
            # e isso quem cuida e o checa_teto_fim_de_semana. Silencio.
            st["off_streak"] = 0
            st["nag_level"] = 0
            save_state(st)
            return
        # E o tempo dele. Cobra para comecar, nunca invade a tela.
        teto = min(teto, 2)
        if st.get("weekend_capped", 0) >= 1:
            # Meta ja batida: o sistema cala a boca pelo resto do dia.
            save_state(st)
            return

    base_t1 = (cfg.get("weekend_nag_after_min", 30) if modo == "weekend"
               else cfg["nag_after_min"])
    t1 = cfg["block_nag_after_min"] if in_block else base_t1
    t2 = t1 + (cfg["escalate_2_after_min"] - cfg["nag_after_min"])
    t3 = t1 + (cfg["escalate_3_after_min"] - cfg["nag_after_min"])

    task = block.get("task") if in_block else st.get("frog", "")
    tail = (" Tarefa: %s" % task) if task else ""
    if klass == "UNKNOWN":
        tail = (" Classifique «%s» em localhost:%d e o sistema para de "
                "perguntar." % (app, cfg["dashboard_port"]))

    if teto >= 3 and off >= t3 and (level < 3 or
                      now.timestamp() - st.get("last_nag", 0)
                      > cfg["renag_every_min"] * 60):
        msg = pick(cfg["messages"]["l3"], now.minute)
        notify("HIC — terceiro aviso", msg + tail, "Sosumi")
        speak(msg, cfg)
        modal("HIC — VOLTA PRO TRABALHO",
              "%s\n\n%d minutos fora dos apps de trabalho.%s" % (msg, off, tail))
        set_focus(cfg, True, "nag_l3")
        st["focus_forced"] = True
        st["nag_level"] = 3
        st["last_nag"] = now.timestamp()
        st["nags_today"] = st.get("nags_today", 0) + 1
    elif off >= t2 and level < 2:
        msg = pick(cfg["messages"]["l2"], now.minute)
        notify("HIC — segundo aviso", msg + tail, "Basso")
        speak(msg, cfg)
        st["nag_level"] = 2
        st["last_nag"] = now.timestamp()
        st["nags_today"] = st.get("nags_today", 0) + 1
    elif off >= t1 and level < 1:
        msg = pick(cfg["messages"]["l1"], now.minute)
        notify("HIC — volta pro foco", msg + tail, "Submarine")
        st["nag_level"] = 1
        st["last_nag"] = now.timestamp()
        st["nags_today"] = st.get("nags_today", 0) + 1

    save_state(st)


# ------------------------------------------------------------------- blocos


def atribui_minuto_de_trabalho(cfg, st, now):
    """Um minuto classificado como WORK: conta no dia, credita na tarefa ativa
    e avisa se estourou a estimativa. Usado dentro E fora da janela de cobranca
    — contar e cobrar sao eixos independentes."""
    st["work_min_today"] = int(st.get("work_min_today", 0)) + 1
    plan = load_plan()
    tarefa = active_task(plan)
    if not tarefa:
        return
    tarefa["actual_min"] = int(tarefa.get("actual_min", 0)) + 1
    est = int(tarefa.get("estimate_min") or 0)
    real = tarefa["actual_min"]
    nivel = int(tarefa.get("overrun_notified", 0))
    if est and real >= est * 2 and nivel < 2:
        tarefa["overrun_notified"] = 2
        notify("HIC — dobrou a estimativa",
               "%s: %dmin estimados, %dmin reais. Reestime ou quebre em partes."
               % (tarefa["title"], est, real), "Sosumi")
    elif est and real > est and nivel < 1:
        tarefa["overrun_notified"] = 1
        notify("HIC — estourou a estimativa",
               "%s: voce disse %dmin, ja sao %dmin."
               % (tarefa["title"], est, real), "Basso")
    save_plan(plan)


def checa_hora_tardia(cfg, st, now):
    """O oposto da cobranca. Depois de certa hora o sistema nao te chama de
    volta ao trabalho — ele te manda sair dele."""
    if not cfg.get("late_nudge_enabled", True):
        return
    hm = now.hour * 60 + now.minute
    nivel = int(st.get("late_nudged", 0))
    n1 = hhmm_to_min(cfg.get("late_nudge_1", "22:00"))
    n2 = hhmm_to_min(cfg.get("late_nudge_2", "23:00"))
    # Madrugada e da meia-noite ate as 05:00 — NAO "antes do expediente".
    # Comecar as 07:00 e cedo; as 03:00 e outra coisa.
    madrugada = hm < hhmm_to_min(cfg.get("late_nudge_madrugada_end", "05:00"))
    feito = int(st.get("work_min_today", 0))

    if madrugada and nivel < 3:
        st["late_nudged"] = 3
        ontem = summarize_day(
            (now.date() - dt.timedelta(days=1)).strftime("%Y-%m-%d"))["work_min"]
        msg = ("%02d:%02d da manha. Ontem foram %dh%02d de foco. Isso nao "
               "aparece como vantagem no dashboard, aparece como queda daqui "
               "a duas semanas." % (now.hour, now.minute, ontem // 60, ontem % 60))
        notify("HIC — passou da meia-noite", msg, "Sosumi")
        speak("Passou da meia-noite. Fecha o notebook.", cfg)
        modal("HIC — FECHA O NOTEBOOK", msg, "Fechando")
        set_focus(cfg, False, "auto_off")
        st["nags_today"] = st.get("nags_today", 0) + 1
    elif not madrugada and hm >= n2 and nivel < 2:
        st["late_nudged"] = 2
        msg = ("%dh%02d de foco hoje. O proximo minuto rende menos que o sono "
               "que ele custa." % (feito // 60, feito % 60))
        notify("HIC — ja deu", msg, "Basso")
        speak(msg, cfg)
        st["nags_today"] = st.get("nags_today", 0) + 1
    elif not madrugada and hm >= n1 and nivel < 1:
        st["late_nudged"] = 1
        notify("HIC — %02d:%02d" % (now.hour, now.minute),
               "%dh%02d de foco hoje. Boa hora de fechar."
               % (feito // 60, feito % 60), "Glass")


def checa_teto_fim_de_semana(cfg, st, now):
    """Parada dura. O alvo do fim de semana e um TETO, nao um piso: bateu,
    o sistema manda fechar o notebook — e escala se voce insistir, com a mesma
    firmeza que usaria para te tirar do YouTube."""
    alvo = int(cfg.get("weekend_target_min", 180))
    feito = int(st.get("work_min_today", 0))
    nivel = int(st.get("weekend_capped", 0))
    o1 = alvo + int(cfg.get("weekend_overrun_1_min", 60))
    o2 = alvo + int(cfg.get("weekend_overrun_2_min", 120))

    if feito >= o2 and nivel < 3:
        st["weekend_capped"] = 3
        msg = ("%dh%02d num sabado. Isso nao e vantagem competitiva, e divida "
               "que a semana vai cobrar." % (feito // 60, feito % 60))
        notify("HIC — PARA", msg, "Sosumi")
        speak("Passou duas horas do teto. Fecha o notebook.", cfg)
        modal("HIC — FECHA O NOTEBOOK",
              "%s\n\nMeta do fim de semana: %dh. Voce esta em %dh%02d."
              % (msg, alvo // 60, feito // 60, feito % 60), "Fechando")
        set_focus(cfg, False, "auto_off")
        st["nags_today"] = st.get("nags_today", 0) + 1
    elif feito >= o1 and nivel < 2:
        st["weekend_capped"] = 2
        msg = ("Voce passou %dmin do teto. Consistencia bate intensidade em "
               "horizonte de cinco anos." % (feito - alvo))
        notify("HIC — passou do teto", msg, "Basso")
        speak(msg, cfg)
        st["nags_today"] = st.get("nags_today", 0) + 1
    elif feito >= alvo and nivel < 1:
        st["weekend_capped"] = 1
        notify("HIC — meta batida",
               "%dh%02d de foco. Fecha o notebook — o resto do fim de semana "
               "e seu." % (feito // 60, feito % 60), "Glass")
        set_focus(cfg, False, "auto_off")


def finish_block(cfg, st, completed):
    block = st.get("block")
    if not block:
        return
    mins = block.get("work_min", 0)
    st["block"] = None
    st["blocks_done_today"] = st.get("blocks_done_today", 0) + (1 if completed else 0)
    save_state(st)
    if st.get("focus_forced") or block.get("focus"):
        set_focus(cfg, False, "auto_off")
        st["focus_forced"] = False
        save_state(st)
    verb = "concluido" if completed else "abortado"
    plan = load_plan()
    tarefa = active_task(plan)
    if tarefa:
        est = int(tarefa.get("estimate_min") or 0)
        real = int(tarefa.get("actual_min") or 0)
        notify("HIC — bloco %s" % verb,
               "%s: %dmin reais de %dmin estimados. Terminou? Marque em "
               "localhost:%d" % (tarefa["title"], real, est,
                                 load_cfg()["dashboard_port"]), "Glass")
    else:
        notify("HIC — bloco %s" % verb,
               "%s — %d min de foco real." % (block.get("task", "bloco"), mins),
               "Glass")


def cmd_frog(argv):
    cfg = load_cfg()
    st = load_state()
    minutes = 90
    task = ""
    rest = list(argv)
    if rest and rest[-1].isdigit():
        minutes = int(rest.pop())
    task = " ".join(rest).strip()
    plan = load_plan()
    alvo = None
    if plan:
        # numero puro = id de tarefa; senao casa pelo titulo; senao pega o sapo
        if task.isdigit():
            alvo = find_task(plan, task)
        if not alvo and task:
            alvo = next((t for t in plan["tasks"]
                         if task.lower() in t["title"].lower()), None)
        if not alvo and not task:
            pend = [t for t in plan["tasks"] if t["status"] != "done"]
            alvo = next((t for t in pend if t["bucket"] == "frog"),
                        pend[0] if pend else None)
    if alvo:
        start_task(plan, alvo["id"])
        save_plan(plan)
        task = alvo["title"]
        if minutes == 90 and alvo.get("estimate_min"):
            minutes = int(alvo["estimate_min"])
    if not task:
        try:
            task = input("Qual e o sapo? ").strip()
        except EOFError:
            task = "deep work"
    now = time.time()
    st["block"] = {
        "task": task or "deep work",
        "started_at": now,
        "ends_at": now + minutes * 60,
        "work_min": 0,
        "focus": True,
    }
    st["off_streak"] = 0
    st["nag_level"] = 0
    save_state(st)
    ok = set_focus(cfg, True, "frog_start")
    notify("HIC — bloco iniciado",
           "%s · %d min%s" % (task, minutes, "" if ok else " (Focus nao configurado)"),
           "Glass")
    print("Bloco iniciado: %s (%d min)" % (task, minutes))
    if not ok:
        print("Aviso: atalho '%s' nao encontrado. Rode 'hic doctor'."
              % cfg["focus_shortcut_on"])


def cmd_done():
    cfg = load_cfg()
    st = load_state()
    if not st.get("block"):
        print("Nenhum bloco ativo.")
        return
    finish_block(cfg, st, completed=True)
    print("Bloco encerrado.")


# ------------------------------------------------------------- plano 3/3/3


# Ordem dos baldes E a prioridade. Sapo primeiro, sempre — sem decisao nova
# de manha. Estimativa default por balde, editavel por tarefa.
BUCKETS = {
    "frog": {"ordem": 0, "rotulo": "sapo", "estimativa": 180, "max": 1},
    "urgent": {"ordem": 1, "rotulo": "urgente", "estimativa": 30, "max": 3},
    "maintenance": {"ordem": 2, "rotulo": "manutenção", "estimativa": 15, "max": 3},
}


def plan_path(now=None):
    return PLAN_DIR / (today_key(now) + ".json")


def new_task(tid, title, bucket, estimate=None):
    return {
        "id": tid,
        "title": title,
        "bucket": bucket if bucket in BUCKETS else "urgent",
        "estimate_min": int(estimate if estimate is not None
                            else BUCKETS.get(bucket, BUCKETS["urgent"])["estimativa"]),
        "status": "todo",
        "actual_min": 0,
        "started_at": None,
        "done_at": None,
        "overrun_notified": 0,
    }


def empty_plan(day=None):
    return {
        "date": day or today_key(),
        "created_at": dt.datetime.now().isoformat(timespec="seconds"),
        "tasks": [],
        "next_id": 1,
    }


def migrate_plan(p):
    """Planos antigos guardavam 3 listas de strings. Vira lista de tarefas."""
    if p.get("tasks") is not None:
        p.setdefault("next_id", len(p["tasks"]) + 1)
        return p
    tasks, n = [], 1
    if p.get("frog"):
        tasks.append(new_task(n, p["frog"], "frog")); n += 1
    for t in p.get("urgent", []):
        tasks.append(new_task(n, t, "urgent")); n += 1
    for t in p.get("maintenance", []):
        tasks.append(new_task(n, t, "maintenance")); n += 1
    p["tasks"] = tasks
    p["next_id"] = n
    return p


def load_plan(now=None, create=False):
    p = plan_path(now)
    if p.exists():
        try:
            return migrate_plan(json.loads(p.read_text()))
        except Exception:
            pass
    return empty_plan() if create else None


def save_plan(plan, now=None):
    ensure_dirs()
    plan["tasks"] = sorted(
        plan.get("tasks", []),
        key=lambda t: (BUCKETS.get(t.get("bucket", "urgent"), {}).get("ordem", 9),
                       t.get("id", 0)))
    tmp = plan_path(now).with_suffix(".tmp")
    tmp.write_text(json.dumps(plan, indent=2, ensure_ascii=False))
    tmp.replace(plan_path(now))


def active_task(plan):
    for t in (plan or {}).get("tasks", []):
        if t.get("status") == "doing":
            return t
    return None


def find_task(plan, tid):
    for t in (plan or {}).get("tasks", []):
        if str(t.get("id")) == str(tid):
            return t
    return None


def start_task(plan, tid):
    """Uma tarefa ativa por vez — o relogio nao pode correr em duas."""
    alvo = find_task(plan, tid)
    if not alvo:
        return None
    for t in plan["tasks"]:
        if t.get("status") == "doing" and t is not alvo:
            t["status"] = "todo"
    alvo["status"] = "doing"
    alvo["started_at"] = alvo.get("started_at") or \
        dt.datetime.now().isoformat(timespec="seconds")
    return alvo


def plan_totals(plan):
    ts = (plan or {}).get("tasks", [])
    est = sum(int(t.get("estimate_min") or 0) for t in ts)
    real = sum(int(t.get("actual_min") or 0) for t in ts)
    feitas = [t for t in ts if t.get("status") == "done"]
    est_f = sum(int(t.get("estimate_min") or 0) for t in feitas)
    real_f = sum(int(t.get("actual_min") or 0) for t in feitas)
    return {
        "estimado": est, "real": real,
        "feitas": len(feitas), "total": len(ts),
        "estimado_feitas": est_f, "real_feitas": real_f,
        "vies": round(real_f / est_f, 2) if est_f else None,
    }


def accuracy_history(dias=14):
    """Quanto voce erra a estimativa, historicamente. O produto de verdade."""
    est = real = n = 0
    for i in range(dias):
        d = (dt.date.today() - dt.timedelta(days=i)).strftime("%Y-%m-%d")
        p = plan_path(dt.datetime.strptime(d, "%Y-%m-%d"))
        if not p.exists():
            continue
        try:
            pl = migrate_plan(json.loads(p.read_text()))
        except Exception:
            continue
        for t in pl.get("tasks", []):
            if t.get("status") == "done" and t.get("estimate_min") and t.get("actual_min"):
                est += int(t["estimate_min"]); real += int(t["actual_min"]); n += 1
    return {"tarefas": n, "estimado": est, "real": real,
            "vies": round(real / est, 2) if est else None}


def cmd_plan():
    ensure_dirs()
    plan = load_plan(create=True)
    print("\n  HIC — ritual 3/3/3")
    print("  " + "-" * 48)
    print("  Deixe em branco para pular. A estimativa e um contrato:")
    print("  o daemon vai cronometrar quanto realmente levou.\n")

    def pergunta(rotulo, bucket, quantos):
        for i in range(1, quantos + 1):
            titulo = input("  %s %d/%d: " % (rotulo, i, quantos)).strip()
            if not titulo:
                continue
            padrao = BUCKETS[bucket]["estimativa"]
            bruto = input("      estimativa em min [%d]: " % padrao).strip()
            try:
                est = int(bruto) if bruto else padrao
            except ValueError:
                est = padrao
            plan["tasks"].append(new_task(plan["next_id"], titulo, bucket, est))
            plan["next_id"] += 1

    pergunta("Sapo (projeto de ~3h)", "frog", 1)
    pergunta("Urgente", "urgent", 3)
    pergunta("Manutencao", "maintenance", 3)
    save_plan(plan)
    tot = plan_totals(plan)
    print("\n  %d tarefa(s), %d min estimados no total." % (tot["total"], tot["estimado"]))
    print("  Comece com: hic frog\n")


def cmd_task(argv):
    plan = load_plan(create=True)
    sub = argv[0] if argv else "list"
    rest = argv[1:]

    if sub in ("add", "a"):
        bucket = "urgent"
        est = None
        while rest and rest[-1] in BUCKETS:
            bucket = rest.pop()
        if rest and rest[-1].isdigit():
            est = int(rest.pop())
        titulo = " ".join(rest).strip()
        if not titulo:
            print("uso: hic task add \"titulo\" [minutos] [frog|urgent|maintenance]")
            return
        t = new_task(plan["next_id"], titulo, bucket, est)
        plan["next_id"] += 1
        plan["tasks"].append(t)
        save_plan(plan)
        print("#%d  %s  (%s, %dmin)" % (t["id"], t["title"],
                                        BUCKETS[t["bucket"]]["rotulo"], t["estimate_min"]))
    elif sub in ("start", "s") and rest:
        t = start_task(plan, rest[0])
        if not t:
            print("tarefa #%s nao existe" % rest[0]); return
        save_plan(plan)
        print("cronometrando: %s (estimativa %dmin)" % (t["title"], t["estimate_min"]))
    elif sub in ("done", "d") and rest:
        t = find_task(plan, rest[0])
        if not t:
            print("tarefa #%s nao existe" % rest[0]); return
        t["status"] = "done"
        t["done_at"] = dt.datetime.now().isoformat(timespec="seconds")
        save_plan(plan)
        est, real = t.get("estimate_min", 0), t.get("actual_min", 0)
        delta = ("%+d min" % (real - est)) if est else "sem estimativa"
        print("feito: %s — estimou %dmin, levou %dmin (%s)"
              % (t["title"], est, real, delta))
    elif sub in ("rm", "del") and rest:
        plan["tasks"] = [t for t in plan["tasks"] if str(t["id"]) != str(rest[0])]
        save_plan(plan)
        print("removida.")
    elif sub in ("est", "e") and len(rest) >= 2:
        t = find_task(plan, rest[0])
        if t:
            t["estimate_min"] = int(rest[1])
            t["overrun_notified"] = 0
            save_plan(plan)
            print("#%s agora estima %s min" % (rest[0], rest[1]))
    else:
        ts = plan.get("tasks", [])
        if not ts:
            print("\n  Sem plano hoje. Rode: hic plan\n"); return
        tot = plan_totals(plan)
        print()
        for t in ts:
            mark = {"done": "x", "doing": ">", "todo": " "}.get(t["status"], " ")
            est, real = t.get("estimate_min", 0), t.get("actual_min", 0)
            cor = C["0"]
            if t["status"] == "done":
                cor = C["g"] if real <= est else C["y"]
            elif t["status"] == "doing":
                cor = C["b"]
            if est and real > est:
                cor = C["r"]
            print("  [%s] %s#%-3d %-38s%s %s%3d/%-3dmin%s  %s"
                  % (mark, cor, t["id"], t["title"][:38], C["0"],
                     cor, real, est, C["0"], BUCKETS[t["bucket"]]["rotulo"]))
        print("  " + "-" * 62)
        print("  %d/%d feitas · %d min estimados · %d min reais"
              % (tot["feitas"], tot["total"], tot["estimado"], tot["real"]))
        h = accuracy_history()
        if h["vies"]:
            print("  vies historico: voce leva %.0f%% do que estima (%d tarefas)"
                  % (h["vies"] * 100, h["tarefas"]))
        print()


# ----------------------------------------------------------------- agregacao


def read_day(day):
    p = LOG_DIR / (day + ".jsonl")
    if not p.exists():
        return []
    recs = []
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            recs.append(json.loads(line))
        except Exception:
            continue
    return recs


def summarize_day(day):
    recs = read_day(day)
    counts = {"WORK": 0, "DIST": 0, "OFF": 0, "AWAY": 0, "NEUTRAL": 0,
              "BLIND": 0, "LOCKED": 0, "UNKNOWN": 0, "OFFHOURS": 0,
              "PRIVATE": 0}
    apps = {}
    hosts = {}
    desconhecidos = {}
    timeline = {}
    for r in recs:
        k = r.get("class", "OFF")
        counts[k] = counts.get(k, 0) + 1
        a = r.get("app") or "-"
        if k == "WORK":
            apps[a] = apps.get(a, 0) + 1
        if k == "DIST" and r.get("host"):
            hosts[r["host"]] = hosts.get(r["host"], 0) + 1
        if k == "UNKNOWN":
            # UNKNOWN com host = dominio do navegador; sem host = app
            chave = ("host", r["host"]) if r.get("host") else ("app", a)
            if chave[1] and chave[1] != "-":
                desconhecidos[chave] = desconhecidos.get(chave, 0) + 1
        try:
            t = dt.datetime.fromisoformat(r["ts"])
            timeline[t.hour * 60 + t.minute] = k
        except Exception:
            pass
    return {
        "date": day,
        "counts": counts,
        "work_min": counts.get("WORK", 0),
        "dist_min": counts.get("DIST", 0),
        "off_min": counts.get("OFF", 0),
        "away_min": counts.get("AWAY", 0) + counts.get("LOCKED", 0),
        "locked_min": counts.get("LOCKED", 0),
        "blind_min": counts.get("BLIND", 0),
        "unknown_min": counts.get("UNKNOWN", 0),
        "offhours_min": counts.get("OFFHOURS", 0),
        "top_apps": sorted(apps.items(), key=lambda x: -x[1])[:6],
        "top_hosts": sorted(hosts.items(), key=lambda x: -x[1])[:6],
        "unknown_hosts": desconhecidos,
        "timeline": timeline,
    }


def triage_queue(cfg, dias=7):
    """Dominios E apps vistos e ainda nao classificados, dos ultimos N dias.
    Filtra os que ja foram triados desde que o log foi escrito."""
    acc = {}
    for i in range(dias):
        d = (dt.date.today() - dt.timedelta(days=i)).strftime("%Y-%m-%d")
        if not (LOG_DIR / (d + ".jsonl")).exists():
            continue
        for chave, n in summarize_day(d)["unknown_hosts"].items():
            acc[chave] = acc.get(chave, 0) + n
    fila = []
    for (kind, nome), n in acc.items():
        if kind == "host":
            if (host_matches(nome, cfg.get("work_domains", []))
                    or host_matches(nome, cfg.get("blocked_domains", []))):
                continue
        else:
            if app_class(nome, cfg) != "UNKNOWN":
                continue
        fila.append({"kind": kind, "host": nome, "min": n})
    return sorted(fila, key=lambda x: -x["min"])[:25]


def banda_do_dia(cfg, d):
    """(piso, teto) do dia, ou None se for dia protegido.
    Fim de semana ja e teto puro — piso zero, qualquer quantidade serve."""
    wd = d.isoweekday()
    if wd in cfg.get("work_days", []):
        return (int(cfg.get("band_min_min", 300)),
                int(cfg.get("band_max_min", 480)))
    if cfg.get("weekend_enabled", True) and wd in cfg.get("weekend_days", []):
        return (0, int(cfg.get("weekend_target_min", 180)))
    return None


def estado_da_banda(cfg, d, minutos):
    b = banda_do_dia(cfg, d)
    if b is None:
        return "protegido"
    lo, hi = b
    if minutos < lo:
        return "abaixo"
    if minutos > hi:
        return "acima"
    return "dentro"


def alvo_do_dia(cfg, d):
    """Dia protegido nao quebra streak; fim de semana usa o alvo do fim de
    semana; dia util usa o alvo normal."""
    wd = d.isoweekday()
    if wd in cfg.get("work_days", []):
        return cfg["streak_target_min"]
    if cfg.get("weekend_enabled", True) and wd in cfg.get("weekend_days", []):
        return int(cfg.get("weekend_target_min", 180))
    return None


def streak(cfg):
    """Dias consecutivos DENTRO da banda. Estourar o teto quebra tanto quanto
    ficar abaixo do piso — e essa e a informacao nova."""
    n = 0
    d = dt.date.today()
    # o dia de hoje ainda esta em curso: se ainda nao chegou no piso, nao conta
    # contra; comeca de ontem.
    if estado_da_banda(cfg, d, summarize_day(d.strftime("%Y-%m-%d"))["work_min"]) \
            != "dentro":
        d = d - dt.timedelta(days=1)
    limite = 0
    while limite < 400:
        limite += 1
        key = d.strftime("%Y-%m-%d")
        if banda_do_dia(cfg, d) is None:
            d = d - dt.timedelta(days=1)
            continue
        if not (LOG_DIR / (key + ".jsonl")).exists():
            break
        if estado_da_banda(cfg, d, summarize_day(key)["work_min"]) == "dentro":
            n += 1
            d = d - dt.timedelta(days=1)
        else:
            break
    return n


def build_state_payload():
    cfg = load_cfg()
    st = load_state()
    now = dt.datetime.now()
    day = summarize_day(today_key(now))
    ok, why = in_work_window(cfg, now)
    block = st.get("block")
    in_block = bool(block and now.timestamp() < block.get("ends_at", 0))
    last14 = []
    for i in range(13, -1, -1):
        d = (dt.date.today() - dt.timedelta(days=i)).strftime("%Y-%m-%d")
        s = summarize_day(d)
        last14.append({
            "date": d,
            "work_min": s["work_min"],
            "dist_min": s["dist_min"],
            "hit": s["work_min"] >= cfg["streak_target_min"],
        })
    paused = st.get("paused_until", 0)
    tick_age = None
    if st.get("last_tick"):
        try:
            tick_age = int(
                (now - dt.datetime.fromisoformat(st["last_tick"])).total_seconds())
        except Exception:
            tick_age = None
    return {
        "now": now.isoformat(timespec="seconds"),
        "window": st.get("window", why),
        "in_window": ok,
        "sampling": bool(st.get("sampling", ok)),
        "tick_age": tick_age,
        "mode": st.get("mode", day_mode(cfg, now)),
        "enforcing": bool(st.get("enforcing", ok)),
        "count_all_day": bool(cfg.get("count_all_day", True)),
        "late_nudged": int(st.get("late_nudged", 0)),
        "weekend_target_min": int(cfg.get("weekend_target_min", 180)),
        "weekend_capped": int(st.get("weekend_capped", 0)),
        "blind_streak": st.get("blind_streak", 0),
        "work_start": (cfg.get("weekend_start", "09:00")
                       if day_mode(cfg, now) == "weekend"
                       else cfg["work_start"]),
        "work_end": (cfg.get("weekend_end", "20:00")
                     if day_mode(cfg, now) == "weekend"
                     else cfg["work_end"]),
        "band_min": (banda_do_dia(cfg, now.date()) or (0, 0))[0],
        "band_max": (banda_do_dia(cfg, now.date()) or (0, 0))[1],
        "band_state": estado_da_banda(cfg, now.date(),
                                      summarize_day(today_key(now))["work_min"]),
        "daily_target_min": (banda_do_dia(cfg, now.date()) or (0, 240))[1],
        "streak_target_min": cfg["streak_target_min"],
        "current": {
            "class": st.get("last_class", "-"),
            "app": st.get("last_app", "-"),
            "host": st.get("last_host", ""),
            "idle": st.get("last_idle", 0),
            "off_streak": st.get("off_streak", 0),
            "nag_level": st.get("nag_level", 0),
            "last_tick": st.get("last_tick", ""),
            "last_sample": st.get("last_sample", ""),
        },
        "today": {
            "work_min": day["work_min"],
            "dist_min": day["dist_min"],
            "off_min": day["off_min"],
            "away_min": day["away_min"],
            "blind_min": day["blind_min"],
            "unknown_min": day["unknown_min"],
            "nags": st.get("nags_today", 0),
            "blocks": st.get("blocks_done_today", 0),
            "top_apps": day["top_apps"],
            "top_hosts": day["top_hosts"],
        },
        "timeline": [
            {"m": m, "k": k} for m, k in sorted(day["timeline"].items())
        ],
        "block": {
            "active": in_block,
            "task": block.get("task") if block else "",
            "work_min": block.get("work_min", 0) if block else 0,
            "ends_in": int((block["ends_at"] - now.timestamp()) / 60)
            if in_block else 0,
        },
        "plan": load_plan() or empty_plan(),
        "totals": plan_totals(load_plan()),
        "accuracy": accuracy_history(),
        "buckets": {k: v["rotulo"] for k, v in BUCKETS.items()},
        "triage": triage_queue(cfg),
        "unknown_policy": cfg.get("unknown_domain_policy", "log"),
        "streak": streak(cfg),
        "last14": last14,
        "paused": bool(paused and now.timestamp() < paused),
        "paused_min": int((paused - now.timestamp()) / 60)
        if paused and now.timestamp() < paused else 0,
    }


# ------------------------------------------------------------------- server

DASHBOARD_HTML = r"""<!doctype html>
<html lang="pt-BR"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>HIC OS</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:#000;--panel:#0a0a0a;--border:#1f1f1f;--border2:#2e2e2e;
  --fg:#ededed;--muted:#8f8f8f;--dim:#5a5a5a;
  --ok:#3ecf8e;--warn:#f5a524;--bad:#f45b5b;--acc:#4f9dff;
  --mono:ui-monospace,"SF Mono",SFMono-Regular,Menlo,monospace;
}
body{
  background:var(--bg);color:var(--fg);min-height:100vh;
  font-family:-apple-system,BlinkMacSystemFont,"SF Pro Display","Inter",system-ui,sans-serif;
  -webkit-font-smoothing:antialiased;
  background-image:
    radial-gradient(60rem 30rem at 50% -10rem,rgba(79,157,255,.10),transparent 70%),
    linear-gradient(rgba(255,255,255,.022) 1px,transparent 1px),
    linear-gradient(90deg,rgba(255,255,255,.022) 1px,transparent 1px);
  background-size:auto,44px 44px,44px 44px;
}
.wrap{max-width:1080px;margin:0 auto;padding:44px 24px 72px}
header{display:flex;align-items:flex-end;justify-content:space-between;
  gap:16px;flex-wrap:wrap;margin-bottom:32px}
h1{font-size:26px;letter-spacing:-.03em;font-weight:600}
h1 span{color:var(--dim);font-weight:400}
.sub{color:var(--muted);font-size:13px;margin-top:6px;font-family:var(--mono)}
.pill{display:inline-flex;align-items:center;gap:7px;border:1px solid var(--border2);
  border-radius:999px;padding:7px 14px;font-size:12.5px;font-family:var(--mono);
  color:var(--muted);background:rgba(255,255,255,.02)}
.dot{width:7px;height:7px;border-radius:50%;background:var(--dim);
  box-shadow:0 0 0 0 currentColor}
.dot.on{background:var(--ok);animation:p 2.4s infinite}
.dot.warn{background:var(--warn)}.dot.bad{background:var(--bad);animation:p 1s infinite}
@keyframes p{0%{opacity:1}50%{opacity:.35}100%{opacity:1}}
.grid{display:grid;gap:14px;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));
  margin-bottom:14px}
.grid.kpi{grid-template-columns:repeat(auto-fit,minmax(176px,1fr))}
.grid.kpi .big{font-size:36px}
.card{border:1px solid var(--border);border-radius:14px;background:var(--panel);
  padding:20px 22px;position:relative;overflow:hidden}
.card.wide{grid-column:1/-1}
.label{font-size:10.5px;letter-spacing:.13em;text-transform:uppercase;
  color:var(--dim);font-family:var(--mono);margin-bottom:12px}
.big{font-size:42px;font-weight:600;letter-spacing:-.045em;line-height:1;
  font-variant-numeric:tabular-nums}
.big small{font-size:15px;color:var(--dim);font-weight:400;margin-left:5px;
  letter-spacing:0}
.meta{color:var(--muted);font-size:12.5px;margin-top:10px;font-family:var(--mono)}
.bar{height:5px;border-radius:3px;background:#191919;margin-top:14px;overflow:hidden}
.bar i{display:block;height:100%;background:var(--ok);border-radius:3px;
  transition:width .5s ease}
.tl{display:flex;gap:1px;height:60px;align-items:stretch;margin-top:6px;
  border-radius:6px;overflow:hidden;background:#0f0f0f}
.tl i{flex:1 1 0;min-width:0}
.tlx{display:flex;justify-content:space-between;color:var(--dim);font-size:10.5px;
  font-family:var(--mono);margin-top:8px}
.legend{display:flex;gap:16px;flex-wrap:wrap;margin-top:14px;font-size:11.5px;
  color:var(--muted);font-family:var(--mono)}
.legend b{display:inline-block;width:9px;height:9px;border-radius:2px;
  margin-right:6px;vertical-align:middle}
.streak{display:grid;grid-template-columns:repeat(7,1fr);gap:6px;margin-top:6px}
.streak i{aspect-ratio:1;border-radius:5px;background:#161616;border:1px solid #222}
.streak i.hit{background:var(--ok);border-color:var(--ok);opacity:.85}
.streak i.part{background:#1f3d30;border-color:#2b5443}
.rows{display:flex;flex-direction:column;gap:9px;margin-top:4px}
.row{display:flex;justify-content:space-between;gap:12px;font-size:13px;
  font-family:var(--mono);color:var(--muted);align-items:baseline}
.row b{color:var(--fg);font-weight:500;overflow:hidden;text-overflow:ellipsis;
  white-space:nowrap}
.row s{text-decoration:none;color:var(--dim);font-variant-numeric:tabular-nums}
ol{list-style:none;counter-reset:c}
ol li{counter-increment:c;display:flex;gap:11px;padding:6px 0;font-size:13.5px;
  border-bottom:1px solid #141414;color:var(--fg)}
ol li:last-child{border:0}
ol li:before{content:counter(c);font-family:var(--mono);color:var(--dim);
  font-size:11px;padding-top:2px;min-width:12px}
/* ---- triagem de dominios ---- */
.tri{display:grid;grid-template-columns:1fr 62px 108px 116px;gap:10px;
  align-items:center;padding:9px 0;border-bottom:1px solid #141414}
.tri:last-child{border-bottom:0}
.thost{font-family:var(--mono);font-size:13px;color:var(--fg);overflow:hidden;
  text-overflow:ellipsis;white-space:nowrap}
.kind{font-style:normal;font-size:9.5px;letter-spacing:.08em;text-transform:uppercase;
  color:var(--dim);border:1px solid #242424;border-radius:4px;padding:2px 5px;
  margin-right:9px;background:#111}
.tmin{font-family:var(--mono);font-size:11.5px;color:var(--dim);text-align:right;
  font-variant-numeric:tabular-nums}
.tri-b{border:1px solid #262626;background:#131313;color:#8f8f8f;border-radius:7px;
  padding:6px 10px;font:inherit;font-size:12px;cursor:pointer;white-space:nowrap;
  transition:.12s}
.tri-b.work:hover{border-color:#3ecf8e;color:#3ecf8e;background:rgba(62,207,142,.1)}
.tri-b.block:hover{border-color:#f45b5b;color:#f45b5b;background:rgba(244,91,91,.1)}
@media(max-width:640px){
  .tri{grid-template-columns:1fr 54px;row-gap:8px}
  .tri-b{grid-column:span 1}
}

/* ---- lista de tarefas ativa ---- */
.chead{display:flex;justify-content:space-between;align-items:baseline;gap:14px;
  flex-wrap:wrap;margin-bottom:14px}
.pmeta{font-family:var(--mono);font-size:12px;color:var(--muted);
  font-variant-numeric:tabular-nums}
.task{display:grid;grid-template-columns:24px 24px 1fr 84px 92px 64px 20px;gap:10px;
  align-items:center;padding:10px 0;border-bottom:1px solid #141414}
.task:last-of-type{border-bottom:0}
.task.done .ttl{color:var(--dim);text-decoration:line-through}
.task.doing{background:linear-gradient(90deg,rgba(62,207,142,.07),transparent);
  margin:0 -10px;padding-left:10px;padding-right:10px;border-radius:7px}
.tbtn{width:24px;height:24px;border-radius:50%;border:1px solid #2b2b2b;
  background:#141414;color:#9a9a9a;cursor:pointer;font-size:11px;line-height:1;
  display:grid;place-items:center;padding:0;transition:.12s}
.tbtn:hover{border-color:#3ecf8e;color:#3ecf8e}
.task.doing .tbtn.play{border-color:#3ecf8e;color:#3ecf8e;background:rgba(62,207,142,.14)}
.task.done .tbtn.check{border-color:#3ecf8e;color:#3ecf8e;background:rgba(62,207,142,.16)}
.ttl{font-size:14px;color:var(--fg);overflow:hidden;text-overflow:ellipsis;
  white-space:nowrap}
.chip{font-family:var(--mono);font-size:10px;letter-spacing:.06em;
  text-transform:uppercase;padding:3px 7px;border-radius:5px;text-align:center;
  border:1px solid #232323;color:#7d7d7d;background:#121212}
.chip.frog{border-color:#2a4a6b;color:#6fa8dc;background:rgba(79,157,255,.08)}
.chip.urgent{border-color:#4a3520;color:#d99a4e;background:rgba(217,154,78,.07)}
.tbar{height:4px;border-radius:3px;background:#191919;overflow:hidden}
.tbar i{display:block;height:100%;border-radius:3px;transition:width .4s ease}
.tnum{font-family:var(--mono);font-size:11.5px;color:var(--muted);text-align:right;
  font-variant-numeric:tabular-nums;white-space:nowrap}
.tnum b{color:var(--fg);font-weight:500}
.tnum.over b{color:#f45b5b}
.tnum input{width:38px;background:transparent;border:0;border-bottom:1px dashed #333;
  color:var(--muted);font:inherit;text-align:right;padding:0;-moz-appearance:textfield}
.tnum input::-webkit-outer-spin-button,.tnum input::-webkit-inner-spin-button{
  -webkit-appearance:none;margin:0}
.tnum input:focus{outline:none;border-bottom-color:#4f9dff;color:var(--fg)}
.tdel{background:none;border:0;color:#333;cursor:pointer;font-size:14px;padding:0;
  line-height:1}
.tdel:hover{color:#f45b5b}
.addrow{display:grid;grid-template-columns:1fr 130px 68px auto;gap:8px;
  margin-top:16px;padding-top:14px;border-top:1px solid var(--border)}
.addrow input,.addrow select,.addrow button{background:#121212;border:1px solid #242424;
  border-radius:7px;color:var(--fg);font:inherit;font-size:13px;padding:8px 11px}
.addrow input::placeholder{color:#4a4a4a}
.addrow input:focus,.addrow select:focus{outline:none;border-color:#3ecf8e}
.addrow button{cursor:pointer;color:#3ecf8e;border-color:#24402f;
  background:rgba(62,207,142,.08);font-weight:500;white-space:nowrap}
.addrow button:hover{background:rgba(62,207,142,.16)}
.sect{font-size:10px;letter-spacing:.12em;text-transform:uppercase;color:var(--dim);
  font-family:var(--mono);margin:14px 0 2px}
.sect:first-of-type{margin-top:0}
@media(max-width:760px){
  .task{grid-template-columns:24px 24px 1fr 60px 20px;row-gap:7px}
  .task .chip{display:none}
  .task .tbar{grid-column:1/-1;order:9}
  .addrow{grid-template-columns:1fr 1fr;}
  .addrow input:first-child{grid-column:1/-1}
}
.k{font-family:var(--mono);font-size:12px;color:var(--acc)}
.empty{color:var(--dim);font-size:13px;font-family:var(--mono);padding:6px 0}
footer{margin-top:34px;color:var(--dim);font-size:11.5px;font-family:var(--mono);
  display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap}
code{font-family:var(--mono);background:#141414;border:1px solid var(--border);
  padding:2px 6px;border-radius:5px;font-size:11.5px;color:var(--muted)}
@media(max-width:640px){.big{font-size:34px}.wrap{padding:28px 16px 56px}}
</style></head><body><div class="wrap">
<header>
  <div><h1>HIC <span>OS</span></h1><div class="sub" id="sub">carregando…</div></div>
  <div class="pill"><span class="dot" id="dot"></span><span id="statusTxt">—</span></div>
</header>
<div class="grid kpi">
  <div class="card"><div class="label">Deep work hoje</div>
    <div class="big" id="work">0<small>min</small></div>
    <div class="bar"><i id="workbar" style="width:0%"></i></div>
    <div class="meta" id="workmeta">—</div></div>
  <div class="card"><div class="label">Streak</div>
    <div class="big" id="streak">0<small>dias</small></div>
    <div class="meta" id="streakmeta">—</div></div>
  <div class="card"><div class="label">Distração</div>
    <div class="big" id="dist">0<small>min</small></div>
    <div class="meta" id="distmeta">—</div></div>
  <div class="card"><div class="label">Puxões de orelha</div>
    <div class="big" id="nags">0</div>
    <div class="meta" id="nagmeta">—</div></div>
  <div class="card"><div class="label">Viés de estimativa</div>
    <div class="big" id="bias">—</div>
    <div class="meta" id="biasmeta">—</div></div>
</div>
<div class="grid">
  <div class="card wide"><div class="label">Linha do tempo do expediente</div>
    <div class="tl" id="tl"></div>
    <div class="tlx"><span id="tls">—</span><span id="tlm">—</span><span id="tle">—</span></div>
    <div class="legend">
      <span><b style="background:#3ecf8e"></b>foco</span>
      <span><b style="background:#f45b5b"></b>distração</span>
      <span><b style="background:#3a3a3a"></b>fora</span>
      <span><b style="background:#1c1c1c"></b>ausente</span>
      <span><b style="background:#8b6fd4"></b>sem visão</span>
      <span><b style="background:#b8862b"></b>não classificado</span>
      <span><b style="background:#0f0f0f;border:1px solid #222"></b>sem dado</span>
    </div></div>
</div>
<div class="grid" id="triagewrap" style="display:none">
  <div class="card wide">
    <div class="chead">
      <div class="label" style="margin:0">Domínios para triar</div>
      <div class="pmeta">o daemon não cobrou por eles — decida e ele aprende</div>
    </div>
    <div id="triage"></div>
  </div>
</div>
<div class="grid">
  <div class="card wide">
    <div class="chead">
      <div class="label" style="margin:0">Plano 3/3/3 · estimado vs real</div>
      <div class="pmeta" id="planmeta">—</div>
    </div>
    <div id="tasks"></div>
    <form class="addrow" id="addform" autocomplete="off">
      <input id="ttitle" placeholder="nova tarefa…" maxlength="160" required>
      <select id="tbucket" aria-label="categoria">
        <option value="frog">🐸 sapo</option>
        <option value="urgent" selected>urgente</option>
        <option value="maintenance">manutenção</option>
      </select>
      <input id="test" type="number" min="1" max="600" value="30" aria-label="estimativa em minutos">
      <button type="submit">adicionar</button>
    </form>
  </div>
</div>
<div class="grid">
  <div class="card"><div class="label">Últimos 14 dias</div>
    <div class="streak" id="s14"></div>
    <div class="meta" id="s14meta">—</div></div>
  <div class="card"><div class="label">Onde o tempo foi</div><div class="rows" id="apps"></div></div>
</div>
<footer>
  <span>tick a cada 60s · <code>hic status</code> · <code>hic frog</code> · <code>hic plan</code></span>
  <span id="upd">—</span>
</footer>
</div>
<script>
const COL={WORK:'#3ecf8e',DIST:'#f45b5b',OFF:'#3a3a3a',AWAY:'#1c1c1c',
           NEUTRAL:'#2a3a4a',BLIND:'#8b6fd4',LOCKED:'#1c1c1c',UNKNOWN:'#b8862b',
           OFFHOURS:'#141414'};
const $=i=>document.getElementById(i);
const hm=m=>`${Math.floor(m/60)}h${String(m%60).padStart(2,'0')}`;
const t2m=s=>{const[a,b]=s.split(':');return +a*60+ +b};
function render(d){
  const c=d.current, t=d.today;
  $('sub').textContent=`${d.window} · ${d.work_start}–${d.work_end} · ${c.app||'—'}${c.host?' · '+c.host:''}`;
  const dot=$('dot');dot.className='dot';
  const age=d.tick_age;
  let s='ocioso';
  if(age===null||age===undefined||age>180){
    s=age==null?'daemon sem batimento':`daemon parado há ${Math.floor(age/60)}min`;
    dot.classList.add('bad');
  }
  else if(d.blind_streak>=3){s='sem visão · falta Acessibilidade';dot.classList.add('bad')}
  else if(d.paused){s=`pausado ${d.paused_min}min`;dot.classList.add('warn')}
  else if(d.block.active){s=`bloco · ${d.block.task} · ${d.block.ends_in}min`;dot.classList.add('on')}
  else if(!d.sampling){s=`em silêncio · ${d.window}`;dot.classList.add('warn')}
  else if(!d.enforcing){s=`contando · ${d.window}`;dot.classList.add('warn')}
  else if(c.class==='WORK'){s='em foco';dot.classList.add('on')}
  else if(c.class==='DIST'){s='distração detectada';dot.classList.add('bad')}
  else if(c.class==='AWAY'){s='ausente';dot.classList.add('warn')}
  else if(c.off_streak>0){s=`fora há ${c.off_streak}min`;dot.classList.add(c.off_streak>=20?'bad':'warn')}
  $('statusTxt').textContent=s;

  $('work').innerHTML=`${t.work_min}<small>min</small>`;
  const lo=d.band_min||0, hi=d.band_max||480, est=d.band_state||'dentro';
  const pct=Math.min(100,100*t.work_min/Math.max(1,hi));
  $('workbar').style.width=pct+'%';
  $('workbar').style.background=
    est==='acima'?'#f45b5b':est==='dentro'?'#3ecf8e':'#f5a524';
  $('workmeta').textContent=
    est==='acima' ? `${hm(t.work_min)} · ${t.work_min-hi}min ACIMA do teto de ${hm(hi)}`
    : est==='abaixo' ? `${hm(t.work_min)} · faltam ${lo-t.work_min}min para o piso de ${hm(lo)}`
    : est==='protegido' ? `${hm(t.work_min)} · dia protegido`
    : `${hm(t.work_min)} · dentro da banda ${hm(lo)}–${hm(hi)}`;

  $('streak').innerHTML=`${d.streak}<small>dias</small>`;
  $('streakmeta').textContent=d.streak
    ? `dias seguidos DENTRO da banda ${hm(d.band_min||0)}–${hm(d.band_max||480)}`
    : `estourar o teto quebra igual ficar abaixo do piso`;

  $('dist').innerHTML=`${t.dist_min}<small>min</small>`;
  $('distmeta').textContent=(t.unknown_min?`${t.unknown_min}min não classificados · `:'')
    +(t.top_hosts.length?t.top_hosts.map(h=>`${h[0]} ${h[1]}m`).join(' · ')
                        :'nenhum site bloqueado hoje');

  $('nags').textContent=t.nags;
  $('nagmeta').textContent=(t.blind_min?`⚠ ${t.blind_min}min sem enxergar o app · `:'')
    +`${t.blocks} bloco(s) concluído(s) · ${t.away_min}min ausente`;

  const ws=t2m(d.work_start),we=t2m(d.work_end);
  const map={};d.timeline.forEach(x=>map[x.m]=x.k);
  let h='';for(let m=ws;m<we;m++){h+=`<i style="background:${COL[map[m]]||'#0f0f0f'}"></i>`}
  $('tl').innerHTML=h;
  $('tls').textContent=d.work_start;$('tle').textContent=d.work_end;
  $('tlm').textContent=String(Math.floor((ws+we)/2/60)).padStart(2,'0')+':00';

  renderTasks(d); renderTriage(d);

  const mx=Math.max(1,...d.last14.map(x=>x.work_min));
  $('s14').innerHTML=d.last14.map(x=>
    `<i class="${x.hit?'hit':(x.work_min>0?'part':'')}" title="${x.date}: ${x.work_min}min"></i>`).join('');
  const hits=d.last14.filter(x=>x.hit).length;
  $('s14meta').textContent=`${hits}/14 dias no alvo · pico ${mx}min`;

  $('apps').innerHTML=t.top_apps.length
    ? t.top_apps.map(a=>`<div class="row"><b>${a[0]}</b><s>${a[1]}m</s></div>`).join('')
    : '<div class="empty">sem dados ainda</div>';

  $('upd').textContent='atualizado '+new Date().toLocaleTimeString('pt-BR');
}
const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function renderTasks(d){
  const ts=(d.plan&&d.plan.tasks)||[], tot=d.totals||{}, B=d.buckets||{};
  $('planmeta').textContent=ts.length
    ? `${tot.feitas||0}/${tot.total||0} feitas · ${tot.estimado||0}min estimados · ${tot.real||0}min reais`
    : 'nenhuma tarefa hoje';
  if(!ts.length){
    $('tasks').innerHTML='<div class="empty">monte o dia abaixo, ou rode <code>hic plan</code> no terminal</div>';
  }else{
    $('tasks').innerHTML=ts.map(t=>{
      const est=t.estimate_min||0, real=t.actual_min||0;
      const pct=est?Math.min(100,100*real/est):0;
      const over=est&&real>est;
      const col=t.status==='done'?(over?'#f5a524':'#3ecf8e'):over?'#f45b5b':'#4f9dff';
      return `<div class="task ${t.status}" data-id="${t.id}">
        <button class="tbtn play" data-act="${t.status==='doing'?'pause':'start'}"
          title="${t.status==='doing'?'pausar cronômetro':'cronometrar esta tarefa'}"
          >${t.status==='doing'?'❚❚':'▶'}</button>
        <button class="tbtn check" data-act="done"
          title="${t.status==='done'?'reabrir':'marcar como feita'}">✓</button>
        <span class="ttl">${esc(t.title)}</span>
        <span class="chip ${t.bucket}">${B[t.bucket]||t.bucket}</span>
        <span class="tbar"><i style="width:${pct}%;background:${col}"></i></span>
        <span class="tnum ${over?'over':''}"><b>${real}</b>/<input type="number"
          min="1" max="600" value="${est}" data-act="est">m</span>
        <button class="tdel" data-act="del" title="remover">×</button>
      </div>`}).join('');
  }
  const a=d.accuracy||{};
  if(a.vies){
    $('bias').innerHTML=`${Math.round(a.vies*100)}<small>%</small>`;
    $('biasmeta').textContent=a.vies>1
      ? `você leva ${Math.round((a.vies-1)*100)}% a mais do que estima · ${a.tarefas} tarefas`
      : `você termina antes do que estima · ${a.tarefas} tarefas`;
  }else{
    $('bias').textContent='—';
    $('biasmeta').textContent='conclua uma tarefa estimada para calibrar';
  }
}
function renderTriage(d){
  const q=d.triage||[];
  $('triagewrap').style.display=q.length?'':'none';
  if(!q.length){$('triage').innerHTML='';return}
  $('triage').innerHTML=q.map(x=>`<div class="tri" data-host="${esc(x.host)}"
      data-kind="${esc(x.kind||'host')}">
      <span class="thost"><i class="kind">${x.kind==='app'?'app':'site'}</i>${esc(x.host)}</span>
      <span class="tmin">${x.min}min</span>
      <button class="tri-b work" data-act="allow">é trabalho</button>
      <button class="tri-b block" data-act="block">é distração</button>
    </div>`).join('');
}
$('triage').addEventListener('click',e=>{
  const b=e.target.closest('[data-act]'); if(!b)return;
  const row=b.closest('.tri');
  post('/api/domain/'+(b.dataset.act==='allow'?'allow':'block'),
       {host:row.dataset.host, kind:row.dataset.kind||'host'});
});
async function post(url,body){
  const r=await fetch(url,{method:'POST',cache:'no-store',
    headers:{'X-HIC':'1','Content-Type':'application/json'},
    body:JSON.stringify(body||{})});
  if(r.ok) render(await r.json()); else load();
}
$('tasks').addEventListener('click',e=>{
  const btn=e.target.closest('[data-act]'); if(!btn||btn.tagName==='INPUT')return;
  const id=btn.closest('.task').dataset.id, act=btn.dataset.act;
  if(act==='del'){post('/api/task/delete',{id})}
  else if(act==='done'){post('/api/task/done',{id})}
  else if(act==='start'){post('/api/task/start',{id})}
  else if(act==='pause'){post('/api/task/pause',{id})}
});
$('tasks').addEventListener('change',e=>{
  if(e.target.dataset.act!=='est')return;
  post('/api/task/estimate',{id:e.target.closest('.task').dataset.id,
    minutes:parseInt(e.target.value,10)||30});
});
$('addform').addEventListener('submit',e=>{
  e.preventDefault();
  const title=$('ttitle').value.trim(); if(!title)return;
  post('/api/task/add',{title,bucket:$('tbucket').value,
    estimate_min:parseInt($('test').value,10)||30});
  $('ttitle').value='';
});
$('tbucket').addEventListener('change',e=>{
  $('test').value={frog:180,urgent:30,maintenance:15}[e.target.value]||30;
});
async function load(){try{render(await(await fetch('/api/state',{cache:'no-store'})).json())}catch(e){$('sub').textContent='daemon offline'}}
load();setInterval(()=>{if(!document.activeElement||document.activeElement.tagName!=='INPUT')load()},15000);
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype):
        data = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        # O servidor so escuta em 127.0.0.1, mas qualquer pagina aberta no seu
        # navegador tambem alcanca localhost. Duas guardas baratas: exigir um
        # header custom (que forcaria preflight cross-origin, e nao respondemos
        # a OPTIONS) e recusar Origin de fora.
        if self.headers.get("X-HIC") != "1":
            return self._send(403, json.dumps({"erro": "header X-HIC ausente"}),
                              "application/json")
        origem = self.headers.get("Origin")
        if origem and origem not in (
                "http://localhost:%d" % load_cfg()["dashboard_port"],
                "http://127.0.0.1:%d" % load_cfg()["dashboard_port"]):
            return self._send(403, json.dumps({"erro": "origem recusada"}),
                              "application/json")
        try:
            n = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(n) or b"{}")
        except Exception:
            return self._send(400, json.dumps({"erro": "json invalido"}),
                              "application/json")

        path = self.path.split("?")[0]
        try:
            plan = load_plan(create=True)
            tid = body.get("id")

            if path == "/api/task/add":
                titulo = (body.get("title") or "").strip()[:160]
                if not titulo:
                    return self._send(400, json.dumps({"erro": "titulo vazio"}),
                                      "application/json")
                bucket = body.get("bucket", "urgent")
                t = new_task(plan["next_id"], titulo, bucket,
                             body.get("estimate_min"))
                plan["next_id"] += 1
                plan["tasks"].append(t)
            elif path == "/api/task/start":
                if not start_task(plan, tid):
                    return self._send(404, json.dumps({"erro": "nao existe"}),
                                      "application/json")
            elif path == "/api/task/pause":
                t = find_task(plan, tid)
                if t and t["status"] == "doing":
                    t["status"] = "todo"
            elif path == "/api/task/done":
                t = find_task(plan, tid)
                if not t:
                    return self._send(404, json.dumps({"erro": "nao existe"}),
                                      "application/json")
                t["status"] = "todo" if t["status"] == "done" else "done"
                t["done_at"] = (dt.datetime.now().isoformat(timespec="seconds")
                                if t["status"] == "done" else None)
            elif path == "/api/task/estimate":
                t = find_task(plan, tid)
                if t:
                    t["estimate_min"] = max(1, min(600, int(body.get("minutes", 30))))
                    t["overrun_notified"] = 0
            elif path == "/api/task/delete":
                plan["tasks"] = [t for t in plan["tasks"]
                                 if str(t["id"]) != str(tid)]
            elif path in ("/api/domain/allow", "/api/domain/block"):
                kind = body.get("kind", "host")
                bruto = (body.get("host") or "").strip()
                if kind == "app":
                    host = norm_app(bruto)[:120]
                    if not host:
                        return self._send(400, json.dumps({"erro": "app invalido"}),
                                          "application/json")
                else:
                    host = bruto.lower().lstrip(".")
                    if (not host or len(host) > 253 or "/" in host
                            or " " in host):
                        return self._send(400,
                                          json.dumps({"erro": "host invalido"}),
                                          "application/json")
                cfg = load_cfg()
                if kind == "app":
                    destino = ("work_apps" if path.endswith("allow")
                               else "blocked_apps")
                    outro = ("blocked_apps" if path.endswith("allow")
                             else "work_apps")
                else:
                    destino = ("work_domains" if path.endswith("allow")
                               else "blocked_domains")
                    outro = ("blocked_domains" if path.endswith("allow")
                             else "work_domains")
                cfg[outro] = [d for d in cfg.get(outro, []) if d != host]
                if host not in cfg.get(destino, []):
                    cfg.setdefault(destino, []).append(host)
                save_cfg(cfg)
                return self._send(200, json.dumps(build_state_payload(),
                                                  ensure_ascii=False),
                                  "application/json; charset=utf-8")
            else:
                return self._send(404, json.dumps({"erro": "rota"}),
                                  "application/json")

            save_plan(plan)
            self._send(200, json.dumps(build_state_payload(), ensure_ascii=False),
                       "application/json; charset=utf-8")
        except Exception as e:
            self._send(500, json.dumps({"erro": str(e)}), "application/json")

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/api/state":
            try:
                self._send(200, json.dumps(build_state_payload(),
                                           ensure_ascii=False),
                           "application/json; charset=utf-8")
            except Exception as e:
                self._send(500, json.dumps({"error": str(e)}),
                           "application/json")
        elif path in ("/", "/index.html"):
            self._send(200, DASHBOARD_HTML, "text/html; charset=utf-8")
        else:
            self._send(404, "not found", "text/plain")


def cmd_serve():
    cfg = load_cfg()
    port = int(cfg.get("dashboard_port", 7777))
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print("HIC dashboard em http://localhost:%d" % port)
    srv.serve_forever()


def cmd_dash():
    cfg = load_cfg()
    port = int(cfg.get("dashboard_port", 7777))
    url = "http://localhost:%d" % port
    detach(["open", url])
    print(url)


# ----------------------------------------------------------------- terminal

C = {"g": "\033[32m", "r": "\033[31m", "y": "\033[33m", "b": "\033[34m",
     "d": "\033[90m", "B": "\033[1m", "0": "\033[0m"}


def cmd_status():
    d = build_state_payload()
    t, c = d["today"], d["current"]
    age = d.get("tick_age")
    if age is None:
        beat = "%smonitor sem batimento%s" % (C["r"], C["0"])
    elif age > 180:
        beat = "%smonitor parado ha %dmin%s" % (C["r"], age // 60, C["0"])
    elif d.get("enforcing"):
        beat = "%samostrando + cobrando%s" % (C["g"], C["0"])
    elif d.get("sampling"):
        beat = "%scontando, sem cobrar%s" % (C["b"], C["0"])
    else:
        beat = "%svivo, em silencio%s" % (C["y"], C["0"])
    print()
    print("  %sHIC OS%s  %s%s%s  ·  %s"
          % (C["B"], C["0"], C["d"], d["window"], C["0"], beat))
    print("  " + "-" * 52)
    lo, hi = d.get("band_min", 0), d.get("band_max", 480)
    est = d.get("band_state", "dentro")
    cor = {"dentro": C["g"], "abaixo": C["y"], "acima": C["r"],
           "protegido": C["d"]}.get(est, C["0"])
    bar_n = int(20 * min(1, t["work_min"] / max(1, hi)))
    bar = "#" * bar_n + "." * (20 - bar_n)
    extra = ""
    if est == "acima":
        extra = "  %s+%dmin acima do teto%s" % (C["r"], t["work_min"] - hi, C["0"])
    elif est == "abaixo":
        extra = "  %sfaltam %dmin para o piso%s" % (C["y"], lo - t["work_min"], C["0"])
    print("  deep work   %s%s%s  %dmin%s"
          % (cor, bar, C["0"], t["work_min"], extra))
    print("  banda       %dh%02d–%dh%02d  ·  %s%s%s"
          % (lo // 60, lo % 60, hi // 60, hi % 60, cor, est.upper(), C["0"]))
    print("  streak      %s%d dias%s dentro da banda"
          % (C["b"], d["streak"], C["0"]))
    print("  distracao   %s%dmin%s   fora %dmin   ausente %dmin"
          % (C["r"] if t["dist_min"] else C["d"], t["dist_min"], C["0"],
             t["off_min"], t["away_min"]))
    print("  avisos      %d   blocos %d" % (t["nags"], t["blocks"]))
    ln = d.get("late_nudged", 0)
    if ln:
        rot = {1: "22h — boa hora de fechar", 2: "23h — ja deu",
               3: "passou da meia-noite"}.get(ln, "")
        print("  %starde%s       %s" % (C["y"], C["0"], rot))
    if d.get("mode") == "weekend":
        alvo = d.get("weekend_target_min", 180)
        feito = t["work_min"]
        cap = d.get("weekend_capped", 0)
        if cap >= 2:
            estado = "%sPASSOU %dmin DO TETO%s" % (C["r"], feito - alvo, C["0"])
        elif cap >= 1:
            estado = "%smeta batida — o resto do dia e seu%s" % (C["g"], C["0"])
        else:
            # "restantes" sugeria cota a cumprir. Nao ha piso no sabado:
            # o numero e a folga ANTES de o sistema mandar parar.
            estado = "%dmin de folga antes do teto" % max(0, alvo - feito)
        print("  fim de sem  teto de %dh%02d · %s" % (alvo // 60, alvo % 60, estado))
    if d.get("blind_streak", 0) >= 3 or t.get("blind_min", 0):
        print("  %sSEM VISAO%s   %d min sem ler o app em primeiro plano — "
              "falta permissao de Acessibilidade (hic doctor)"
              % (C["r"], C["0"], t.get("blind_min", 0)))
    print("  agora       %s%s%s %s%s"
          % (C["g"] if c["class"] == "WORK" else C["y"], c["class"], C["0"],
             c["app"] or "-", (" / " + c["host"]) if c["host"] else ""))
    if d["block"]["active"]:
        print("  bloco       %s%s%s  %dmin feitos, %dmin restantes"
              % (C["B"], d["block"]["task"], C["0"],
                 d["block"]["work_min"], d["block"]["ends_in"]))
    if c["off_streak"]:
        print("  fora ha     %s%dmin%s (nivel %d)"
              % (C["y"], c["off_streak"], C["0"], c["nag_level"]))
    if t["top_apps"]:
        print("  apps        " + "  ".join("%s %dm" % (a, n)
                                           for a, n in t["top_apps"][:4]))
    if t["top_hosts"]:
        print("  %sfugas%s       " % (C["r"], C["0"])
              + "  ".join("%s %dm" % (h, n) for h, n in t["top_hosts"][:4]))
    fila = d.get("triage") or []
    if fila:
        print("  %striar%s       %d dominio(s) sem classificacao: %s"
              % (C["y"], C["0"], len(fila),
                 ", ".join("%s (%dm)" % (x["host"], x["min"]) for x in fila[:4])))
        print("              decida em http://localhost:%d"
              % load_cfg()["dashboard_port"])
    tot = d.get("totals") or {}
    if tot.get("total"):
        print("  plano       %d/%d feitas · %dmin estimados · %dmin reais"
              % (tot["feitas"], tot["total"], tot["estimado"], tot["real"]))
        at = active_task(d.get("plan"))
        if at:
            est, real = at.get("estimate_min", 0), at.get("actual_min", 0)
            cor = C["r"] if est and real > est else C["g"]
            print("  cronometro  %s%s%s  %s%d/%dmin%s"
                  % (C["B"], at["title"], C["0"], cor, real, est, C["0"]))
    acc = d.get("accuracy") or {}
    if acc.get("vies"):
        print("  vies        voce leva %.0f%% do que estima (%d tarefas)"
              % (acc["vies"] * 100, acc["tarefas"]))
    print("  dashboard   http://localhost:%d" % load_cfg()["dashboard_port"])
    print()


def cmd_pause(argv):
    mins = int(argv[0]) if argv and argv[0].isdigit() else 30
    st = load_state()
    st["paused_until"] = time.time() + mins * 60
    save_state(st)
    print("Monitor pausado por %d min." % mins)


def cmd_resume():
    st = load_state()
    st["paused_until"] = 0
    st["off_streak"] = 0
    st["nag_level"] = 0
    save_state(st)
    print("Monitor religado.")


def cmd_focus(argv):
    cfg = load_cfg()
    on = not (argv and argv[0] in ("off", "0", "false"))
    ok = set_focus(cfg, on, "manual")
    print("Focus %s: %s" % ("ON" if on else "OFF",
                            "ok" if ok else "FALHOU (rode hic doctor)"))


def cmd_report(argv):
    cfg = load_cfg()
    n = int(argv[0]) if argv and argv[0].isdigit() else 14
    print()
    print("  %-12s %8s %8s  %s" % ("data", "foco", "distr.", "banda"))
    print("  " + "-" * 52)
    for i in range(n - 1, -1, -1):
        dd = dt.date.today() - dt.timedelta(days=i)
        d = dd.strftime("%Y-%m-%d")
        s = summarize_day(d)
        est = estado_da_banda(cfg, dd, s["work_min"])
        cor = {"dentro": C["g"], "abaixo": C["y"], "acima": C["r"]}.get(est, C["d"])
        b = banda_do_dia(cfg, dd)
        marca = {"dentro": "dentro", "abaixo": "abaixo do piso",
                 "acima": "ACIMA DO TETO", "protegido": "protegido"}[est]
        if b and est == "acima":
            marca += " (+%dmin)" % (s["work_min"] - b[1])
        print("  %-12s %7dm %7dm  %s%s%s"
              % (d, s["work_min"], s["dist_min"], cor, marca, C["0"]))
    print()


def cmd_doctor():
    cfg = load_cfg()
    print("\n  HIC — diagnostico de permissoes\n  " + "-" * 46)

    def line(name, ok, hint=""):
        mark = "%sOK %s" % (C["g"], C["0"]) if ok else "%sFALHA%s" % (C["r"], C["0"])
        print("  %-22s %s %s" % (name, mark, hint if not ok else ""))

    app = frontmost_app()
    line("app em foreground", bool(app), "conceda Acessibilidade — SEM ISSO O "
         "MONITOR FICA CEGO (mas nao te cobra a toa)")
    if app:
        print("      -> %s" % app)
    blind = load_state().get("blind_streak", 0)
    if blind:
        print("      -> %so daemon esta cego ha %d tick(s)%s"
              % (C["r"], blind, C["0"]))

    idle = idle_seconds()
    line("idle (ioreg)", idle >= 0)
    print("      -> %ds ocioso" % idle)

    host = browser_host(cfg)
    line("URL do %s" % cfg["browser_app"], bool(host),
         "abra o navegador e conceda Automacao")
    if host:
        print("      -> %s" % host)

    notify("HIC — teste", "Se voce esta vendo isso, notificacoes funcionam.",
           "Submarine")
    print("  %-22s %senviada%s (confira o canto da tela)"
          % ("notificacao", C["y"], C["0"]))

    shortcuts = {l.strip() for l in sh(["shortcuts", "list"], timeout=10).splitlines()}
    on_ok = cfg["focus_shortcut_on"] in shortcuts
    off_ok = cfg["focus_shortcut_off"] in shortcuts
    line("atalho '%s'" % cfg["focus_shortcut_on"], on_ok, "crie no app Atalhos")
    line("atalho '%s'" % cfg["focus_shortcut_off"], off_ok, "crie no app Atalhos")
    tot, oks, u_on, u_off = focus_evidence()
    line("Focus executado de fato", bool(u_on and u_on.get("ok")
                                         and u_off and u_off.get("ok")),
         "sem prova ainda — rode: hic focus on; hic focus off")
    for rotulo, r in (("ultimo ON ", u_on), ("ultimo OFF", u_off)):
        if r:
            print("      -> %s %s  %s  via %s%s" % (
                rotulo, r["ts"], "ok" if r.get("ok") else "FALHOU rc=%s" % r.get("rc"),
                r.get("source", "?"),
                ("  (%s)" % r["err"]) if r.get("err") else ""))
    if tot:
        print("      -> %d/%d chamadas recentes com sucesso" % (oks, tot))

    for lbl, plist in (("agent monitor", "com.nebuloz.hic.monitor"),
                       ("agent dashboard", "com.nebuloz.hic.dashboard")):
        out = sh(["launchctl", "list", plist], timeout=6)
        line(lbl, bool(out), "rode o install.command de novo")

    st = load_state()
    age = None
    if st.get("last_tick"):
        try:
            age = int((dt.datetime.now()
                       - dt.datetime.fromisoformat(st["last_tick"])).total_seconds())
        except Exception:
            age = None
    line("batimento do monitor", age is not None and age < 180,
         "agent parado — rode install.command de novo")
    if age is not None:
        print("      -> ultimo tick ha %ds" % age)
        if st.get("sampling"):
            print("      -> amostrando agora (%s)" % st.get("window", "-"))
        else:
            print("      -> %sem silencio: %s%s — correto, nao e falha"
                  % (C["y"], st.get("window", "-"), C["0"]))
    n_logs = len(list(LOG_DIR.glob("*.jsonl")))
    line("dias de log gravados", n_logs > 0,
         "ainda nenhum — o monitor so grava dentro do expediente")
    if n_logs:
        print("      -> %d arquivo(s), %d min hoje"
              % (n_logs, summarize_day(today_key())["work_min"]))

    if not (on_ok and off_ok):
        print("""
  Para o Focus Mode funcionar, abra o app Atalhos e crie 2 atalhos:
    1) Nome: "%s"   -> acao "Definir Foco" -> Trabalho -> Ativado
    2) Nome: "%s"  -> acao "Definir Foco" -> Trabalho -> Desativado
  Sem eles o resto do sistema continua funcionando normal.
""" % (cfg["focus_shortcut_on"], cfg["focus_shortcut_off"]))
    print()


def cmd_setup_focus():
    """Descobre atalhos de Foco que ja existem antes de mandar voce criar."""
    cfg = load_cfg()
    print("\n  HIC — configurar Modo Foco")
    print("  " + "-" * 54)

    bruto = sh(["shortcuts", "list"], timeout=20)
    atalhos = [l.strip() for l in bruto.splitlines() if l.strip()]
    if not atalhos:
        print("  %sNao consegui listar seus atalhos.%s" % (C["r"], C["0"]))
        print("  Abra o app Atalhos uma vez e rode isto de novo.\n")
        detach(["open", "-a", "Shortcuts"])
        return

    print("  %d atalho(s) na sua conta.\n" % len(atalhos))
    on, off = cfg["focus_shortcut_on"], cfg["focus_shortcut_off"]
    if on in atalhos and off in atalhos:
        print("  %sJa configurado%s: '%s' / '%s'" % (C["g"], C["0"], on, off))
        print("  Testando...")
        ok1 = set_focus(cfg, True, "setup_test")
        time.sleep(1.5)
        ok2 = set_focus(cfg, False, "setup_test")
        print("  ligar: %s   desligar: %s\n"
              % ("OK" if ok1 else "FALHOU", "OK" if ok2 else "FALHOU"))
        return

    liga = re.compile(r"(focus|foco|dnd|perturb)", re.I)
    on_re = re.compile(r"\b(on|lig\w*|ativ\w*|start|inicia\w*)\b", re.I)
    off_re = re.compile(r"\b(off|deslig\w*|desativ\w*|stop|encerr\w*|fim)\b", re.I)
    cands = [a for a in atalhos if liga.search(a)]

    if not cands:
        print("  Nenhum atalho de Foco encontrado. Crie dois, uma vez so:\n")
        print("    1) Novo atalho -> acao \"Definir Foco\"")
        print("       escolha o Foco que voce usa -> Ativado")
        print("       renomeie para: %s%s%s" % (C["B"], on, C["0"]))
        print("    2) Igual, mas -> Desativado")
        print("       renomeie para: %s%s%s\n" % (C["B"], off, C["0"]))
        print("  Se preferir outros nomes, aponte no config:")
        print("    hic config  ->  focus_shortcut_on / focus_shortcut_off\n")
        print("  Abrindo o app Atalhos...")
        detach(["open", "-a", "Shortcuts"])
        return

    print("  %sEncontrei atalhos que parecem ser de Foco:%s" % (C["y"], C["0"]))
    for i, a in enumerate(cands, 1):
        pista = ("liga?" if on_re.search(a) else
                 "desliga?" if off_re.search(a) else "")
        print("    %d. %-42s %s%s%s" % (i, a, C["d"], pista, C["0"]))
    print("\n  Aponte o config para eles (Enter para pular):")
    try:
        a = input("    numero do que LIGA o foco: ").strip()
        b = input("    numero do que DESLIGA:     ").strip()
    except EOFError:
        return
    mudou = False
    if a.isdigit() and 1 <= int(a) <= len(cands):
        cfg["focus_shortcut_on"] = cands[int(a) - 1]; mudou = True
    if b.isdigit() and 1 <= int(b) <= len(cands):
        cfg["focus_shortcut_off"] = cands[int(b) - 1]; mudou = True
    if not mudou:
        print("  Nada alterado.\n"); return
    save_cfg(cfg)
    print("\n  Salvo: '%s' / '%s'"
          % (cfg["focus_shortcut_on"], cfg["focus_shortcut_off"]))
    print("  Testando...")
    ok1 = set_focus(cfg, True, "setup_test")
    time.sleep(1.5)
    ok2 = set_focus(cfg, False, "setup_test")
    print("  ligar: %s   desligar: %s\n"
          % ("OK" if ok1 else "FALHOU", "OK" if ok2 else "FALHOU"))


HELP = """
  HIC OS — disciplina de foco no macOS

    hic status          resumo do dia
    hic dash            abre o mini-app no navegador (lista clicavel)
    hic plan            ritual matinal 3/3/3 com estimativas
    hic task            lista as tarefas de hoje
    hic task add "X" 45 [frog|urgent|maintenance]
    hic task start 2    cronometra a tarefa #2
    hic task done 2     conclui e mostra estimado vs real
    hic task est 2 90   corrige a estimativa
    hic frog "tarefa" 90    inicia bloco de deep work (min opcional)
    hic done            encerra o bloco atual
    hic pause 30        silencia o monitor por N minutos
    hic resume          religa o monitor
    hic setup-focus     procura seus atalhos de Foco e configura sozinho
    hic focus on|off    liga/desliga o Focus Mode
    hic report 14       tabela dos ultimos N dias
    hic doctor          testa permissoes do macOS
    hic reclassify 7    reprocessa os logs com o config atual
    hic scrub           apaga dominios privados do historico
    hic config          abre o config.json
    hic logs            caminho dos logs
"""


def main():
    ensure_dirs()
    load_cfg()          # cria config.json default no primeiro uso
    argv = sys.argv[1:]
    cmd = argv[0] if argv else "status"
    rest = argv[1:]
    if cmd == "tick":
        cmd_tick()
    elif cmd in ("status", "st"):
        cmd_status()
    elif cmd == "serve":
        cmd_serve()
    elif cmd in ("dash", "dashboard", "open"):
        cmd_dash()
    elif cmd == "plan":
        cmd_plan()
    elif cmd in ("task", "tasks", "t", "ls"):
        cmd_task(rest)
    elif cmd in ("frog", "block", "start"):
        cmd_frog(rest)
    elif cmd in ("done", "stop", "end"):
        cmd_done()
    elif cmd == "pause":
        cmd_pause(rest)
    elif cmd == "resume":
        cmd_resume()
    elif cmd == "focus":
        cmd_focus(rest)
    elif cmd in ("setup-focus", "setupfocus", "focus-setup"):
        cmd_setup_focus()
    elif cmd == "report":
        cmd_report(rest)
    elif cmd == "doctor":
        cmd_doctor()
    elif cmd in ("reclassify", "recalc", "reclassificar"):
        cmd_reclassify(rest)
    elif cmd in ("scrub", "limpar", "privacidade"):
        cmd_scrub(rest)
    elif cmd == "config":
        load_cfg()
        detach(["open", "-t", str(CFG_PATH)])
        print(CFG_PATH)
    elif cmd == "logs":
        ensure_dirs()
        print(LOG_DIR)
    else:
        print(HELP)


if __name__ == "__main__":
    main()
