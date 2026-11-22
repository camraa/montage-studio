"""Version libre : plus de clé de licence ni de filigrane.

Module conservé pour compatibilité avec les anciens appels (status, watermark...).
"""


def status():
    return {"licensed": True, "name": "Version complète", "plan": "libre"}


def activate(key=""):
    return True, status()


def deactivate():
    return status()


def watermark(img):
    return img
