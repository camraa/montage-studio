# Montage Studio

Montage automatique des recs Fortnite : Cup, Ranked Reload, Ranked Battle Royale,
Arène Box Fight (rang + manches) et Créatif 1v1 (score lu en haut de l'écran).

## Les fichiers à double-cliquer
| Fichier | Rôle |
|---|---|
| **BUILD_EXE.bat** | Fabrique l'app et l'installateur complet → `dist\MontageStudio_Setup.exe` (+ `.bin`). 1er build : 15-30 min. |
| **PUBLIER_INSTALLATEUR.bat** | Met l'installateur en ligne et copie le lien pour tes clients : https://github.com/camraa/montage-studio-maj/releases/tag/installateur |
| **PUBLIER_MAJ.bat** | Envoie une mise à jour (quelques Mo), reçue automatiquement par toutes les apps installées. |
| **STUDIO.bat** | Lance l'app directement depuis le code, sans build (pour tester tes modifs). |

## Sur un nouveau PC
GitHub Desktop → Clone → `camraa/montage-studio`, puis **BUILD_EXE.bat**. Rien d'autre à copier.
Après des modifs : **Commit** → **Push**, puis **Pull** sur l'autre PC.

## Ce que fait le montage
- Coupe le salon, le matchmaking, le début du bus, les creux de plus de 5 min sans kill ni palier de top, et le spectate de fin.
- Carton récap avant chaque game : points et avancement de la Cup, ou rang + ELO gagné en Ranked.
- Musique sur les cartons, qui baisse toute seule quand tu parles ou que le jeu fait du bruit.
  Ajoute tes musiques libres de droits dans `musiques\` (mp3, wav, ogg, m4a, flac).
- Cup : musique stressante sur les 2 dernières minutes de chaque partie (dossier `musiques\fin_de_zone\`),
  plus discrète et qui baisse sous ta voix. Réglable ou désactivable dans l'onglet Rendu.
- Toutes les musiques fournies sont composées par code : libres de droits, utilisables sur YouTube.
- Rendu 4K 60 i/s sur la carte graphique : `[PRÉ-UPLOAD] <nom> - <mode> 4K.mp4` dans Vidéos ;
  le rec d'origine est rangé dans `Vidéos\Vidéos brutes`. Un `.txt` avec titre + chapitres YouTube est créé à côté.
- Miniatures : onglet Miniatures → 4 variantes → Exporter vers `Vidéos\Miniatures`.

## Dans l'app
- Raccourcis : Espace lecture, S couper, Suppr supprimer, A ajouter, Ctrl+S, Ctrl+Z, Ctrl+R.
- Fenêtre façon Mac : boutons rouge / orange / vert, double-clic sur la barre du haut pour agrandir.
  Cadre Windows classique : Affichage → Fenêtre façon Mac (décocher), puis relancer.
- Refaire l'analyse d'un rec : Projet → Refaire le scan complet.
