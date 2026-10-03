#!/usr/bin/env python3
"""seedance_swap.py - swap the person in a video with an AI character via the
Seedance 2.5 API (BytePlus ModelArk / Volcano Ark), then build a side-by-side
comparison video. Needs only Python 3 stdlib + ffmpeg/ffprobe.

  check    VIDEO OUTDIR                 probe, upscale if under the pixel minimum, preview grid
  character new NAME --sheet S --face F --appearance TEXT [--dir characters]
                                        save a reusable character profile
  character show DIR                    print a saved profile
  prompt   --char DIR --target TEXT [--char DIR --target TEXT ...] --out P
                                        build the swap prompt with correct @图片N numbering
  run      VIDEO [--char DIR ...] [REF ...] --prompt-file P --out OUT.mp4
                                        submit edit task, poll, download result
                                        (the result URL is saved to OUT.mp4.url.txt and
                                        can be used as VIDEO for a second pass)
  query    TASK_ID --out OUT.mp4        resume / re-download an existing task
  compare  ORIGINAL GENERATED --out OUT.mp4
                                        left original, right swapped, labelled

Media for `run` can be: a public https URL, an asset://<id> from the console
asset library, or a local image file (sent as base64). Reference videos must be
a public URL or asset://<id>.

Env: ARK_API_KEY (required for run/query)
     ARK_BASE_URL   default https://ark.ap-southeast.bytepluses.com/api/v3
                    (mainland Volcano Ark: https://ark.cn-beijing.volces.com/api/v3)
     SEEDANCE_MODEL default dreamina-seedance-2-5-260628 (BytePlus model id)
"""
import argparse, base64, json, math, mimetypes, os, shutil, subprocess, sys, time
import urllib.request, urllib.error

BASE = os.environ.get("ARK_BASE_URL", "https://ark.ap-southeast.bytepluses.com/api/v3").rstrip("/")
MODEL = os.environ.get("SEEDANCE_MODEL", "dreamina-seedance-2-5-260628")
MIN_PIXELS = 409_600          # reference video minimum (width*height)
MAX_REF_SECONDS = 30.0        # Seedance 2.5 total reference video length
MAX_IMAGES = 30               # Seedance 2.5 reference images per request


def sh(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit("command failed: %s\n%s" % (" ".join(cmd), r.stderr[-1500:]))
    return r.stdout


def probe(path):
    out = json.loads(sh(["ffprobe", "-v", "error", "-show_entries",
                         "format=duration:stream=codec_type,width,height,r_frame_rate",
                         "-of", "json", path]))
    info = {"duration": float(out["format"].get("duration") or 0), "has_audio": False}
    for s in out["streams"]:
        if s["codec_type"] == "video" and "width" not in info:
            info.update(width=s["width"], height=s["height"])
        elif s["codec_type"] == "audio":
            info["has_audio"] = True
    return info


def grid(video, out_jpg, n=8, cols=4):
    d = probe(video)["duration"]
    tmp = out_jpg + "_f"
    os.makedirs(tmp, exist_ok=True)
    frames = []
    for i in range(n):
        f = os.path.join(tmp, "f%d.jpg" % i)
        sh(["ffmpeg", "-y", "-v", "error", "-ss", "%.2f" % (d * (i + 0.5) / n), "-i", video,
            "-frames:v", "1", "-vf", "scale=360:640:force_original_aspect_ratio=decrease,"
            "pad=360:640:(ow-iw)/2:(oh-ih)/2", f])
        frames.append(f)
    rows = math.ceil(n / cols)
    layout = "|".join("%d_%d" % (360 * (i % cols), 640 * (i // cols)) for i in range(n))
    args = []
    for f in frames:
        args += ["-i", f]
    sh(["ffmpeg", "-y", "-v", "error", *args, "-filter_complex",
        "xstack=inputs=%d:layout=%s:fill=black" % (n, layout), out_jpg])
    shutil.rmtree(tmp, ignore_errors=True)
    return out_jpg


# ---------------------------------------------------------------- check
def cmd_check(a):
    os.makedirs(a.outdir, exist_ok=True)
    info = probe(a.video)
    w, h, d = info["width"], info["height"], info["duration"]
    print("video: %dx%d (%d px), %.2fs, audio=%s" % (w, h, w * h, d, info["has_audio"]))
    ready = a.video
    if w * h < MIN_PIXELS:
        scale = math.sqrt(MIN_PIXELS / (w * h)) * 1.05
        nw, nh = int(w * scale) // 2 * 2, int(h * scale) // 2 * 2
        short = min(nw, nh)
        if short < 720:                       # round up to a clean 720 short side
            f = 720 / short
            nw, nh = int(nw * f) // 2 * 2, int(nh * f) // 2 * 2
        ready = os.path.join(a.outdir, "upscaled.mp4")
        sh(["ffmpeg", "-y", "-v", "error", "-i", a.video, "-vf",
            "scale=%d:%d:flags=lanczos,setsar=1" % (nw, nh), "-c:v", "libx264", "-preset", "slow",
            "-crf", "16", "-pix_fmt", "yuv420p", "-c:a", "copy", "-movflags", "+faststart", ready])
        print("upscaled to %dx%d (%d px) -> %s" % (nw, nh, nw * nh, ready))
    if d > MAX_REF_SECONDS:
        print("WARNING: %.1fs is longer than %ds - split it before running" % (d, MAX_REF_SECONDS))
    if d < 1.8:
        print("WARNING: shorter than 1.8s - too short for a reference video")
    print("preview grid -> %s" % grid(a.video, os.path.join(a.outdir, "preview.jpg")))
    print("ready video  -> %s" % ready)


# ---------------------------------------------------------------- characters
def load_char(d):
    f = os.path.join(d, "character.json")
    if not os.path.exists(f):
        sys.exit("no character.json in %s" % d)
    c = json.load(open(f, encoding="utf-8"))
    c["images"] = [i if i.startswith(("http://", "https://", "asset://")) else os.path.join(d, i)
                   for i in c["images"]]
    c.setdefault("image_notes", [""] * len(c["images"]))
    return c


def cmd_character(a):
    if a.action == "show":
        print(json.dumps(load_char(a.name), indent=2, ensure_ascii=False))
        return
    d = os.path.join(a.dir, a.name)
    os.makedirs(d, exist_ok=True)
    images, notes = [], []
    for src, note, base in ((a.sheet, "多角度设定图", "sheet"), (a.face, "正面半身照", "face")):
        if not src:
            continue
        if src.startswith(("http://", "https://", "asset://")):
            images.append(src)
        else:
            dst = base + os.path.splitext(src)[1].lower()
            shutil.copy(src, os.path.join(d, dst))
            images.append(dst)
        notes.append(note)
    if not images:
        sys.exit("give at least --sheet or --face")
    prof = {"name": a.name, "appearance": a.appearance, "images": images, "image_notes": notes}
    json.dump(prof, open(os.path.join(d, "character.json"), "w", encoding="utf-8"),
              indent=2, ensure_ascii=False)
    print("saved %s/character.json" % d)


def char_image_numbers(chars):
    out, n = [], 0
    for c in chars:
        nums = list(range(n + 1, n + len(c["images"]) + 1))
        n += len(c["images"])
        out.append(nums)
    return out


def refs_text(nums):
    return "和".join("@图片%d" % i for i in nums)


def cmd_prompt(a):
    if len(a.char) != len(a.target):
        sys.exit("give one --target for every --char")
    chars = [load_char(d) for d in a.char]
    nums = char_image_numbers(chars)
    if nums and nums[-1] and nums[-1][-1] > MAX_IMAGES:
        sys.exit("too many reference images (%d > %d)" % (nums[-1][-1], MAX_IMAGES))
    L = []
    if len(chars) == 1:
        c, t = chars[0], a.target[0]
        L.append('视频编辑：将@视频1中的%s替换为%s中的角色"%s"。' % (t, refs_text(nums[0]), c["name"]))
    else:
        L.append("视频编辑：在@视频1中只做以下替换，其他一律不变：")
        for i, (c, t) in enumerate(zip(chars, a.target), 1):
            L.append('%d. 将%s替换为%s中的角色"%s"；' % (i, t, refs_text(nums[i - 1]), c["name"]))
    notes = []
    for c, ns in zip(chars, nums):
        for k, note in zip(ns, c["image_notes"]):
            notes.append("@图片%d是%s的%s" % (k, c["name"], note or "参考图"))
    L.append("，".join(notes) + "，用于锁定角色的面部、发型、体型和服装。")
    for c in chars:
        L.append("%s的外貌：%s" % (c["name"], c["appearance"]))
    if a.keep:
        L.append("%s保持原样，不要替换。" % a.keep)
    if len(chars) > 1:
        L.append("每个角色始终在被替换者的位置，不要互换，不要混合不同角色的特征。")
    L.append("严格保持@视频1中所有动作、手势、走位、表情、口型和节奏不变；场景、背景、光线、色调、"
             "构图和运镜完全不变。手里拿的东西以原视频为准，不要额外添加道具。不要增加或删除画面中的"
             "任何人物、物体和文字。角色的面部、发型和服装在整段视频中保持一致。")
    L += a.extra
    L.append("声音：保留@视频1的原声。" if a.audio == "keep" else "声音：%s" % a.audio)
    text = "\n".join(L)
    open(a.out, "w", encoding="utf-8").write(text + "\n")
    print(text)
    print("\n-> %s (%d chars)" % (a.out, len(text)))
    if len(text) > 800:
        print("NOTE: long prompt - trim if moderation rejects it")


# ---------------------------------------------------------------- API
def api(method, path, body=None):
    key = os.environ.get("ARK_API_KEY")
    if not key:
        sys.exit("ARK_API_KEY is not set")
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method, headers={
        "Authorization": "Bearer " + key, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        sys.exit("HTTP %s %s\n%s" % (e.code, path, e.read().decode(errors="replace")[:2000]))
    except urllib.error.URLError as e:
        sys.exit("cannot reach %s (%s)" % (BASE, e.reason))


def media_url(src, kind):
    if src.startswith(("http://", "https://", "asset://", "data:")):
        return src
    if not os.path.exists(src):
        sys.exit("not found: %s" % src)
    if kind == "video":
        sys.exit("reference video must be a public URL or asset://<id>, not a local file: %s\n"
                 "upload it to the console asset library (or any public host) first" % src)
    mime = mimetypes.guess_type(src)[0] or "image/png"
    with open(src, "rb") as f:
        return "data:%s;base64,%s" % (mime, base64.b64encode(f.read()).decode())


def poll_and_download(task_id, out, timeout):
    t0 = time.time()
    while True:
        r = api("GET", "/contents/generations/tasks/%s" % task_id)
        st = r.get("status")
        print("  %4ds  %s" % (time.time() - t0, st), flush=True)
        if st == "succeeded":
            break
        if st in ("failed", "cancelled"):
            sys.exit("task %s: %s" % (st, json.dumps(r.get("error") or r, ensure_ascii=False)))
        if time.time() - t0 > timeout:
            sys.exit("timeout - resume later with: query %s --out %s" % (task_id, out))
        time.sleep(15)
    url = (r.get("content") or {}).get("video_url")
    if not url:
        sys.exit("no video_url in response: %s" % json.dumps(r, ensure_ascii=False)[:1500])
    urllib.request.urlretrieve(url, out)
    open(out + ".url.txt", "w").write(url + "\n")
    print("saved %s  usage=%s" % (out, r.get("usage")))
    print("result URL (valid ~24h, usable as VIDEO for a second pass) -> %s.url.txt" % out)


def cmd_run(a):
    prompt = open(a.prompt_file, encoding="utf-8").read().strip()
    content = [{"type": "text", "text": prompt},
               {"type": "video_url", "video_url": {"url": media_url(a.video, "video")},
                "role": "reference_video"}]
    images = []
    for d in a.char:
        c = load_char(d)
        start = len(images) + 1
        images += c["images"]
        print("%s -> %s" % (c["name"], refs_text(range(start, len(images) + 1))))
    images += a.refs
    if len(images) > MAX_IMAGES:
        sys.exit("too many reference images (%d > %d)" % (len(images), MAX_IMAGES))
    if not images:
        sys.exit("no reference images - give --char or image files")
    for ref in images:
        content.append({"type": "image_url", "image_url": {"url": media_url(ref, "image")},
                        "role": "reference_image"})
    body = {"model": MODEL, "content": content, "omni_reference_task_type": "edit",
            "ratio": "adaptive", "duration": -1, "resolution": a.resolution,
            "generate_audio": a.audio == "generate", "watermark": False}
    if a.dry_run:
        shown = json.loads(json.dumps(body))
        for c in shown["content"]:
            for k in ("image_url", "video_url"):
                if k in c and c[k]["url"].startswith("data:"):
                    c[k]["url"] = c[k]["url"][:40] + "...(base64)"
        print(json.dumps(shown, indent=2, ensure_ascii=False))
        return
    r = api("POST", "/contents/generations/tasks", body)
    task_id = r.get("id")
    if not task_id:
        sys.exit("no task id: %s" % r)
    print("task %s submitted" % task_id)
    poll_and_download(task_id, a.out, a.timeout)


def cmd_query(a):
    poll_and_download(a.task_id, a.out, a.timeout)


# ---------------------------------------------------------------- compare
def find_font():
    for p in ("/System/Library/Fonts/PingFang.ttc", "/System/Library/Fonts/STHeiti Medium.ttc",
              "C:/Windows/Fonts/msyh.ttc"):
        if os.path.exists(p):
            return p
    try:
        out = sh(["fc-list", ":lang=zh", "file"]).splitlines()
        if out:
            return out[0].split(":")[0]
    except SystemExit:
        pass
    sys.exit("no Chinese font found - pass --font")


def cmd_compare(a):
    font = (a.font or find_font()).replace(":", "\\:")
    g = probe(a.generated)
    W = 720
    H = int(W * g["height"] / g["width"]) // 2 * 2
    fit = "fps=30,scale=%d:%d:force_original_aspect_ratio=increase:flags=lanczos,crop=%d:%d,setsar=1" % (W, H, W, H)
    label = ("drawtext=fontfile='%s':fontsize=56:fontcolor=%s:text='%s':x=%s:y=40:"
             "box=1:boxcolor=black@0.55:boxborderw=18")
    fc = ("[0:v]%s[l];[1:v]%s[r];[l][r]hstack=2,%s,%s,drawbox=x=%d:y=0:w=4:h=%d:color=white@0.9:t=fill[v]"
          % (fit, fit,
             label % (font, "white", a.left, "(%d-tw)/2" % W),
             label % (font, "0xFFD54A", a.right, "%d+(%d-tw)/2" % (W, W)),
             W - 2, H))
    audio_src = "1:a?" if a.audio == "generated" else "0:a?"
    sh(["ffmpeg", "-y", "-v", "error", "-i", a.original, "-i", a.generated, "-filter_complex", fc,
        "-map", "[v]", "-map", audio_src, "-c:v", "libx264", "-preset", "slow", "-crf", "18",
        "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart",
        a.out])
    i = probe(a.out)
    print("comparison: %s  %dx%d  %.2fs" % (a.out, i["width"], i["height"], i["duration"]))


def main():
    p = argparse.ArgumentParser()
    sp = p.add_subparsers(dest="cmd", required=True)
    x = sp.add_parser("check"); x.add_argument("video"); x.add_argument("outdir")
    x.set_defaults(f=cmd_check)
    x = sp.add_parser("character"); x.add_argument("action", choices=["new", "show"])
    x.add_argument("name", help="character name (new) or profile folder (show)")
    x.add_argument("--dir", default="characters"); x.add_argument("--sheet"); x.add_argument("--face")
    x.add_argument("--appearance", default=""); x.set_defaults(f=cmd_character)
    x = sp.add_parser("prompt"); x.add_argument("--char", action="append", required=True)
    x.add_argument("--target", action="append", required=True)
    x.add_argument("--keep", default=""); x.add_argument("--extra", action="append", default=[])
    x.add_argument("--audio", default="keep"); x.add_argument("--out", default="prompt.txt")
    x.set_defaults(f=cmd_prompt)
    x = sp.add_parser("run"); x.add_argument("video"); x.add_argument("refs", nargs="*")
    x.add_argument("--char", action="append", default=[])
    x.add_argument("--prompt-file", required=True); x.add_argument("--out", default="swapped.mp4")
    x.add_argument("--resolution", default="1080p", choices=["480p", "720p", "1080p"])
    x.add_argument("--audio", default="keep", choices=["keep", "generate"])
    x.add_argument("--timeout", type=int, default=1800)
    x.add_argument("--dry-run", action="store_true"); x.set_defaults(f=cmd_run)
    x = sp.add_parser("query"); x.add_argument("task_id"); x.add_argument("--out", default="swapped.mp4")
    x.add_argument("--timeout", type=int, default=1800); x.set_defaults(f=cmd_query)
    x = sp.add_parser("compare"); x.add_argument("original"); x.add_argument("generated")
    x.add_argument("--out", default="compare.mp4"); x.add_argument("--font")
    x.add_argument("--left", default="原视频"); x.add_argument("--right", default="AI 换人后")
    x.add_argument("--audio", default="original", choices=["original", "generated"])
    x.set_defaults(f=cmd_compare)
    a = p.parse_args()
    a.f(a)


if __name__ == "__main__":
    main()
