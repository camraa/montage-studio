"""Clé de signature des mises à jour automatiques — À GARDER POUR TOI.

  python keygen.py --init     crée la paire de clés (une seule fois, sur le PC qui publie les mises à jour)

licence_privee/cle_privee.pem signe les paquets de mise à jour (PUBLIER_MAJ.bat).
license_pub.py contient la clé PUBLIQUE intégrée à l'app : elle vérifie qu'une mise à jour vient bien de toi.
license_pub.py va sur GitHub ; licence_privee/ ne va JAMAIS sur GitHub (il est dans .gitignore).
"""
import sys
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

HERE = Path(__file__).resolve().parent
PRIV_DIR = HERE / "licence_privee"
PRIV = PRIV_DIR / "cle_privee.pem"
PUB_PY = HERE / "license_pub.py"


def b64e(b):
    import base64
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def init(force=False):
    if PRIV.exists() and not force:
        key = serialization.load_pem_private_key(PRIV.read_bytes(), None)
    elif PUB_PY.exists() and not force:
        # autre PC : la clé publique vient du dépôt GitHub, on ne la remplace surtout pas
        print("[INFO] license_pub.py présent (venu du dépôt) : build OK.")
        print("       Pour publier des mises à jour depuis ce PC, copie-y le dossier licence_privee\\ de ton PC principal.")
        return None
    else:
        PRIV_DIR.mkdir(exist_ok=True)
        key = Ed25519PrivateKey.generate()
        PRIV.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                           serialization.NoEncryption()))
        (PRIV_DIR / "LISEZ-MOI.txt").write_text(
            "cle_privee.pem = ta clé secrète qui signe les mises à jour automatiques.\n"
            "NE LA PARTAGE JAMAIS, ne la mets pas sur GitHub, et fais-en une sauvegarde (clé USB, cloud perso).\n"
            "Si tu la perds, les apps déjà installées refuseront tes futures mises à jour : il faudra réinstaller.\n",
            encoding="utf-8")
        print(f"[OK] nouvelle clé de signature : {PRIV}")
    pub = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    PUB_PY.write_text(f'PUBLIC_KEY = "{b64e(pub)}"\n', encoding="utf-8")
    return key


if __name__ == "__main__":
    if "--init" in sys.argv:
        init(force="--force" in sys.argv)
    else:
        print(__doc__)
