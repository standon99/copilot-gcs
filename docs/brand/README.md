# Project icon

The original icon combines a navigation arrow, protective shield and amber
waypoint, using the app's existing teal/dark palette. It is included under the
project's MIT license.

![Project icon](../../web/public/icon.png)

- [SVG source](../../web/public/icon.svg): app header and README.
- [512 px PNG](../../web/public/icon.png): general use.
- [32 px favicon](../../web/public/favicon.png) and
  [180 px touch icon](../../web/public/apple-touch-icon.png): browser shortcuts.
- [GitHub social preview](social-preview.png): 1280 × 640 PNG, under 1 MB.

![Repository social preview](social-preview.png)

GitHub provides a **Settings → General → Social preview → Edit → Upload an
image** setting for repository link previews. Upload `social-preview.png` using
an account with repository settings access. GitHub permits a first image upload
for public repositories; private repositories can update an image uploaded
previously. The setting is unavailable for this private repository as checked
on 2026-09-17, so the preview is supplied here for future use. The icon is visible
in the repository README. This does not change the owner's profile avatar or
GitHub's standard repository-type glyph.
[GitHub instructions](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/customizing-your-repositorys-social-media-preview).

## Regenerate PNGs

The SVGs are editable source; PNGs are deterministic exports. From the repository
root with Node 22+ on PATH:

```sh
npm install --prefix .tools/brand-render --no-save @resvg/resvg-js
node docs/brand/render.cjs
```

Keep the mark in `social-preview.svg` aligned with `web/public/icon.svg` when
changing its geometry. The renderer is optional, ignored tooling; it adds no
runtime dependency to the app. Inspect exports and refresh affected screenshots
before committing a visible branding change.
