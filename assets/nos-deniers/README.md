# Nos Deniers — version 2

Signature : **Du budget voté à l’euro dépensé**

## Fichiers

- `nos-deniers-icone.svg` — icône seule, 200 × 200. À utiliser dans une carte du portail, comme les autres icônes LexMachine.
- `nos-deniers-logo.svg` — composition verticale avec le nom et la signature, 440 × 318.
- `nos-deniers-horizontal.svg` — composition horizontale avec le nom et la signature, 580 × 200.

Les trois SVG sont autonomes, avec un extérieur transparent. Les textes des deux logos sont convertis en tracés : aucune police, image ou ressource externe n’est nécessaire.

## Intégration

Copier ce dossier dans le répertoire d’assets du site, puis adapter le chemin :

```html
<img
  src="/assets/nos-deniers-v2/nos-deniers-logo.svg"
  width="440"
  height="318"
  alt="Nos Deniers — Du budget voté à l’euro dépensé"
  style="max-width: 100%; height: auto;"
>
```

Pour une carte où le nom et la signature existent déjà en HTML, utiliser `nos-deniers-icone.svg` avec `width="200"`, `height="200"` et `alt=""`.

## Charte graphique

- Bleu marine : `#173A55`
- Corail : `#D84B50`
- Disque bleu pâle : `#EDF4FA`
- Nom : `#08183F`
- Blanc : `#FFFFFF`
- Typographie des textes vectorisés : Inter, axe optique 32, nom en graisse 700 et signature en graisse 400, comme le portail.

Le dessin reprend exactement l’icône de la première proposition : fronton centré et trois colonnes, sans loupe. Le nom et la signature sont conservés.

Les fichiers du site et la première proposition n’ont pas été modifiés.
