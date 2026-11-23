"""Publie une mise à jour de Montage Studio sur GitHub Releases (lancé par PUBLIER_MAJ.bat).

  python publish.py                      version suivante automatique, notes = dernier commit
  python publish.py 1.0.1 "Correction du scan Battle Royale"
  python publish.py 1.0.1 --notes-file notes.txt [--min-base 1.0.0] [--no-upload]
  python publish.py --version-build      écrit _version.py pour BUILD_EXE (= dernière version publiée)

1. écrit la version dans _version.py (pas dans git : rien à committer après une publication)
2. compile le code (.pyc) + interface/polices/musiques -> update-<version>.zip (quelques Mo)
3. crée latest.json (empreinte SHA-256) et envoie les deux fichiers dans une release GitHub (outil gh)

  python publish.py --installateur
     met dist/MontageStudio_Setup.exe (+ .bin) en ligne dans la release fixe "installateur"
     -> lien à donner aux clients : https://github.com/<dépôt>/releases/tag/installateur
"""
import argparse
import hashlib
import json
import py_compile
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from updater import APP_MODULES, BASE_VERSION, normalize_repo  # noqa: E402

ASSETS = ["studio", "polices", "musiques", "intro.mp3", "outro.mp3", "icone.ico", "icone.png"]


def repo_name():
    p = HERE / "update_repo.txt"
    if p.exists() and normalize_repo(p.read_text(encoding="utf-8")):
        repo = normalize_repo(p.read_text(encoding="utf-8"))
        p.write_text(repo + "\n", encoding="utf-8")
        return repo
    sys.exit("[ERREUR] update_repo.txt manquant (lance BUILD_EXE.bat une fois, il te le demande)")


def set_version(v):
    (HERE / "_version.py").write_text(f'VERSION = "{v}"\n', encoding="utf-8")


def _vt(v):
    return tuple(int(x) for x in v.split("."))


def local_version():
    m = re.search(r'"(\d+\.\d+\.\d+)"', (HERE / "_version.py").read_text(encoding="utf-8")) \
        if (HERE / "_version.py").exists() else None
    return m.group(1) if m else BASE_VERSION


def published_version(repo):
    """Plus haute version publiée sur GitHub (tags vX.Y.Z) ; None si inconnue."""
    exe = shutil.which("gh")
    if not exe:
        return None
    r = subprocess.run([exe, "release", "list", "--repo", repo, "--limit", "100", "--json", "tagName"],
                       capture_output=True, text=True)
    if r.returncode:
        return None
    tags = [t["tagName"][1:] for t in json.loads(r.stdout or "[]") if re.fullmatch(r"v\d+\.\d+\.\d+", t["tagName"])]
    return max(tags, key=_vt) if tags else None


def next_version(repo):
    best = max([v for v in (local_version(), published_version(repo)) if v], key=_vt)
    a, b, c = _vt(best)
    return f"{a}.{b}.{c + 1}"


def last_commit_subject():
    try:
        r = subprocess.run(["git", "-C", str(HERE), "log", "-1", "--pretty=%s"], capture_output=True, text=True)
        return r.stdout.strip() if r.returncode == 0 else ""
    except OSError:
        return ""


def build_package(version, out_dir):
    tmp = Path(tempfile.mkdtemp())
    code = tmp / "code.zip"
    with zipfile.ZipFile(code, "w", zipfile.ZIP_DEFLATED) as z:
        for m in sorted(APP_MODULES):
            src = HERE / f"{m}.py"
            pyc = tmp / f"{m}.pyc"
            py_compile.compile(str(src), cfile=str(pyc), doraise=True,
                               invalidation_mode=py_compile.PycInvalidationMode.UNCHECKED_HASH)
            z.write(pyc, f"{m}.pyc")
    pkg = out_dir / f"update-{version}.zip"
    with zipfile.ZipFile(pkg, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(code, "code.zip")
        for a in ASSETS:
            p = HERE / a
            if p.is_dir():
                for f in sorted(p.rglob("*")):
                    if f.is_file() and "__pycache__" not in f.parts:
                        z.write(f, "assets/" + f.relative_to(HERE).as_posix())
            elif p.exists():
                z.write(p, f"assets/{a}")
    shutil.rmtree(tmp, ignore_errors=True)
    return pkg


def gh(*args, check=True):
    exe = shutil.which("gh")
    if not exe:
        return None
    return subprocess.run([exe, *args], check=check)


INSTALL_TAG = "installateur"
INSTALL_NOTES = """## Installer Montage Studio

1. Télécharge **tous** les fichiers ci-dessous (`MontageStudio_Setup.exe` et les `.bin`) dans le **même dossier**.
2. Lance `MontageStudio_Setup.exe`.

Windows 10/11 64 bits. Carte NVIDIA conseillée (l'analyse marche sans, mais plus lentement).
Les mises à jour arrivent ensuite toutes seules dans l'app.
"""


def ensure_repo(repo):
    if repo.endswith("/montage-studio"):        # dépôt du code lui-même (public) : existe forcément
        return
    if gh("repo", "view", repo, check=False).returncode != 0:
        print(f"[GITHUB] création du dépôt public {repo} (il ne contiendra que l'installateur et les mises à jour)")
        gh("repo", "create", repo, "--public", "--add-readme", "--description", "Téléchargement et mises à jour de Montage Studio")


def publish_installer():
    repo = repo_name()
    files = sorted((HERE / "dist").glob("MontageStudio_Setup*.exe")) + sorted((HERE / "dist").glob("MontageStudio_Setup*.bin"))
    if not any(f.suffix == ".exe" for f in files):
        sys.exit("[ERREUR] dist/MontageStudio_Setup.exe introuvable : lance d'abord BUILD_EXE.bat")
    total = sum(f.stat().st_size for f in files)
    print(f"[INFO] {len(files)} fichier(s), {total / 1e9:.2f} Go à envoyer : ça peut prendre un moment")
    if not shutil.which("gh"):
        sys.exit(f"[ERREUR] outil GitHub (gh) absent. Envoi manuel : https://github.com/{repo}/releases/new?tag={INSTALL_TAG}")
    ensure_repo(repo)
    gh("release", "delete", INSTALL_TAG, "--repo", repo, "--yes", "--cleanup-tag", check=False)
    gh("release", "create", INSTALL_TAG, *map(str, files), "--repo", repo, "--latest=false",
       "--title", "Télécharger Montage Studio", "--notes", INSTALL_NOTES)
    link = f"https://github.com/{repo}/releases/tag/{INSTALL_TAG}"
    print(f"[OK] installateur en ligne. Lien à donner à tes clients :\n     {link}")
    try:
        subprocess.run(["clip"], input=link.encode(), check=False)
        print("     (lien copié dans le presse-papiers)")
    except OSError:
        pass


def main():
    if "--installateur" in sys.argv:
        return publish_installer()
    if "--version-build" in sys.argv:          # BUILD_EXE : l'exe prend la dernière version publiée
        v = max([x for x in (local_version(), published_version(repo_name())) if x], key=_vt)
        set_version(v)
        return print(f"     version de l'app : {v}")
    ap = argparse.ArgumentParser()
    ap.add_argument("version", nargs="?", default="auto")
    ap.add_argument("notes", nargs="?", default="")
    ap.add_argument("--notes-file")
    ap.add_argument("--min-base", default=BASE_VERSION)
    ap.add_argument("--no-upload", action="store_true")
    a = ap.parse_args()
    repo = repo_name()
    v = next_version(repo) if a.version in ("auto", "") else a.version.lstrip("v")
    if not re.fullmatch(r"\d+\.\d+\.\d+", v):
        sys.exit("[ERREUR] version au format X.Y.Z (ex : 1.0.1)")
    notes = Path(a.notes_file).read_text(encoding="utf-8") if a.notes_file else (a.notes or last_commit_subject())
    print(f"[MAJ] version {v} : {notes or '(sans notes)'}")

    set_version(v)
    out = HERE / "dist" / "maj" / f"v{v}"
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    pkg = build_package(v, out)
    blob = pkg.read_bytes()
    sha = hashlib.sha256(blob).hexdigest()
    manifest = {"version": v, "url": f"https://github.com/{repo}/releases/download/v{v}/{pkg.name}",
                "sha256": sha, "min_base": a.min_base, "notes": notes, "size": len(blob)}
    (out / "latest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[OK] paquet {pkg.name} ({len(blob) / 1e6:.1f} Mo) + latest.json -> {out}")

    if a.no_upload:
        return
    if not shutil.which("gh"):
        print("[INFO] outil GitHub (gh) absent : envoi manuel.\n"
              f"  1. Ouvre https://github.com/{repo}/releases/new?tag=v{v}\n"
              f"  2. Glisse les 2 fichiers de {out}\n  3. Clique 'Publish release'")
        return
    ensure_repo(repo)
    gh("release", "create", f"v{v}", str(pkg), str(out / "latest.json"), "--repo", repo,
       "--title", f"Montage Studio {v}", "--notes", notes or f"Montage Studio {v}")
    print(f"[OK] mise à jour {v} publiée : toutes les apps la recevront à leur prochain lancement")


if __name__ == "__main__":
    main()
