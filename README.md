# Montage Studio

Montage automatique des recs Fortnite : Cup, Ranked Reload, Ranked Battle Royale,
Arène Box Fight (rang + manches) et Créatif 1v1 (score lu en haut de l'écran).

## Les fichiers à double-cliquer
| Fichier | Quand | Durée |
|---|---|---|
| **STUDIO.bat** | Tester une modif : **Pull origin** puis double-clic. L'app s'ouvre directement depuis le code. | quelques s |
| *(rien)* | **Mises à jour automatiques** : chaque envoi de code publie une mise à jour toute seule (voir plus bas). | ~1 min |
| **PUBLIER_MAJ.bat** | Secours : publier à la main depuis ton PC (version et notes automatiques). | ~30 s |
| **BUILD_EXE.bat** | Seulement quand une nouvelle bibliothèque arrive (je te le dis). `BUILD_EXE.bat clean` = build complet. | 1er build long, ensuite plus court |
| **PUBLIER_INSTALLATEUR.bat** | Après un BUILD_EXE : fabrique l'installateur et le met en ligne (lien copié) : https://github.com/camraa/montage-studio/releases/tag/installateur | quelques min |

Une mise à jour peut ajouter de nouveaux fichiers de code : pas besoin de réinstaller l'app pour ça.

## Mises à jour automatiques
Le dépôt est public : chaque envoi de code publie une mise à jour dans ses **Releases** (GitHub Actions,
aucun jeton à régler). Les apps la récupèrent au lancement et toutes les 20 min.
Pour envoyer du code sans publier : mettre le mot-clé no-maj entre crochets dans le message du commit.
Lien de téléchargement pour les clients : https://github.com/camraa/montage-studio/releases/tag/installateur

## Sur un nouveau PC
GitHub Desktop → Clone → `camraa/montage-studio`, puis **STUDIO.bat** (installe ce qu'il faut au 1er lancement).
**BUILD_EXE.bat** seulement si tu veux l'exe sur ce PC.

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

## Pour les réseaux
- **Shorts TikTok** (Rendu → Créer les Shorts) : les meilleurs enchaînements de kills en vidéos verticales
  1080x1920 avec gros titre auto et **sous-titres de ta voix** mot par mot → `Vidéos\Shorts`.
  Tes **réactions au son** (voix qui monte d'un coup) comptent aussi : bonus pour un fight où tu réagis,
  et une grosse réaction sans kill peut devenir un Short. Piste du micro réglable (onglet Rendu → Shorts).
- **Texte YouTube** (touche Y, ou bouton « Texte YouTube » dans la file après un rendu) : 3 titres,
  description avec chapitres détaillés (kills, points / ELO par game), tags — boutons Copier.
  Aussi enregistré dans `<montage>.txt` à côté de la vidéo.
- **Progression** (onglet Progression, touche 5) : chaque rec analysé s'ajoute tout seul — rang en fin de
  session (Ranked), points par cup, kills, jours de grind. « Miniature de progression » ouvre une miniature
  préremplie (rang de départ du grind, rang actuel, jour du grind, ELO de la dernière session).
- **Sous-titres YouTube** : option « Fichier .srt » dans l'onglet Rendu (à envoyer avec la vidéo).
- **Compteur en direct** pendant les games : partie, kills (s'allume à chaque kill), points ou rang.
- **Carton de fin de Cup** avec le graphique des points partie par partie.
- **Studio de bannières** (onglet Bannières) : miniatures Cup (classement, mystère #?, duo, gros titre),
  Ranked (grind, avant/après), bannière de chaîne, écran de fin, bandeau de stream, bannière X.
  Ton skin est détouré depuis le rec (curseur sur ton skin → « Détourer »). Tes vraies icônes de rangs / cups :
  dépose-les en PNG dans le dossier « Mes icônes » (elles remplacent les badges dessinés).

## Dans l'app
- Raccourcis : Espace lecture, S couper, Suppr supprimer, A ajouter, Ctrl+S, Ctrl+Z, Ctrl+R.
- Fenêtre façon Mac : boutons rouge / orange / vert, double-clic sur la barre du haut pour agrandir.
  Cadre Windows classique : Affichage → Fenêtre façon Mac (décocher), puis relancer.
- Refaire l'analyse d'un rec : Projet → Refaire le scan complet.
