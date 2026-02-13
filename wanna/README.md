# Wanna PWA

Aplikacja PWA do monitorowania temperatury wody i uruchamiania grzania CWU.

**URL**: https://wanna-app.pages.dev

## Easter Eggs

Animowane overlay z przezroczystością (VP9 alpha), losowane co 20s.
Prawdopodobieństwo wyświetlenia: `1/(n+1)` gdzie n = liczba eggów.
Każdy egg odtwarza się raz do końca i znika.

### Jak dodać nowego easter egga

1. Przygotuj animację w formacie `.mov` (ProRes 4444 z alpha, 720×1280)
2. Skonwertuj do WebM (VP9 z alpha):

```bash
ffmpeg -i wanna/eggs/NUMER.mov -c:v libvpx-vp9 -pix_fmt yuva420p -b:v 1M -auto-alt-ref 0 -an wanna/eggs/NUMER.webm
```

3. Pliki nazywaj kolejno: `1.webm`, `2.webm`, `3.webm` itd.
4. Deploy:

```bash
wrangler pages deploy wanna --project-name wanna-app --branch main
```

### Parametry ffmpeg

| Parametr | Znaczenie |
|---|---|
| `-c:v libvpx-vp9` | Kodek VP9 (obsługuje alpha) |
| `-pix_fmt yuva420p` | Format pikseli z kanałem alpha |
| `-b:v 1M` | Bitrate ~1Mbps |
| `-auto-alt-ref 0` | Wymagane dla alpha w VP9 |
| `-an` | Bez audio |

### Wskazówki

- Format źródłowy: **ProRes 4444** (`.mov`) — pełne 8-bit alpha
- Rozmiar: **720×1280** (jak tło wideo)
- **Nie używaj animated WebP** — ffmpeg produkuje ghosting z alpha
- WebM z VP9 alpha: brak ghostingu, mniejsze pliki (~200-600KB), event `ended`
- Pliki `.mov` nie trafiają do repo (`.gitignore`)
