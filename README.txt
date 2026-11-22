MONTAGE STUDIO
==============

>>> BUILD_EXE.bat : fabrique la VRAIE application (MontageStudio.exe + installateur)
    Résultat dans dist\ :
      - dist\MontageStudio\MontageStudio.exe   (l'app, à lancer directement)
      - dist\MontageStudio_Setup.exe + .bin     (l'installateur complet : app, FFmpeg, modèles OCR,
                                               moteur CUDA, polices, musiques)
    Aucune licence, aucune clé : l'app est complète dès l'installation.
    1er build : 15-30 min.

>>> PUBLIER_INSTALLATEUR.bat : met l'installateur en ligne et copie le LIEN à donner à tes clients.
    Le lien ne change jamais : https://github.com/camraa/montage-studio-maj/releases/tag/installateur
    À relancer après chaque BUILD_EXE.bat.

>>> PUBLIER_MAJ.bat : envoie une MISE À JOUR (quelques Mo).
    Toutes les apps installées la téléchargent toutes seules au lancement suivant,
    puis bouton vert "Mise à jour prête — Redémarrer". L'app n'accepte que les paquets venant
    de ton dépôt GitHub, avec une empreinte vérifiée.
    Si une version plante au démarrage, l'app revient automatiquement à la précédente.

>>> GitHub : le code est dans ton dépôt privé camraa/montage-studio. Sur un nouveau PC :
    GitHub Desktop -> Clone -> montage-studio, puis BUILD_EXE.bat. Rien d'autre à copier.
    Après des modifs : Commit -> Push (et Pull sur l'autre PC).
    Le téléchargement et les mises à jour vont dans un 2e dépôt PUBLIC : camraa/montage-studio-maj
    (créé tout seul la 1re fois).

Modes : Cup, Ranked Reload, Ranked Battle Royale, Arène Box Fight (rang + manches),
        Créatif 1v1 (score des matchs lu en haut de l'écran).

>>> STUDIO.bat : l'interface de montage (s'ouvre dans le navigateur)
    Bibliothèque de tes recs, timeline éditable (coupes, segments), cartons modifiables,
    musique par carton, miniatures YouTube auto, file d'attente de rendu.
    Raccourcis : Espace lecture, S couper, Suppr supprimer, A ajouter, Ctrl+S, Ctrl+Z, Ctrl+R.

Interface façon macOS : fenêtre sans cadre avec les boutons rouge (fermer), orange (réduire)
    et vert (agrandir). On déplace la fenêtre en attrapant une zone vide de la barre du haut,
    double-clic dessus = agrandir / restaurer.
    Pour revenir au cadre Windows classique : Affichage > Fenêtre façon Mac (décocher), puis relancer.

Lanceurs sans interface (montage 100 % auto) :
  MONTAGE_CUP.bat             -> récap points + avancement de la cup avant chaque partie
  MONTAGE_RANKED_RELOAD.bat   -> rang + ELO gagné en gros entre chaque game
  MONTAGE_RANKED_BR.bat       -> idem en Battle Royale
  MONTAGE_BOX_ARENA.bat       -> Arène Box Fight : rang + victoires/défaites par match
  MONTAGE_CREATIF_1V1.bat     -> Créatif 1v1 : score de chaque match

Tu peux choisir plusieurs vidéos d'un coup (Ctrl+clic) : elles sont montées l'une après l'autre.
Chaque montage s'appelle "[PRÉ-UPLOAD] <nom> - <mode> 4K.mp4" (dans Vidéos), et le rec
d'origine est rangé dans "Vidéos\Vidéos brutes" une fois le montage réussi.

Musique : sur les cartons + quelques secondes de gameplay, puis elle s'efface. Elle baisse
toute seule quand tu parles ou que le jeu fait du bruit, et remonte quand c'est calme.
Musiques : intro.mp3 / outro.mp3 + tout ce qui est dans le dossier musiques\ (lofi, synthwave,
trap, house, epic, composées par code = libres de droits). Ajoute tes propres musiques libres de
droit dans musiques\ (mp3/wav/ogg/m4a/flac) : elles seront tirées au hasard entre les games.
Polices : Luckiest Guy + Anton (libres, dossier polices\), style Fortnite.

Ce qui est coupé : salon / matchmaking / chargement, début du bus, creux de plus de 5 min
sans kill ni palier de top, spectate de fin de game.

Le rang et le % de progression sont lus dans le salon entre les games (Bronze I ... Unreal).
L'ELO gagné = différence de progression entre le salon d'avant et celui d'après la game.

Réglages : config.json (bus_skip_s, dead_gap_s, résolution, débit...)
Refaire le scan d'une vidéo : supprimer son dossier dans work\

Miniatures : onglet "Miniatures YouTube" du studio -> 4 variantes -> Exporter -> Vidéos\Miniatures.
Chaque rendu crée aussi un .txt à côté du montage : titre proposé + chapitres YouTube.
