#!/usr/bin/env python3
"""Renderiza uma VSL a partir de um vsl.json.
Uso: python3 render_vsl.py vsl.json [--preview] [--out pasta]
Requer: ffmpeg, pillow, numpy. Opcional: edge-tts (narração sintética).
"""
import sys, os, json, subprocess, shutil, wave, glob, argparse
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

ap = argparse.ArgumentParser()
ap.add_argument("spec"); ap.add_argument("--preview", action="store_true"); ap.add_argument("--out", default="out")
A = ap.parse_args()
BASE = os.path.dirname(os.path.abspath(A.spec))
S = json.load(open(A.spec, encoding="utf-8"))
OUT = A.out; os.makedirs(f"{OUT}/scenes", exist_ok=True); os.makedirs(f"{OUT}/audio", exist_ok=True)
def P(p): return p if os.path.isabs(p) else os.path.join(BASE, p)

W, H = map(int, S.get("size", "1080x1920").split("x")); FPS = 30
K = min(W, H) / 1080  # escala de fonte
def hexc(h): h = h.lstrip("#"); return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))
ACC = hexc(S.get("accent", "#F5B841")); WHITE = (255, 255, 255); GREY = (205, 205, 210); BG = (8, 8, 10)

# ---------- fontes ----------
def find_font(names):
    dirs = ["/usr/share/fonts", "/usr/local/share/fonts", os.path.expanduser("~/.fonts"), os.path.expanduser("~/.local/share/fonts"),
            "/Library/Fonts", "/System/Library/Fonts", os.path.expanduser("~/Library/Fonts"), "C:/Windows/Fonts"]
    for n in names:
        if os.path.isfile(n): return n
        for d in dirs:
            hits = glob.glob(f"{d}/**/{n}", recursive=True)
            if hits: return hits[0]
    return None
FB = S.get("font_bold") or find_font(["Poppins-Bold.ttf", "Montserrat-Bold.ttf", "arialbd.ttf", "Arial Bold.ttf", "DejaVuSans-Bold.ttf"])
FM = S.get("font_regular") or find_font(["Poppins-Medium.ttf", "Montserrat-Medium.ttf", "arial.ttf", "Arial.ttf", "DejaVuSans.ttf"])
def F(path, size):
    try: return ImageFont.truetype(path, int(size * K))
    except Exception: return ImageFont.load_default(int(size * K))

# ---------- fundos ----------
PHOTO = Image.open(P(S["photo"])).convert("RGB") if S.get("photo") else Image.new("RGB", (W, H), (30, 30, 36))
VERT = H > W; LAND = W > H
HERO_H = int(H * (0.65 if VERT else 0.62 if H == W else 1.0))
HERO_W = int(W * 0.62) if LAND else W
CW, CX = (int(W * 0.5), int(W * 0.48)) if LAND else (W, 0)  # área de texto
TEXT_TOP = int(H * (0.585 if VERT else 0.52 if H == W else 0.45))
cs = max(HERO_W * 1.14 / PHOTO.width, HERO_H * 1.14 / PHOTO.height)
HERO = PHOTO.resize((int(PHOTO.width * cs), int(PHOTO.height * cs)), Image.LANCZOS)
g = np.clip((np.arange(HERO_H) - HERO_H * 0.42) / (HERO_H * 0.58), 0, 1) ** 1.3
if LAND:
    g = np.clip((np.arange(HERO_W) - HERO_W * 0.55) / (HERO_W * 0.45), 0, 1) ** 1.2
    GRAD = Image.fromarray((np.tile(g[None, :], (HERO_H, 1)) * 255).astype(np.uint8))
else:
    GRAD = Image.fromarray((np.tile(g[:, None], (1, W)) * 255).astype(np.uint8))
BLK = Image.new("RGB", (HERO_W, HERO_H), BG)
fx = S.get("focus", [0.5, 0.4])  # ponto de foco do zoom (x,y em fração)

def dark_bg():
    s = max(W / PHOTO.width, H / PHOTO.height)
    im = PHOTO.resize((int(PHOTO.width * s) + 2, int(PHOTO.height * s) + 2), Image.LANCZOS)
    x, y = (im.width - W) // 2, (im.height - H) // 2
    im = im.crop((x, y, x + W, y + H)).filter(ImageFilter.GaussianBlur(38 * K))
    return Image.blend(im, Image.new("RGB", (W, H), BG), 0.80)
DARK = dark_bg()

def hero_frame(p):
    z = 1.0 + 0.10 * p
    cw, ch = int(HERO.width / 1.14 / z), int(HERO.height / 1.14 / z)
    cx, cy = HERO.width * fx[0], HERO.height * fx[1]
    x0 = int(min(max(cx - cw / 2, 0), HERO.width - cw)); y0 = int(min(max(cy - ch / 2, 0), HERO.height - ch))
    crop = HERO.crop((x0, y0, x0 + cw, y0 + ch)).resize((HERO_W, HERO_H), Image.BILINEAR)
    bg = Image.new("RGB", (W, H), BG); bg.paste(Image.composite(BLK, crop, GRAD), (0, 0)); return bg

# ---------- textos ----------
ST = {"h": (FB, 74, WHITE), "g": (FB, 86, ACC), "s": (FM, 48, GREY), "x": (FB, 150, ACC), "price": (FB, 190, ACC),
      "b": (FM, 52, WHITE), "tag": (FB, 40, (20, 16, 8)), "strike": (FM, 56, (150, 150, 155))}
GAP = {"h": 26, "g": 26, "s": 22, "x": 20, "price": 10, "b": 22, "tag": 34, "strike": 10}
MAXW = int(min(CW, 1080 * K) * 0.87)

def wrap(d, text, font, maxw):
    lines, cur = [], ""
    for w in text.split():
        t = (cur + " " + w).strip()
        if d.textlength(t, font=font) <= maxw or not cur: cur = t
        else: lines.append(cur); cur = w
    return lines + ([cur] if cur else [])

def render_item(kind, text):
    fp, size, col = ST[kind]; font = F(fp, size); d0 = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    if kind == "tag" and S.get("accent_text"): col = hexc(S["accent_text"])
    if kind == "b":
        lines = wrap(d0, text, font, MAXW - int(90 * K)); lh = int(size * K * 1.3)
        im = Image.new("RGBA", (CW, lh * len(lines) + int(10 * K)), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
        x0 = (CW - MAXW) // 2; r = int(52 * K)
        d.ellipse((x0, int(8 * K), x0 + r, int(8 * K) + r), fill=ACC)
        d.line([(x0 + r * .25, 8 * K + r * .5), (x0 + r * .44, 8 * K + r * .72), (x0 + r * .77, 8 * K + r * .27)], fill=(20, 16, 8), width=max(3, int(7 * K)), joint="curve")
        for i, ln in enumerate(lines): d.text((x0 + int(82 * K), i * lh), ln, font=font, fill=col)
        return im
    if kind == "tag":
        tw = d0.textlength(text, font=font); hh = int(84 * K)
        im = Image.new("RGBA", (CW, hh), (0, 0, 0, 0)); d = ImageDraw.Draw(im); x = (CW - tw) / 2
        d.rounded_rectangle((x - 36 * K, 4 * K, x + tw + 36 * K, hh - 4 * K), radius=int(38 * K), fill=ACC)
        d.text((CW / 2, hh / 2), text, font=font, fill=col, anchor="mm"); return im
    lines = wrap(d0, text, font, MAXW); lh = int(size * K * 1.18)
    im = Image.new("RGBA", (CW, lh * len(lines) + int(12 * K)), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    for i, ln in enumerate(lines):
        if kind != "s": d.text((CW / 2 + 3 * K, i * lh + 4 * K), ln, font=font, fill=(0, 0, 0, 150), anchor="ma")
        d.text((CW / 2, i * lh), ln, font=font, fill=col, anchor="ma")
        if kind == "strike":
            tw = d.textlength(ln, font=font)
            d.line([(CW / 2 - tw / 2 - 8, i * lh + lh * .52), (CW / 2 + tw / 2 + 8, i * lh + lh * .52)], fill=(230, 70, 70), width=max(3, int(6 * K)))
    return im

# ---------- narração ----------
def adur(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path], capture_output=True, text=True)
    return float(r.stdout.strip())

voice = S.get("voice", "none"); scenes = S["scenes"]
for i, sc in enumerate(scenes):
    sc["_audio"] = None
    if voice == "edge" and sc.get("say"):
        mp = f"{OUT}/audio/s{i:02d}.mp3"
        if not os.path.exists(mp) or A.preview is False:
            if not shutil.which("edge-tts"): sys.exit("edge-tts não encontrado: pip install edge-tts (ou use voice: files/none)")
            subprocess.run(["edge-tts", "--voice", S.get("edge_voice", "pt-BR-AntonioNeural"), "--rate", S.get("edge_rate", "+8%"),
                            "--text", sc["say"], "--write-media", mp], check=True)
        sc["_audio"] = mp
    elif voice == "files" and sc.get("audio"):
        sc["_audio"] = P(sc["audio"])
    nominal = sc.get("dur") or (max([it[0] for it in sc["items"]] + [0]) + 3)
    if sc["_audio"]:
        real = adur(sc["_audio"]) + S.get("pad", 0.9)  # folga após a fala (menor = vídeo mais ágil)
        f = real / nominal
        sc["items"] = [[t * f, k, tx] for t, k, tx in sc["items"]]
        sc["dur"] = real
    else:
        sc["dur"] = nominal
TOTAL = sum(sc["dur"] for sc in scenes)

def ease(x): x = max(0, min(1, x)); return 1 - (1 - x) ** 3

def build(sc):
    rend = [(float(t), k, render_item(k, tx)) for t, k, tx in sc["items"]]
    th = sum(im.height for _, _, im in rend) + sum(int(GAP[k] * K) for _, k, _ in rend[:-1])
    if sc.get("mode", "dark") == "hero" and not LAND:
        avail = H - TEXT_TOP - int(110 * K); top = TEXT_TOP + max(0, (avail - th) // 2); top = min(top, H - int(110 * K) - th)
    else: top = (H - th) // 2
    pos, y = [], top
    for _, k, im in rend: pos.append(y); y += im.height + int(GAP[k] * K)
    return rend, pos

def frame(sc, built, t, off):
    rend, pos = built; dur = sc["dur"]
    bg = (hero_frame(t / dur) if sc.get("mode") == "hero" else DARK.copy()).convert("RGBA")
    for (ta, k, im), y in zip(rend, pos):
        a = ease((t - ta) / 0.45)
        if a <= 0: continue
        if a < 1: im = im.copy(); im.putalpha(im.getchannel("A").point(lambda v: int(v * a)))
        bg.alpha_composite(im, (CX if sc.get("mode") == "hero" else (W - CW) // 2, y + int(34 * K * (1 - a))))
    d = ImageDraw.Draw(bg); bh = max(6, int(10 * K))
    d.rectangle((0, 0, W, bh), fill=(40, 40, 45)); d.rectangle((0, 0, int(W * (off + t) / TOTAL), bh), fill=ACC)
    if S.get("brand"):
        d.text((W - 30 * K, H - 30 * K), S["brand"], font=F(FM, 30), fill=(170, 170, 175), anchor="rd")
    out = bg.convert("RGB"); fade = min(1, t / 0.35, (dur - t) / 0.35)
    return out if fade >= 1 else Image.blend(Image.new("RGB", (W, H)), out, max(0, fade))

# ---------- preview ----------
if A.preview:
    os.makedirs(f"{OUT}/preview", exist_ok=True); off = 0
    for i, sc in enumerate(scenes):
        b = build(sc); frame(sc, b, sc["dur"] - 0.5, off).save(f"{OUT}/preview/cena{i:02d}.jpg", quality=88); off += sc["dur"]
    print(f"Preview: {len(scenes)} imagens em {OUT}/preview  | duração total ≈ {TOTAL:.1f}s"); sys.exit()

# ---------- render das cenas ----------
off = 0; starts = []
for i, sc in enumerate(scenes):
    starts.append(off); b = build(sc); n = int(round(sc["dur"] * FPS))
    tmp, fin = f"{OUT}/scenes/s{i:02d}.tmp.mp4", f"{OUT}/scenes/s{i:02d}.mp4"
    p = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
                          "-c:v", "libx264", "-preset", "veryfast", "-crf", "19", "-pix_fmt", "yuv420p", tmp], stdin=subprocess.PIPE)
    for f in range(n): p.stdin.write(frame(sc, b, f / FPS, off).tobytes())
    p.stdin.close()
    if p.wait() != 0: sys.exit(f"ffmpeg falhou na cena {i}")
    os.replace(tmp, fin); off += n / FPS; print(f"cena {i+1}/{len(scenes)} ok")
TOTAL = off
with open(f"{OUT}/list.txt", "w") as fh:
    for i in range(len(scenes)): fh.write(f"file 'scenes/s{i:02d}.mp4'\n")
subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", f"{OUT}/list.txt", "-c", "copy", f"{OUT}/video.mp4"], check=True)

# ---------- trilha ----------
music = P(S["music"]) if S.get("music") else f"{OUT}/music.wav"
if not S.get("music"):
    SR = 44100; t = np.arange(int(SR * TOTAL)) / SR; out = np.zeros_like(t)
    nf = lambda m: 440 * 2 ** ((m - 69) / 12); prog = [[57, 60, 64, 69], [53, 57, 60, 65], [48, 52, 55, 60], [55, 59, 62, 67]]
    for i in range(int(TOTAL / 4) + 1):
        s, e = int(i * 4 * SR), min(len(t), int((i + 1) * 4 * SR + SR))
        if s >= len(t): break
        tt = t[s:e] - i * 4; env = np.minimum(1, tt / 1.2) * np.exp(-np.maximum(0, tt - 4) * 3)
        for m in prog[i % 4]: out[s:e] += env * (np.sin(2*np.pi*nf(m)*tt) + .3*np.sin(4*np.pi*nf(m)*tt)) * .05
        out[s:e] += env * np.sin(2 * np.pi * nf(prog[i % 4][0] - 12) * tt) * .09
    L = int(.25 * SR); tt = np.arange(L) / SR; kick = np.sin(2*np.pi*(60+60*np.exp(-tt*30))*tt) * np.exp(-tt*14) * .18
    for k in range(int(TOTAL / .6)):
        s = int(k * .6 * SR)
        if s + L <= len(t): out[s:s+L] += kick
    out *= np.minimum(1, np.minimum(t / 2, (TOTAL - t) / 3)); out = out / (np.abs(out).max() + 1e-9) * .6
    w = wave.open(music, "wb"); w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR); w.writeframes((out * 32767).astype(np.int16).tobytes()); w.close()

# ---------- mixagem ----------
ins = ["-i", f"{OUT}/video.mp4", "-i", music]; flt = []; labels = []
has_voice = any(sc["_audio"] for sc in scenes)
mv = S.get("music_volume", 0.13 if has_voice else 0.7)
flt.append(f"[1:a]volume={mv},atrim=0:{TOTAL:.3f}[m]"); labels.append("[m]"); j = 2
for sc, st in zip(scenes, starts):
    if sc["_audio"]:
        ins += ["-i", sc["_audio"]]; ms = int((st + 0.3) * 1000)
        flt.append(f"[{j}:a]aresample=44100,volume=1.0,adelay={ms}|{ms}[v{j}]"); labels.append(f"[v{j}]"); j += 1
flt.append(f"{''.join(labels)}amix=inputs={len(labels)}:normalize=0:duration=first,alimiter=limit=0.95[a]")
final = f"{OUT}/VSL_final.mp4"
subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *ins, "-filter_complex", ";".join(flt), "-map", "0:v", "-map", "[a]",
                "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", final], check=True)
print(f"Pronto: {final} ({TOTAL:.1f}s)")
