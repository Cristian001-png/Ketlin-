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

def dark_bg(src=None, dim=0.80):
    src = src or PHOTO
    s = max(W / src.width, H / src.height)
    im = src.resize((int(src.width * s) + 2, int(src.height * s) + 2), Image.LANCZOS)
    x, y = (im.width - W) // 2, (im.height - H) // 2
    im = im.crop((x, y, x + W, y + H)).filter(ImageFilter.GaussianBlur(38 * K))
    return Image.blend(im, Image.new("RGB", (W, H), BG), dim)
DARK = dark_bg()
_BG = {}
def bg_for(sc):
    """Fundo desfocado da cena: campo "bg" (imagem própria) ou a foto principal."""
    p = sc.get("bg")
    if not p: return DARK
    key = (p, sc.get("bg_dim", 0.72))
    if key not in _BG: _BG[key] = dark_bg(Image.open(P(p)).convert("RGB"), key[1])
    return _BG[key]

# ---------- cartão (mode "card") e chat (mode "chat") ----------
CARD_TOP = int(H * (0.06 if VERT else 0.08))
CARD_H = int(H * (0.34 if VERT else 0.36 if H == W else 0.78))
CARD_W = int(W * (0.84 if not LAND else 0.42))
CARD_TEXT_TOP = CARD_TOP + CARD_H + int(70 * K)
CHAT_TOP = int(H * (0.09 if VERT else 0.08)); CHAT_H = int(H * (0.46 if VERT else 0.40 if H == W else 0.80))
CHAT_TEXT_TOP = CHAT_TOP + CHAT_H + int(60 * K)

def prep_card(sc):
    im = Image.open(P(sc["image"])).convert("RGB"); c = sc.get("image_crop")
    if c: im = im.crop((int(c[0] * im.width), int(c[1] * im.height), int(c[2] * im.width), int(c[3] * im.height)))
    s = min(CARD_W / im.width, CARD_H / im.height)
    im = im.resize((int(im.width * s), int(im.height * s)), Image.LANCZOS); r = int(22 * K); pad = int(60 * K)
    mask = Image.new("L", im.size, 0); ImageDraw.Draw(mask).rounded_rectangle((0, 0, im.width - 1, im.height - 1), r, fill=255)
    sh = Image.new("L", (im.width + 2 * pad, im.height + 2 * pad), 0)
    ImageDraw.Draw(sh).rounded_rectangle((pad, pad + int(16 * K), pad + im.width, pad + im.height + int(16 * K)), r, fill=180)
    sh = sh.filter(ImageFilter.GaussianBlur(24 * K))
    bg = bg_for(sc) if sc.get("bg") else dark_bg(im, 0.80)
    return {"im": im, "mask": mask, "sh": sh, "pad": pad, "bg": bg}

def card_center():
    return (int(W * 0.26), H // 2) if LAND else (W // 2, CARD_TOP + CARD_H // 2)

def card_frame(sc, t, p):
    cd = sc["_card"]; bg = cd["bg"].copy().convert("RGBA"); a = ease(t / 0.5); z = 1.0 + 0.035 * p
    im = cd["im"].resize((int(cd["im"].width * z), int(cd["im"].height * z)), Image.BILINEAR)
    mk = cd["mask"].resize(im.size, Image.BILINEAR)
    cx, cy = card_center(); cy += int(60 * K * (1 - a)); x, y = cx - im.width // 2, cy - im.height // 2
    sh = cd["sh"].resize((im.width + 2 * cd["pad"], im.height + 2 * cd["pad"]))
    bg.paste(Image.new("RGBA", sh.size, (0, 0, 0, 255)), (x - cd["pad"], y - cd["pad"]), sh.point(lambda v: int(v * a)))
    bg.paste(im, (x, y), mk.point(lambda v: int(v * a)))
    return bg

def chat_times(sc):
    ch = sc["chat"]; sp = ch.get("speed", 16); t0 = ch.get("start", 0.2)
    t_typed = t0 + len(ch["user"]) / sp; t_ai = t_typed + 0.25
    return t0, t_typed, t_ai, ch.get("stamp_at", t_ai + 1.2)

def chat_frame(sc, t):
    ch = sc["chat"]; tn = t / sc.get("_f", 1); t0, t_typed, t_ai, t_st = chat_times(sc)
    bg = bg_for(sc).copy().convert("RGBA"); d = ImageDraw.Draw(bg)
    pw = CARD_W; px = card_center()[0] - pw // 2; py = CHAT_TOP; ph = CHAT_H; r = int(30 * K)
    d.rounded_rectangle((px, py, px + pw, py + ph), r, fill=(18, 20, 26, 235), outline=(60, 64, 78, 255), width=max(2, int(3 * K)))
    hf = F(FB, 40); av = int(68 * K); hy = py + int(30 * K)
    d.ellipse((px + int(28 * K), hy, px + int(28 * K) + av, hy + av), fill=ACC)
    d.text((px + int(28 * K) + av / 2, hy + av / 2), "IA", font=F(FB, 30), fill=(20, 16, 8), anchor="mm")
    d.text((px + int(112 * K), hy + av / 2), ch.get("title", "Assistente de IA"), font=hf, fill=WHITE, anchor="lm")
    d.line((px, hy + av + int(22 * K), px + pw, hy + av + int(22 * K)), fill=(50, 54, 66), width=2)
    f = F(FM, 52); maxw = int(pw * 0.70); y = hy + av + int(60 * K)
    n = int(max(0, tn - t0) * ch.get("speed", 16)); typed = ch["user"][:n]
    if tn >= t0:
        d0 = ImageDraw.Draw(Image.new("RGB", (1, 1))); lines = wrap(d0, ch["user"], f, maxw)
        shown, left = [], len(typed)
        for ln in lines: shown.append(ln[:max(0, left)]); left -= len(ln) + 1
        if tn < t_typed and int(tn * 3) % 2 == 0: shown[min(len(shown) - 1, sum(1 for s_ in shown if s_) - 1 if any(shown) else 0)] += "|"
        lh = int(68 * K); bw = max(d0.textlength(ln, font=f) for ln in lines) + int(56 * K); bh = lh * len(lines) + int(44 * K)
        bx = px + pw - int(28 * K) - bw
        d.rounded_rectangle((bx, y, bx + bw, y + bh), int(26 * K), fill=(37, 99, 235))
        for i, ln in enumerate(shown): d.text((bx + int(30 * K), y + int(22 * K) + i * lh), ln, font=f, fill=WHITE)
        y += bh + int(40 * K)
    if tn >= t_ai:
        bx = px + int(28 * K); n_ln = ch.get("ai_lines", 5); bw = int(pw * 0.80)
        if tn < t_ai + 0.5:
            d.rounded_rectangle((bx, y, bx + int(170 * K), y + int(84 * K)), int(30 * K), fill=(48, 52, 64))
            for k in range(3):
                on = int((tn - t_ai) * 6) % 3 == k; cxx = bx + int((48 + 37 * k) * K)
                d.ellipse((cxx - 11 * K, y + 31 * K, cxx + 11 * K, y + 53 * K), fill=(220, 220, 225) if on else (120, 124, 135))
        else:
            k_show = min(n_ln, int((tn - t_ai - 0.5) / 0.1) + 1); lh = int(50 * K)
            d.rounded_rectangle((bx, y, bx + bw, y + int(40 * K) + lh * n_ln), int(30 * K), fill=(48, 52, 64))
            rnd = np.random.default_rng(len(ch["user"]))
            for k in range(k_show):
                ww = int((bw - int(60 * K)) * (rnd.uniform(0.55, 1.0) if k < n_ln - 1 else 0.45))
                d.rounded_rectangle((bx + int(28 * K), y + int(28 * K) + k * lh, bx + int(28 * K) + ww, y + int(50 * K) + k * lh), int(11 * K), fill=(130, 134, 146))
    if ch.get("stamp") and tn >= t_st:
        a = ease((tn - t_st) / 0.18); sz = 1.0 + 0.7 * (1 - a); sf = F(FB, 80)
        tw = int(ImageDraw.Draw(Image.new("RGB", (1, 1))).textlength(ch["stamp"], font=sf)); bw_, bh_ = tw + int(80 * K), int(150 * K)
        st = Image.new("RGBA", (bw_, bh_), (0, 0, 0, 0)); ds = ImageDraw.Draw(st); red = (230, 57, 70, 255)
        ds.rounded_rectangle((6, 6, bw_ - 6, bh_ - 6), int(18 * K), outline=red, width=max(5, int(10 * K)))
        ds.text((bw_ / 2, bh_ / 2), ch["stamp"], font=sf, fill=red, anchor="mm")
        st = st.rotate(-8, expand=True, resample=Image.BICUBIC); st = st.resize((int(st.width * sz), int(st.height * sz)), Image.BILINEAR)
        st.putalpha(st.getchannel("A").point(lambda v: int(v * a)))
        cx = card_center()[0]; cy = py + int(ph * 0.62); bg.alpha_composite(st, (max(0, cx - st.width // 2), max(0, cy - st.height // 2)))
        fl = max(0, 1 - (tn - t_st) / 0.25)
        if fl > 0: bg.alpha_composite(Image.new("RGBA", (W, H), (230, 57, 70, int(70 * fl))))
    return bg

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
        sc["dur"] = real; sc["_f"] = f
    else:
        sc["dur"] = nominal
    if sc.get("mode") == "card": sc["_card"] = prep_card(sc)
TOTAL = sum(sc["dur"] for sc in scenes)

def ease(x): x = max(0, min(1, x)); return 1 - (1 - x) ** 3

def build(sc):
    rend = [(float(t), k, render_item(k, tx)) for t, k, tx in sc["items"]]
    th = sum(im.height for _, _, im in rend) + sum(int(GAP[k] * K) for _, k, _ in rend[:-1])
    mode = sc.get("mode", "dark")
    if mode in ("hero", "card", "chat") and not LAND:
        t0 = TEXT_TOP if mode == "hero" else CHAT_TEXT_TOP if mode == "chat" else CARD_TEXT_TOP
        avail = H - t0 - int(110 * K); top = t0 + max(0, (avail - th) // 2); top = min(top, H - int(110 * K) - th)
    else: top = (H - th) // 2
    pos, y = [], top
    for _, k, im in rend: pos.append(y); y += im.height + int(GAP[k] * K)
    return rend, pos

def frame(sc, built, t, off):
    rend, pos = built; dur = sc["dur"]
    mode = sc.get("mode", "dark")
    if mode == "hero": bg = hero_frame(t / dur).convert("RGBA")
    elif mode == "card": bg = card_frame(sc, t, t / dur)
    elif mode == "chat": bg = chat_frame(sc, t)
    else: bg = bg_for(sc).copy().convert("RGBA")
    for (ta, k, im), y in zip(rend, pos):
        a = ease((t - ta) / 0.45)
        if a <= 0: continue
        if a < 1: im = im.copy(); im.putalpha(im.getchannel("A").point(lambda v: int(v * a)))
        bg.alpha_composite(im, (CX if mode in ("hero", "card") else (W - CW) // 2, y + int(34 * K * (1 - a))))
    d = ImageDraw.Draw(bg); bh = max(6, int(10 * K))
    d.rectangle((0, 0, W, bh), fill=(40, 40, 45)); d.rectangle((0, 0, int(W * (off + t) / TOTAL), bh), fill=ACC)
    if S.get("brand"):
        d.text((W - 30 * K, H - 30 * K), S["brand"], font=F(FM, 30), fill=(170, 170, 175), anchor="rd")
    out = bg.convert("RGB")
    if mode == "chat" and sc["chat"].get("stamp"):
        ts = t / sc.get("_f", 1) - chat_times(sc)[3]
        if 0 <= ts < 0.4:
            amp = int(16 * K * (1 - ts / 0.4)); dx = int(amp * np.sin(ts * 90)); dy = int(amp * np.cos(ts * 70))
            sh = Image.new("RGB", (W, H), BG); sh.paste(out, (dx, dy)); out = sh
    fade = min(1, t / 0.35, (dur - t) / 0.35)
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
# efeitos sonoros: sfx por cena ([tempo, nome ou arquivo, duração opcional]) + whoosh nas transições
def gen_sfx(name, dur=1.0):
    SR2 = 44100; path = f"{OUT}/sfx/{name}_{dur:.2f}.wav"; os.makedirs(f"{OUT}/sfx", exist_ok=True)
    if os.path.exists(path): return path
    rng = np.random.default_rng(11)
    def band(x, lo, hi):
        X = np.fft.rfft(x); fr = np.fft.rfftfreq(len(x), 1 / SR2); X[(fr < lo) | (fr > hi)] = 0; return np.fft.irfft(X, len(x))
    if name == "whoosh":
        n = int(0.5 * SR2); tt = np.arange(n) / SR2; y = np.zeros(n); seg = n // 10
        for i in range(10): y[i*seg:(i+1)*seg] = band(rng.normal(0, 1, seg), 300 + i * 350, 1200 + i * 700)
        y *= np.sin(np.pi * tt / tt[-1]) ** 2 * 0.5
    elif name == "impact":
        n = int(0.9 * SR2); tt = np.arange(n) / SR2
        y = np.sin(2 * np.pi * (48 * tt + 40 * (1 - np.exp(-tt * 25)))) * np.exp(-tt * 5) * 0.9
        y[:int(0.05 * SR2)] += band(rng.normal(0, 1, int(0.05 * SR2)), 800, 6000) * np.exp(-np.arange(int(0.05 * SR2)) / 300) * 0.6
    elif name == "pop":
        n = int(0.12 * SR2); tt = np.arange(n) / SR2; y = np.sin(2 * np.pi * (600 + 900 * tt / tt[-1]) * tt) * np.exp(-tt * 40) * 0.5
    elif name == "type":
        n = int(dur * SR2); y = np.zeros(n); k = 0.0
        while k < dur - 0.05:
            s0 = int(k * SR2); c = band(rng.normal(0, 1, 600), 1500, 7000) * np.exp(-np.arange(600) / 90) * rng.uniform(0.25, 0.45)
            y[s0:s0 + 600] += c[:len(y[s0:s0 + 600])]; k += rng.uniform(0.055, 0.11)
    else:
        return None
    w = wave.open(path, "wb"); w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR2)
    w.writeframes((np.clip(y, -1, 1) * 32767).astype(np.int16).tobytes()); w.close(); return path
sv = S.get("sfx_volume", 0.6); events = []
if S.get("transition_sfx"):
    events += [(st - 0.15, S["transition_sfx"], 0.5, 0.45) for st in starts[1:]]
for sc, st in zip(scenes, starts):
    for ev in sc.get("sfx", []):
        tt_, nm = ev[0], ev[1]; du = ev[2] if len(ev) > 2 else 1.0
        events.append((st + tt_ * sc.get("_f", 1), nm, du * sc.get("_f", 1), 1.0))
for at, nm, du, g in events:
    fpath = P(nm) if os.path.exists(P(nm)) else gen_sfx(nm, du)
    if not fpath: continue
    ins += ["-i", fpath]; ms = max(0, int(at * 1000))
    flt.append(f"[{j}:a]aresample=44100,volume={sv * g:.2f},adelay={ms}|{ms}[e{j}]"); labels.append(f"[e{j}]"); j += 1
flt.append(f"{''.join(labels)}amix=inputs={len(labels)}:normalize=0:duration=first,alimiter=limit=0.95[a]")
final = f"{OUT}/VSL_final.mp4"
subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *ins, "-filter_complex", ";".join(flt), "-map", "0:v", "-map", "[a]",
                "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", final], check=True)
print(f"Pronto: {final} ({TOTAL:.1f}s)")
