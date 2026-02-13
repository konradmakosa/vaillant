# Wanna PWA

Aplikacja PWA do monitorowania temperatury wody i uruchamiania grzania CWU.

**URL**: https://wanna-app.pages.dev

## Easter Eggs

Animowane overlay z przezroczystością, wyświetlane losowo co 30s.

### Jak dodać nowego easter egga

1. Przygotuj animację w formacie `.mov` (ProRes 4444 z alpha, 720×1280)
2. Skonwertuj do animated WebP:

```bash
ffmpeg -i wanna/eggs/NUMER.mov -vcodec libwebp -lossless 0 -q:v 70 -loop 0 -an wanna/eggs/NUMER.webp
```

3. Pliki nazywaj kolejno: `1.webp`, `2.webp`, `3.webp` itd.
4. Deploy:

```bash
wrangler pages deploy wanna --project-name wanna-app --branch main --commit-dirty=true
```

### Parametry ffmpeg

| Parametr | Znaczenie |
|---|---|
| `-vcodec libwebp` | Kodek WebP |
| `-lossless 0` | Kompresja stratna (mniejszy plik) |
| `-q:v 70` | Jakość 0-100 (70 = dobry balans) |
| `-loop 0` | Zapętlaj animację |
| `-an` | Bez audio |

### Wskazówki

- Format źródłowy: **ProRes 4444** (`.mov`) — obsługuje pełne 8-bit alpha
- Rozmiar: **720×1280** (jak tło wideo)
- WebP z alpha jest lżejszy od GIF i ma płynną przezroczystość
- Pliki `.mov` nie trafiają do repo (`.gitignore`)
