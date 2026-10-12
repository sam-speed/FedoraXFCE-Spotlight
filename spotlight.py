#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Spotlight per Fedora XFCE (rofi): app, file e cartelle in un'unica lista.

Ordine dei risultati (sempre rispettato, la ricerca non lo rimescola):
  1. applicazioni (con la loro icona)
  2. file e cartelle "normali" (con l'icona del tipo di file, come in Thunar)
  3. file nascosti / di configurazione / temporanei

Indicizza per intero "/srv/archivio/Archivio LB" + la tua home + i dischi montati.
La ricerca ignora maiuscole e minuscole.

Uso:
    spotlight.py            apre il launcher (da associare a Ctrl+Spazio)
    spotlight.py --reindex  ricostruisce l'indice dei file
"""

import fcntl
import html
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path

# ═══════════════════════════ CONFIGURAZIONE ═══════════════════════════

ARCHIVIO = "/srv/archivio/Archivio LB"   # indicizzato per intero, senza limiti

# "tipo"   = ogni file ha l'icona del suo tipo (PDF, immagine, video...), come in Thunar
# "thunar" = il logo di Thunar su tutti i file (le cartelle restano cartelle)
ICONA_FILE = "tipo"

ICON_THEME = ""         # es. "Papirus-Dark". Vuoto = tema icone del desktop
RINNOVA_OGNI = 300      # secondi dopo i quali l'indice viene aggiornato in background
MAX_VOCI = 500_000      # tetto di sicurezza sul numero di file indicizzati

# ═════════════════════════════════════════════════════════════════════

HOME = Path.home()
UTENTE = os.environ.get("USER") or HOME.name
CACHE = Path(os.environ.get("XDG_CACHE_HOME") or HOME / ".cache") / "spotlight"
INDICE = CACHE / "indice.bin"
TEMA = CACHE / "tema.rasi"

# Cartelle pesanti o inutili da non indicizzare nella home
ESCLUDI_HOME = {
    ".cache", ".git", "node_modules", "__pycache__", ".venv", ".npm", ".cargo",
    ".rustup", ".var", ".mozilla", ".thunderbird", ".steam", ".wine", "flatpak",
    "Trash", ".Trash", "Cache", "GPUCache", "Code Cache", "CacheStorage",
}

# profondita: livelli massimi (None = illimitato)
# nascosti:   livelli massimi dentro cartelle nascoste/di configurazione (None = illimitato)
# etichetta:  come mostrare il percorso (None = percorso assoluto)
RADICI = [
    {"path": ARCHIVIO, "etichetta": "", "profondita": None, "nascosti": None, "escludi": set()},
    {"path": str(HOME), "etichetta": "~", "profondita": 8, "nascosti": 4, "escludi": ESCLUDI_HOME},
    {"path": f"/run/media/{UTENTE}", "etichetta": None, "profondita": 5, "nascosti": 3, "escludi": set()},
    {"path": f"/media/{UTENTE}", "etichetta": None, "profondita": 5, "nascosti": 3, "escludi": set()},
    {"path": "/mnt", "etichetta": None, "profondita": 5, "nascosti": 3, "escludi": set()},
]

# ═══════════════════════════════ TEMA ═══════════════════════════════════

TEMA_RASI = r"""
/* Spotlight - tema viola per rofi.
   Colore d'accento: #8b5cf6 (se lo cambi, cambia anche il gradiente piu' sotto). */
* {
    accent:      #8b5cf6;
    bg:          #14101dF2;
    campo:       #ffffff14;
    fg:          #ece8f7;
    fg-dim:      #8f85ad;

    font: "Sans 13";
    background-color: transparent;
    text-color: @fg;
    margin: 0;
    padding: 0;
    spacing: 0;
}

window {
    location: center;
    anchor: center;
    y-offset: -120px;
    width: 720px;
    background-color: @bg;
    border: 1px;
    border-color: #8b5cf680;
    border-radius: 22px;
}

mainbox {
    padding: 14px;
    spacing: 12px;
    children: [ "inputbar", "listview" ];
}

inputbar {
    padding: 14px 18px;
    spacing: 14px;
    background-color: @campo;
    border-radius: 14px;
    children: [ "prompt", "entry" ];
}

prompt {
    expand: false;
    vertical-align: 0.5;
    text-color: @accent;
    font: "DejaVu Sans Bold 20";
}

entry {
    expand: true;
    vertical-align: 0.5;
    font: "Sans 16";
    placeholder: "Cerca app, file e cartelle…";
    placeholder-color: @fg-dim;
}

listview {
    lines: 8;
    columns: 1;
    spacing: 4px;
    scrollbar: false;
    fixed-height: false;
    dynamic: true;
    cycle: false;
}

element {
    padding: 8px 12px;
    spacing: 14px;
    border-radius: 12px;
    orientation: horizontal;
}

element normal.normal,
element alternate.normal,
element normal.active,
element normal.urgent {
    background-color: #ffffff0a;
}

element selected.normal,
element selected.active,
element selected.urgent {
    background-color: #a78bfa;
    text-color: #1a1030;
    border: 0px 0px 0px 4px;
    border-color: #ffffff;
}

element-icon {
    size: 34px;
    vertical-align: 0.5;
}

element-text {
    vertical-align: 0.5;
    text-color: inherit;
    highlight: bold underline;
}
"""

# ═══════════════════════════════ UTILITÀ ════════════════════════════════

CTRL = re.compile(r"[\x00-\x1f\x7f]")


def esc(testo):
    return html.escape(testo, quote=False)


def stacca(cmd):
    """Avvia un processo completamente staccato da questo script."""
    subprocess.Popen(
        cmd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def notifica(titolo, testo=""):
    if shutil.which("notify-send"):
        stacca(["notify-send", "-i", "system-search", titolo, testo])


def riga_rofi(testo, icona, meta=None):
    """Riga in formato dmenu di rofi: testo + icona (+ parole chiave nascoste)."""
    s = f"{testo}\0icon\x1f{icona}"
    if meta:
        s += f"\x1fmeta\x1f{meta}"
    return s.encode("utf-8")


# ═══════════════════════════════ APPLICAZIONI ═══════════════════════════


def cartelle_dati():
    dirs = [Path(os.environ.get("XDG_DATA_HOME") or HOME / ".local/share")]
    dirs += [
        Path(d)
        for d in (os.environ.get("XDG_DATA_DIRS") or "/usr/local/share:/usr/share").split(":")
        if d
    ]
    for extra in (HOME / ".local/share/flatpak/exports/share", Path("/var/lib/flatpak/exports/share")):
        if extra not in dirs:
            dirs.append(extra)
    return dirs


def leggi_desktop(percorso):
    d, dentro = {}, False
    try:
        with open(percorso, encoding="utf-8", errors="replace") as f:
            for linea in f:
                linea = linea.strip()
                if not linea or linea.startswith("#"):
                    continue
                if linea.startswith("["):
                    if dentro:
                        break
                    dentro = linea == "[Desktop Entry]"
                    continue
                if dentro and "=" in linea:
                    k, v = linea.split("=", 1)
                    d[k.strip()] = v.strip()
    except OSError:
        return None
    return d


def lingue_utente():
    for var in ("LC_ALL", "LC_MESSAGES", "LANG"):
        v = os.environ.get(var)
        if v and v != "C":
            base = v.split(".")[0].split("@")[0]
            return [base, base.split("_")[0]]
    return []


def carica_app():
    lingue = lingue_utente()

    def loc(d, chiave):
        for lg in lingue:
            v = d.get(f"{chiave}[{lg}]")
            if v:
                return v
        return d.get(chiave, "")

    visti, apps = set(), []
    for base in cartelle_dati():
        appdir = base / "applications"
        if not appdir.is_dir():
            continue
        for p in sorted(appdir.rglob("*.desktop")):
            id_app = p.relative_to(appdir).as_posix().replace("/", "-")
            if id_app in visti:
                continue
            visti.add(id_app)  # una voce nascosta in una cartella prioritaria oscura le altre
            d = leggi_desktop(p)
            if not d or d.get("Type") != "Application":
                continue
            if d.get("NoDisplay", "").lower() == "true" or d.get("Hidden", "").lower() == "true":
                continue
            solo = d.get("OnlyShowIn")
            if solo and "XFCE" not in solo.split(";"):
                continue
            if "XFCE" in d.get("NotShowIn", "").split(";"):
                continue
            tryexec = d.get("TryExec")
            if tryexec and not shutil.which(tryexec):
                continue
            nome = loc(d, "Name")
            if not nome:
                continue
            comando = d.get("Exec", "")
            primo = os.path.basename(comando.split()[0]) if comando.split() else ""
            meta = " ".join(
                x for x in (loc(d, "GenericName"), loc(d, "Keywords").replace(";", " "), primo) if x
            )
            apps.append(
                {
                    "nome": nome,
                    "icona": d.get("Icon") or "application-x-executable",
                    "file": str(p),
                    "id": id_app,
                    "terminal": d.get("Terminal", "").lower() == "true",
                    "exec": comando,
                    "meta": CTRL.sub(" ", meta),
                }
            )
    apps.sort(key=lambda a: a["nome"].casefold())
    return apps


def avvia_app(app):
    if app["terminal"]:
        term = shutil.which("xfce4-terminal")
        if term:
            try:
                cmd = shlex.split(re.sub(r"%[a-zA-Z]", "", app["exec"]))
                if cmd:
                    return stacca([term, "-x"] + cmd)
            except ValueError:
                pass
    if shutil.which("gio"):
        stacca(["gio", "launch", app["file"]])
    else:
        stacca(["gtk-launch", app["id"]])


# ═══════════════════════════════ FILE ═══════════════════════════════════

_ICONE = {
    "image-x-generic": "jpg jpeg png gif webp bmp tif tiff svg heic heif avif ico raw cr2 cr3 nef arw dng raf orf rw2 psd xcf afphoto afdesign",
    "video-x-generic": "mp4 mkv mov avi webm m4v mts m2ts mxf wmv flv mpg mpeg 3gp braw drp",
    "audio-x-generic": "mp3 wav flac ogg oga m4a aac opus wma aif aiff mid midi",
    "application-pdf": "pdf",
    "x-office-document": "doc docx odt rtf pages",
    "x-office-spreadsheet": "xls xlsx ods csv numbers",
    "x-office-presentation": "ppt pptx odp key",
    "package-x-generic": "zip 7z rar tar gz tgz xz bz2 zst deb rpm",
    "media-optical": "iso img",
    "text-x-script": "sh py js ts rb pl php lua c h cpp java rs go json xml html css yml yaml toml conf cfg ini",
    "text-x-generic": "txt md log tex srt",
}
ICONE_PER_ESTENSIONE = {ext: icona for icona, exts in _ICONE.items() for ext in exts.split()}

NOMI_STRANI = {
    "thumbs.db", "desktop.ini", "lost+found", "__macosx", "$recycle.bin",
    "system volume information", "@eadir", "#recycle", "__pycache__", "node_modules",
}
SUFFISSI_STRANI = (
    ".tmp", ".temp", ".bak", ".swp", ".swo", ".lock", ".part", ".crdownload",
    ".pyc", ".pyo", ".orig", ".rej", ".dmp", "~",
)


def e_strano(nome_cf):
    """Nascosto, di configurazione, temporaneo o di sistema."""
    return (
        nome_cf.startswith(".")
        or nome_cf.startswith("~$")
        or nome_cf in NOMI_STRANI
        or nome_cf.endswith(SUFFISSI_STRANI)
    )


def icona_file(nome, e_cartella):
    if e_cartella:
        return "folder"
    if ICONA_FILE == "thunar":
        return "org.xfce.thunar"
    ext = nome.rsplit(".", 1)[-1].casefold() if "." in nome else ""
    return ICONE_PER_ESTENSIONE.get(ext, "text-x-generic")


def scansiona(spec, voci):
    radice = spec["path"]
    if not os.path.isdir(radice):
        return
    max_prof, max_nasc = spec["profondita"], spec["nascosti"]
    escludi, et = spec["escludi"], spec["etichetta"]
    pila = [(radice, 1, 0, "")]  # cartella, profondità dei figli, livelli "strani", percorso relativo
    while pila and len(voci) < MAX_VOCI:
        cartella, prof, h, rel = pila.pop()
        if et is None:
            padre = cartella
        elif rel:
            padre = f"{et}/{rel}" if et else rel
        else:
            padre = et
        try:
            with os.scandir(cartella) as it:
                elenco = list(it)
        except OSError:
            continue
        for e in elenco:
            nome = e.name
            if nome in escludi or CTRL.search(nome):
                continue
            try:
                nome.encode("utf-8")
            except UnicodeEncodeError:
                continue
            ncf = nome.casefold()
            strano = h > 0 or e_strano(ncf)
            try:
                e_cartella = e.is_dir()
            except OSError:
                e_cartella = False
            voci.append((1 if strano else 0, prof, ncf, nome, padre, e.path, e_cartella))
            if not e_cartella or e.is_symlink():
                continue
            if max_prof is not None and prof >= max_prof:
                continue
            nh = h + 1 if strano else 0
            if strano and max_nasc is not None and nh >= max_nasc:
                continue
            pila.append((e.path, prof + 1, nh, f"{rel}/{nome}" if rel else nome))


def costruisci_indice():
    voci, radici_viste = [], []
    for spec in RADICI:
        rp = os.path.realpath(spec["path"])
        if any(rp == v or rp.startswith(v + os.sep) for v in radici_viste):
            continue
        radici_viste.append(rp)
        scansiona(spec, voci)
    # prima i normali, poi gli "strani"; dentro ciascun gruppo le cartelle più
    # vicine alla radice, poi ordine alfabetico senza distinguere maiuscole
    voci.sort(key=lambda v: (v[0], v[1], v[2], v[4]))
    return voci


def riga_voce(v):
    strano, _prof, _ncf, nome, padre, _path, e_cartella = v
    testo = esc(nome)
    if strano:
        testo = f'<span alpha="70%">{testo}</span>'
    if padre:
        testo += f'  <span alpha="50%" size="small">{esc(padre)}</span>'
    return riga_rofi(testo, icona_file(nome, e_cartella))


def reindicizza(bassa_priorita=True):
    CACHE.mkdir(parents=True, exist_ok=True)
    with open(CACHE / "lock", "w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            return  # un'altra indicizzazione è già in corso
        if bassa_priorita:
            try:
                os.nice(15)
            except OSError:
                pass
        voci = costruisci_indice()
        tmp = INDICE.with_suffix(".tmp")
        with open(tmp, "wb") as f:
            for v in voci:
                f.write(riga_voce(v) + b"\x1e" + v[5].encode("utf-8") + b"\n")
        os.replace(tmp, INDICE)


def carica_file():
    try:
        blob = INDICE.read_bytes()
    except OSError:
        return [], []
    righe, percorsi = [], []
    for linea in blob.split(b"\n"):
        if linea:
            r, _, p = linea.partition(b"\x1e")
            righe.append(r)
            percorsi.append(p.decode("utf-8"))
    return righe, percorsi


def indice_vecchio():
    try:
        return time.time() - INDICE.stat().st_mtime > RINNOVA_OGNI
    except OSError:
        return True


def apri_percorso(p):
    if os.path.isdir(p):
        thunar = shutil.which("thunar")
        stacca([thunar, p] if thunar else ["xdg-open", p])
    elif os.path.exists(p):
        stacca(["xdg-open", p])
    else:
        notifica("Spotlight", f"Non esiste più (disco scollegato?):\n{p}")


# ═══════════════════════════════ MAIN ═══════════════════════════════════


def scrivi_tema():
    CACHE.mkdir(parents=True, exist_ok=True)
    try:
        if TEMA.read_text(encoding="utf-8") == TEMA_RASI:
            return
    except OSError:
        pass
    TEMA.write_text(TEMA_RASI, encoding="utf-8")


def main():
    if "--reindex" in sys.argv:
        return reindicizza()

    scrivi_tema()
    apps = carica_app()
    righe_file, percorsi = carica_file()

    if not INDICE.exists():
        notifica("Spotlight", "Prima indicizzazione dei file in corso…")
        reindicizza(bassa_priorita=False)
        righe_file, percorsi = carica_file()
    elif indice_vecchio():
        cmd = [sys.executable, os.path.abspath(__file__), "--reindex"]
        if shutil.which("ionice"):
            cmd = ["ionice", "-c3"] + cmd
        stacca(cmd)

    righe = [riga_rofi(esc(a["nome"]), a["icona"], a["meta"]) for a in apps] + righe_file
    dati = b"\n".join(righe) + b"\n"

    cmd = [
        "rofi", "-dmenu",
        "-i",                      # ignora maiuscole/minuscole
        "-matching", "normal",
        "-no-sort",                # mantiene la gerarchia app > file > config
        "-no-custom",
        "-format", "i",            # restituisce l'indice della riga scelta
        "-markup-rows",
        "-show-icons",
        "-p", "⌕",
        "-theme", str(TEMA),
        # rofi non ha la selezione del testo: Ctrl+A svuota il campo, così
        # puoi riscrivere subito (come "seleziona tutto + scrivi"). Il cursore
        # a inizio riga passa su Ctrl+Home (Home è già usato da rofi per la lista).
        "-kb-move-front", "Control+Home",
        "-kb-clear-line", "Control+a,Control+w",
    ]
    if ICON_THEME:
        cmd += ["-icon-theme", ICON_THEME]

    try:
        res = subprocess.run(cmd, input=dati, stdout=subprocess.PIPE)
    except FileNotFoundError:
        notifica("Spotlight", "rofi non è installato: sudo dnf install rofi")
        return
    if res.returncode != 0:
        return
    try:
        i = int(res.stdout.strip())
    except ValueError:
        return
    if i < 0:
        return
    if i < len(apps):
        avvia_app(apps[i])
    else:
        apri_percorso(percorsi[i - len(apps)])


if __name__ == "__main__":
    main()
