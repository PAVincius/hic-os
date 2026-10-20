"""Gera test/fixtures/parity.json rodando o classify_from do hic.py (a referência) em muitas sondas."""
import importlib.util, itertools, json, pathlib, random, sys

root = pathlib.Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("hic", root / "hic.py")
hic = importlib.util.module_from_spec(spec); spec.loader.exec_module(hic)

cfg = {
    "away_after_min": 45, "browser_app": "Google Chrome",
    "work_apps": ["Code", "Cursor", "Terminal", "Slack"],
    "blocked_apps": ["Steam", "Netflix"], "neutral_apps": ["Finder", "Spotify"],
    "work_domains": ["github.com", "localhost", "docs.google.com"],
    "blocked_domains": ["youtube.com", "x.com"],
    "private_domains": ["secret.example"], "private_patterns": [r"\.adult$", r"bad[("],
    "unknown_domain_policy": "log", "unknown_app_policy": "log",
}
apps = ["Code", "cursor", "Terminal‎", " Slack ", "Steam", "Netflix", "Finder", "Spotify", "Google Chrome",
        "Mystery App", "", "loginwindow", "ScreenSaverEngine"]
hosts = ["", "github.com", "gist.github.com", "notgithub.com", "docs.google.com", "google.com", "youtube.com",
         "m.youtube.com", "x.com", "foo.x.com", "box.com", "secret.example", "a.secret.example", "site.adult",
         "randomsite.io", ".github.com", "LOCALHOST", "bad[x.com"]
idles = [0, 30, 2699, 2700, 3600]
rows = []
policies = [("log", "log"), ("block", "block"), ("allow", "allow")]
for (dp, ap), app, host, idle, locked, outside in itertools.product(
        policies, apps, hosts, idles, [False, True], [False, True]):
    if random.Random(f"{app}{host}{idle}{dp}{locked}{outside}").random() > 0.22:
        continue  # amostra determinística
    c = dict(cfg, unknown_domain_policy=dp, unknown_app_policy=ap)
    k, a, h = hic.classify_from(app, host, idle, c, locked=locked, fora_da_janela=outside)
    rows.append({"cfg": {"unknown_domain_policy": dp, "unknown_app_policy": ap},
                 "in": {"app": app, "host": host, "idleSec": idle, "locked": locked, "outsideWindow": outside},
                 "out": {"klass": k, "app": a, "host": h}})
out = {"cfg": cfg, "cases": rows}
(pathlib.Path(__file__).parent.parent / "test/fixtures/parity.json").write_text(json.dumps(out, ensure_ascii=False))
print(len(rows), "casos")
