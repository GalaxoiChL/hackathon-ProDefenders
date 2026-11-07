import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig, type Connect, type Plugin } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// Rădăcina repo-ului: manifest.json folosește căi relative la ea (ex. "output/melbourne_ro.mp4").
const REPO = fileURLToPath(new URL("..", import.meta.url));
// Folderele din repo pe care frontend-ul le citește direct, fără să copiem videoclipuri.
const SERVED_DIRS = ["output", "assets", "data"];

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
  const mount = (use: Connect.Server["use"]) => SERVED_DIRS.forEach((d) => use(`/${d}`, serveRepoFile(d)));
  return {
    name: "serve-repo-dirs",
    configureServer: (server) => mount(server.middlewares.use.bind(server.middlewares)),
    configurePreviewServer: (server) => mount(server.middlewares.use.bind(server.middlewares)),
  };
}

// Serverul din backend/ (uvicorn backend.app:app --port 8000). Dacă nu rulează, frontend-ul citește direct fișierele.
const BACKEND = process.env.BACKEND_URL ?? "http://localhost:8000";
const proxy = { "/api": { target: BACKEND, changeOrigin: true } };

export default defineConfig({
  plugins: [react(), tailwindcss(), serveRepoDirs()],
  server: { port: 5173, open: true, proxy },
  preview: { proxy },
});
