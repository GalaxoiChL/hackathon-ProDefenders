import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig, type Connect, type Plugin } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// Rădăcina repo-ului: manifest.json folosește căi relative la ea (ex. "output/melbourne_ro.mp4").
const REPO = fileURLToPath(new URL("..", import.meta.url));
// Folderele din repo pe care frontend-ul le citește direct, fără să copiem videoclipuri.
// demo/media/: clipurile publicate pentru echipă (pipeline/publish_media.py); le servim tot de aici, în bucăți de 4 MB.
const SERVED_DIRS: Record<string, string> = {
  output: "output",
  assets: "assets",
  data: "data",
  media: "demo/media",
};

const CHUNK_BYTES = 4 * 1024 * 1024;

const MIME: Record<string, string> = {
  ".mp4": "video/mp4",
  ".webm": "video/webm",
  ".json": "application/json",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
};

/** Servește un fișier din repo, cu suport pentru Range (fără el nu merge derularea în video). */
function serveRepoFile(dir: string): Connect.NextHandleFunction {
  const root = path.join(REPO, dir);
  return (req, res, next) => {
    const rel = decodeURIComponent((req.url ?? "/").split("?")[0]);
    const file = path.join(root, rel);
    if (!file.startsWith(root) || !fs.existsSync(file) || !fs.statSync(file).isFile()) return next();

    const size = fs.statSync(file).size;
    const type = MIME[path.extname(file).toLowerCase()] ?? "application/octet-stream";
    const range = /bytes=(\d*)-(\d*)/.exec(req.headers.range ?? "");
    if (range) {
      const start = range[1] ? Number(range[1]) : 0;
      // bucăți de cel mult 4 MB: altfel fiecare video ține ocupată o conexiune până se descarcă tot,
      // iar browserul are doar 6 per server; Compare cu 5 video-uri rămânea cu unul negru
      const end = Math.min(range[2] ? Number(range[2]) : size - 1, start + CHUNK_BYTES - 1, size - 1);
      res.writeHead(206, {
        "Content-Type": type,
        "Content-Length": end - start + 1,
        "Content-Range": `bytes ${start}-${end}/${size}`,
        "Accept-Ranges": "bytes",
        "Cache-Control": "no-store",
      });
      fs.createReadStream(file, { start, end }).pipe(res);
    } else {
      res.writeHead(200, { "Content-Type": type, "Content-Length": size, "Accept-Ranges": "bytes", "Cache-Control": "no-store" });
      fs.createReadStream(file).pipe(res);
    }
  };
}

function serveRepoDirs(): Plugin {
  const mount = (use: Connect.Server["use"]) =>
    Object.entries(SERVED_DIRS).forEach(([url, dir]) => use(`/${url}`, serveRepoFile(dir)));
  return {
    name: "serve-repo-dirs",
    configureServer: (server) => mount(server.middlewares.use.bind(server.middlewares)),
    configurePreviewServer: (server) => mount(server.middlewares.use.bind(server.middlewares)),
  };
}

// Serverul din backend/ (uvicorn backend.app:app --port 8000). Dacă nu rulează, frontend-ul citește direct fișierele.
const BACKEND = process.env.BACKEND_URL ?? "http://localhost:8000";
const proxy = { "/api": { target: BACKEND, changeOrigin: true } };

const escapeRe = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

/**
 * Pentru `npm run build:demo`: pune JS-ul și CSS-ul direct în index.html.
 * O pagină deschisă de pe disc (file://) nu are voie să încarce module JS separate, dar le poate rula inline.
 */
function inlineIntoHtml(): Plugin {
  return {
    name: "inline-into-html",
    apply: "build",
    enforce: "post",
    generateBundle(_, bundle) {
      const html = Object.values(bundle).find((f) => f.type === "asset" && f.fileName.endsWith(".html"));
      if (!html || html.type !== "asset") return;
      let page = String(html.source);
      for (const [name, file] of Object.entries(bundle)) {
        if (file.type === "chunk") {
          const code = file.code.replace(/<\/script/gi, "<\\/script");
          page = page.replace(new RegExp(`<script[^>]*src="[^"]*${escapeRe(name)}"[^>]*></script>`), () => `<script type="module">${code}</script>`);
          delete bundle[name];
        } else if (name.endsWith(".css")) {
          page = page.replace(new RegExp(`<link[^>]*href="[^"]*${escapeRe(name)}"[^>]*>`), () => `<style>${String(file.source)}</style>`);
          delete bundle[name];
        }
      }
      html.source = page;
    },
  };
}

export default defineConfig(({ mode }) =>
  mode === "demo"
    ? {
        // demo/index.html: tot site-ul într-un fișier, lângă demo/media/ (care nu se șterge la build)
        plugins: [react(), tailwindcss(), inlineIntoHtml()],
        base: "./",
        build: { outDir: "../demo", emptyOutDir: false, copyPublicDir: false, cssCodeSplit: false, modulePreload: false, assetsInlineLimit: 100_000_000 },
      }
    : {
        plugins: [react(), tailwindcss(), serveRepoDirs()],
        server: { port: 5173, open: true, proxy },
        preview: { proxy },
      },
);
