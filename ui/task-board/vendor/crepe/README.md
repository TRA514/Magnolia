# Vendored Milkdown Crepe 7.5.0

Self-contained, no-build, offline-capable vendoring of the Milkdown Crepe WYSIWYG
markdown editor for the task-board static app. Served as plain static files — no
runtime CDN, no bundler at runtime.

- **Library:** `@milkdown/crepe`
- **Exact version:** `7.5.0`
- **Vendored on:** 2026-06-10
- **Self-contained:** YES. `crepe.bundle.js` has **0 external/runtime imports** — every
  dependency (`@milkdown/*`, all `@codemirror/*`, all `@lezer/*`, `@floating-ui/*`,
  `atomico`, `@sindresorhus/*`, `@uiw/codemirror-themes`) is inlined by esbuild. This is a
  real vendor, NOT a CDN-fallback shim. The CSS files likewise have 0 remaining `@import`
  statements (sibling/internal imports inlined).

> Note: the esm.sh `?bundle` build (`https://esm.sh/@milkdown/crepe@7.5.0?bundle`) was
> evaluated first and rejected — it returns a ~764-byte re-export shim whose `import`
> statements point at relative esm.sh paths (`/@milkdown/prose/...`, `/node/process.mjs`,
> `/@milkdown/crepe@7.5.0/es2020/crepe.bundle.mjs`). Those resolve only against esm.sh at
> runtime, so it is not offline-capable. We built our own bundle with esbuild instead.

## Files

| File | Bytes | Source (npm package `@milkdown/crepe@7.5.0`) |
|---|---|---|
| `crepe.bundle.js` | 4,270,317 | esbuild bundle of `export { Crepe } from '@milkdown/crepe'` |
| `common.css` | 30,912 | `lib/theme/common/style.css` (sibling `@import`s inlined) |
| `frame.css` | 6,604 | `lib/theme/frame/style.css` (`_internal/classic-common.css` inlined) |

Source URLs (for reference / provenance):
- npm: `https://registry.npmjs.org/@milkdown/crepe/-/crepe-7.5.0.tgz`
- esm.sh (CSS originals): `https://esm.sh/@milkdown/crepe@7.5.0/theme/common/style.css`,
  `https://esm.sh/@milkdown/crepe@7.5.0/theme/frame/style.css`

## API surface (Crepe 7.5.0, from `lib/types/core/crepe.d.ts`)

`Crepe` is exported as a named export. Its public class API is:
`constructor(config)`, `create(): Promise<Editor>`, `destroy(): Promise<Editor>`,
`get editor(): Editor`, `setReadonly(value): this`, and `getMarkdown(): string` —
so `getMarkdown` exists and is the read path.
There is **no** listener/`.on(...)` method or command/`.action(...)` method directly on
`Crepe`; change events and commands must go through the underlying Milkdown editor exposed
via `crepe.editor` (e.g. `crepe.editor.action(...)` with the `@milkdown/kit/listener`
plugin), or the consumer can fall back to synthetic keystrokes + polling `getMarkdown()`.

## Regeneration

```bash
# one-time dev tool (esbuild) — not a runtime build
cd /tmp && rm -rf crepe-vendor && mkdir crepe-vendor && cd crepe-vendor
npm init -y
# crepe declares only `atomico` as a runtime dep; its @milkdown/@codemirror/@lezer
# imports are expected to be provided, so install the full tree explicitly:
npm i @milkdown/crepe@7.5.0 \
  @milkdown/core@7.5.0 @milkdown/ctx@7.5.0 @milkdown/exception@7.5.0 @milkdown/kit@7.5.0 \
  @milkdown/plugin-indent@7.5.0 @milkdown/plugin-tooltip@7.5.0 \
  @milkdown/preset-commonmark@7.5.0 @milkdown/preset-gfm@7.5.0 \
  @milkdown/prose@7.5.0 @milkdown/transformer@7.5.0 @milkdown/utils@7.5.0 \
  @codemirror/autocomplete @codemirror/commands @codemirror/lang-css @codemirror/lang-html \
  @codemirror/lang-javascript @codemirror/language @codemirror/lint @codemirror/search \
  @codemirror/state @codemirror/view \
  @floating-ui/core @floating-ui/dom @floating-ui/utils \
  @lezer/common @lezer/cpp @lezer/css @lezer/highlight @lezer/html @lezer/java \
  @lezer/javascript @lezer/json @lezer/lr @lezer/markdown @lezer/php @lezer/python \
  @lezer/rust @lezer/sass @lezer/xml @lezer/yaml \
  @sindresorhus/slugify @sindresorhus/transliterate @uiw/codemirror-themes

printf "export { Crepe } from '@milkdown/crepe';\n" > entry.js
npx --yes esbuild entry.js --bundle --format=esm --target=es2020 --outfile=crepe.bundle.js

# stylesheets (esbuild inlines the relative @import siblings):
npx --yes esbuild node_modules/@milkdown/crepe/lib/theme/common/style.css \
  --bundle --outfile=common.css
npx --yes esbuild node_modules/@milkdown/crepe/lib/theme/frame/style.css \
  --bundle --outfile=frame.css

# copy crepe.bundle.js, common.css, frame.css into ui/task-board/vendor/crepe/
# verify self-contained: grep -cE "from ?[\"']https?://" crepe.bundle.js  # must be 0
```
