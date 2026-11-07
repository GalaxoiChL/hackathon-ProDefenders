// Pune reclama pe panou în timp real, cu WebGL: fiecare cadru al video-ului + imaginea reclamei deformată în perspectivă.
// Varianta din browser a lui pipeline/insert_ad.py, fără urmărire: camera trebuie să stea pe loc.
import { homography, quadAspect, UNIT_SQUARE, type Point } from "./homography";

const VERT = `
attribute vec2 aPos;
varying vec2 vUv;
void main() {
  vUv = vec2((aPos.x + 1.0) * 0.5, (1.0 - aPos.y) * 0.5); // (0,0) = colțul stânga-sus al cadrului
  gl_Position = vec4(aPos, 0.0, 1.0);
}`;

const FRAG = `
precision mediump float;
uniform sampler2D uVideo;
uniform sampler2D uAd;
uniform mat3 uToUnit;   // pixel din cadru -> coordonate în pătratul reclamei
uniform vec2 uSize;     // dimensiunea cadrului, în pixeli
uniform vec4 uCrop;     // decupajul reclamei: offset.xy, scară.zw
uniform float uHasAd;
uniform float uOutline;
varying vec2 vUv;
void main() {
  vec3 color = texture2D(uVideo, vUv).rgb;
  vec3 q = uToUnit * vec3(vUv * uSize, 1.0);
  vec2 st = q.xy / q.z;
  // margine netezită de ~1 pixel, ca reclama să nu pară decupată cu foarfeca
  vec2 px = fwidth(st);
  vec2 inside2 = smoothstep(vec2(0.0), px, st) * smoothstep(vec2(0.0), px, 1.0 - st);
  float inside = inside2.x * inside2.y;
  if (uHasAd > 0.5 && inside > 0.0) {
    vec4 ad = texture2D(uAd, uCrop.xy + clamp(st, 0.0, 1.0) * uCrop.zw);
    color = mix(color, ad.rgb, ad.a * inside);
  }
  if (uOutline > 0.5) {
    vec2 edge = min(st, 1.0 - st);
    float onEdge = step(min(edge.x, edge.y), 2.5 * max(px.x, px.y)) * step(-2.5 * max(px.x, px.y), min(edge.x, edge.y));
    color = mix(color, vec3(0.13, 0.89, 0.63), onEdge);
  }
  gl_FragColor = vec4(color, 1.0);
}`;

function compile(gl: WebGLRenderingContext, type: number, src: string): WebGLShader {
  const s = gl.createShader(type)!;
  gl.shaderSource(s, src);
  gl.compileShader(s);
  if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(s) ?? "shader error");
  return s;
}

function texture(gl: WebGLRenderingContext): WebGLTexture {
  const t = gl.createTexture()!;
  gl.bindTexture(gl.TEXTURE_2D, t);
  // dimensiuni oarecare (nu puteri ale lui 2): fără mipmap, cu margini prinse
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
  return t;
}

export class Compositor {
  private gl: WebGLRenderingContext;
  private videoTex: WebGLTexture;
  private adTex: WebGLTexture;
  private u: Record<string, WebGLUniformLocation | null> = {};
  private ad: HTMLImageElement | null = null;
  private corners: Point[] | null = null;

  constructor(private canvas: HTMLCanvasElement) {
    const gl = canvas.getContext("webgl", { preserveDrawingBuffer: true, premultipliedAlpha: false });
    if (!gl) throw new Error("This browser cannot draw with WebGL");
    if (!gl.getExtension("OES_standard_derivatives")) throw new Error("This browser lacks a WebGL feature the preview needs");
    this.gl = gl;
    const prog = gl.createProgram()!;
    gl.attachShader(prog, compile(gl, gl.VERTEX_SHADER, VERT));
    gl.attachShader(prog, compile(gl, gl.FRAGMENT_SHADER, "#extension GL_OES_standard_derivatives : enable\n" + FRAG));
    gl.linkProgram(prog);
    if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(prog) ?? "link error");
    gl.useProgram(prog);

    const buf = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buf);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]), gl.STATIC_DRAW);
    const loc = gl.getAttribLocation(prog, "aPos");
    gl.enableVertexAttribArray(loc);
    gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);

    for (const n of ["uVideo", "uAd", "uToUnit", "uSize", "uCrop", "uHasAd", "uOutline"]) this.u[n] = gl.getUniformLocation(prog, n);
    this.videoTex = texture(gl);
    this.adTex = texture(gl);
    gl.uniform1i(this.u.uVideo, 0);
    gl.uniform1i(this.u.uAd, 1);
  }

  /** Mărimea în care desenăm: cea a video-ului, plafonată la `maxWidth` ca să rămână fluid. */
  resize(videoW: number, videoH: number, maxWidth = 1280) {
    const s = Math.min(1, maxWidth / videoW);
    this.canvas.width = Math.round(videoW * s);
    this.canvas.height = Math.round(videoH * s);
    this.gl.viewport(0, 0, this.canvas.width, this.canvas.height);
  }

  /** Colțurile panoului în coordonate relative la cadru (0..1), ordinea TL, TR, BR, BL. */
  setCorners(corners: Point[] | null) {
    this.corners = corners;
  }

  setAd(img: HTMLImageElement | null) {
    this.ad = img;
    if (!img) return;
    const gl = this.gl;
    gl.activeTexture(gl.TEXTURE1);
    gl.bindTexture(gl.TEXTURE_2D, this.adTex);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, img);
  }

  render(video: HTMLVideoElement, outline = false) {
    const gl = this.gl;
    const W = this.canvas.width;
    const H = this.canvas.height;
    if (video.readyState < 2 || !W) return;
    gl.activeTexture(gl.TEXTURE0);
    gl.bindTexture(gl.TEXTURE_2D, this.videoTex);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGB, gl.RGB, gl.UNSIGNED_BYTE, video);

    const quad = this.corners?.map(([x, y]) => [x * W, y * H] as Point);
    const hasQuad = !!quad && quad.length === 4;
    gl.uniform2f(this.u.uSize, W, H);
    gl.uniform1f(this.u.uHasAd, hasQuad && this.ad ? 1 : 0);
    gl.uniform1f(this.u.uOutline, hasQuad && outline ? 1 : 0);
    if (hasQuad) {
      const h = homography(quad, UNIT_SQUARE);
      gl.uniformMatrix3fv(this.u.uToUnit, false, [h[0], h[3], h[6], h[1], h[4], h[7], h[2], h[5], h[8]]);
      gl.uniform4fv(this.u.uCrop, this.ad ? coverCrop(this.ad, quadAspect(quad)) : [0, 0, 1, 1]);
    }
    gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
  }
}

/** Ca `object-fit: cover`: decupează centrul reclamei la proporțiile panoului, fără s-o deformeze. */
function coverCrop(img: HTMLImageElement, target: number): [number, number, number, number] {
  const aspect = img.naturalWidth / img.naturalHeight;
  if (aspect > target) {
    const sx = target / aspect;
    return [(1 - sx) / 2, 0, sx, 1];
  }
  const sy = aspect / target;
  return [0, (1 - sy) / 2, 1, sy];
}
