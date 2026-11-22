"""Publie une mise à jour de Montage Studio sur GitHub Releases (lancé par PUBLIER_MAJ.bat).

  python publish.py 1.0.1 "Correction du scan Battle Royale"
  python publish.py 1.0.1 --notes-file notes.txt [--min-base 1.0.0] [--no-upload]

1. met la version dans common.py
2. compile le code (.pyc) + interface/polices/musiques -> update-<version>.zip (quelques Mo)
3. signe le paquet avec licence_privee/cle_privee.pem (les apps refusent tout paquet non signé)
4. crée latest.json et envoie les deux fichiers dans une release GitHub (outil gh)
"""
import argparse
import base64
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
from updater import APP_MODULES, BASE_VERSION, PREFIX, normalize_repo  # noqa: E402

ASSETS = ["studio", "polices", "musiques", "intro.mp3", "outro.mp3", "icone.ico", "icone.png"]


def repo_name():
    p = HERE / "update_repo.txt"
    if p.exists() and normalize_repo(p.read_text(encoding="utf-8")):
        repo = normalize_repo(p.read_text(encoding="utf-8"))
        p.write_text(repo + "\n", encoding="utf-8")
        return repo
    sys.exit("[ERREUR] update_repo.txt manquant (lance BUILD_EXE.bat une fois, il te le demande)")


def set_version(v):
    p = HERE / "common.py"
    s = p.read_text(encoding="utf-8")
    s2 = re.sub(r'^APP_VERSION = "[^"]*"', f'APP_VERSION = "{v}"', s, count=1, flags=re.M)
    p.write_text(s2, encoding="utf-8")


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


def sign(msg):
    from cryptography.hazmat.primitives import serialization
    key_p = HERE / "licence_privee" / "cle_privee.pem"
    if not key_p.exists():
        sys.exit("[ERREUR] licence_privee/cle_privee.pem introuvable : c'est elle qui signe les mises à jour")
    key = serialization.load_pem_private_key(key_p.read_bytes(), None)
    return base64.urlsafe_b64encode(key.sign(msg)).decode().rstrip("=")


def gh(*args, check=True):
    exe = shutil.which("gh")
    if not exe:
        return None
    return subprocess.run([exe, *args], check=check)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("version")
    ap.add_argument("notes", nargs="?", default="")
    ap.add_argument("--notes-file")
    ap.add_argument("--min-base", default=BASE_VERSION)
    ap.add_argument("--no-upload", action="store_true")
    a = ap.parse_args()
    v = a.version.lstrip("v")
    if not re.fullmatch(r"\d+\.\d+\.\d+", v):
        sys.exit("[ERREUR] version au format X.Y.Z (ex : 1.0.1)")
    notes = Path(a.notes_file).read_text(encoding="utf-8") if a.notes_file else a.notes
    repo = repo_name()

    set_version(v)
    out = HERE / "dist" / "maj" / f"v{v}"
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    pkg = build_package(v, out)
    blob = pkg.read_bytes()
    sha = hashlib.sha256(blob).hexdigest()
    manifest = {"version": v, "url": f"https://github.com/{repo}/releases/download/v{v}/{pkg.name}",
                "sha256": sha, "min_base": a.min_base, "notes": notes, "size": len(blob)}
    manifest["sig"] = sign(f"{PREFIX}|{v}|{sha}|{a.min_base}".encode())
    (out / "latest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[OK] paquet {pkg.name} ({len(blob) / 1e6:.1f} Mo) + latest.json signés -> {out}")

    if a.no_upload:
        return
    if not shutil.which("gh"):
        print("[INFO] outil GitHub (gh) absent : envoi manuel.\n"
              f"  1. Ouvre https://github.com/{repo}/releases/new?tag=v{v}\n"
              f"  2. Glisse les 2 fichiers de {out}\n  3. Clique 'Publish release'")
        return
    if gh("repo", "view", repo, check=False).returncode != 0:
        print(f"[GITHUB] création du dépôt public {repo} (il ne contiendra que les mises à jour)")
        gh("repo", "create", repo, "--public", "--add-readme", "--description", "Mises à jour de Montage Studio")
    gh("release", "create", f"v{v}", str(pkg), str(out / "latest.json"), "--repo", repo,
       "--title", f"Montage Studio {v}", "--notes", notes or f"Montage Studio {v}")
    print(f"[OK] mise à jour {v} publiée : toutes les apps la recevront à leur prochain lancement")


if __name__ == "__main__":
    main()
