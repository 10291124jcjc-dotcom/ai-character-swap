---
name: ai-character-swap
description: 用 AI 角色复刻爆款视频：设计原创夸张角色并保存成可复用的角色档案，挑选适合换人的爆款视频，通过 Seedance 2.5 API 把视频里的一个或多个人换成角色，自动下载成片、生成"原视频 vs 换人后"对比视频，并写好发布文案。用户想做 AI 角色号、给视频换人、复刻 TikTok/IG 上 AI 怪人类爆款时使用。
---

# AI 角色换人爆款（Seedance 2.5 API 版）

一句话做法：**不再自己拍爆款，而是挑已经火了的视频，把里面的人换成你的 AI 角色。**

流程：设计角色 → 生成设定图 → 存成角色档案 → 挑视频并检查 → 上传视频 → 生成提示词 → API 生成 → 检查成片 → 对比视频 → 发布文案。

本文末尾附带脚本 `seedance_swap.py`，只依赖 Python 3 标准库和 ffmpeg。

---

## 0. 底线规则

- **角色必须是原创的。** 不能用明星、政治人物、网红或身边人的照片做原型，也不能做"一看就是在模仿某个真人"的角色。遇到这类要求，说明原因，并引导用户设计原创角色。平台审核也会直接拦截真人面孔。
- 原视频如果是别人的作品，提醒用户一次版权风险：最好用可以二创的素材，或者只借用动作、自己重新拍。只提一次。
- **发布时必须标注 AI 生成**（见第 11 节）。

---

## 1. 准备工作（只需做一次）

1. **开通 Seedance 2.5 API**
   - 海外：BytePlus ModelArk，模型 ID `dreamina-seedance-2-5-260628`，接口地址 `https://ark.ap-southeast.bytepluses.com/api/v3`（默认值）
   - 国内：火山方舟，接口地址 `https://ark.cn-beijing.volces.com/api/v3`，模型 ID 以控制台显示的为准
   - 在控制台开通模型、充值，然后创建 **API Key**
2. **设置环境变量**（Key 绝不写进任何文件、聊天记录或记忆）：
   ```bash
   export ARK_API_KEY=你的key
   # 用火山方舟时再加：
   export ARK_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
   export SEEDANCE_MODEL=控制台里的模型ID
   ```
3. **安装 ffmpeg**：macOS 用 `brew install ffmpeg`，Windows 用 `winget install ffmpeg`
4. 准备脚本：Skill 目录里有 `scripts/seedance_swap.py` 就直接复制到工作目录；没有的话，把本文末尾的 `seedance_swap.py` **原样**写出来
5. **网络**：脚本要能访问上面的接口地址。如果当前环境连不上（比如云端沙盒有白名单限制），告诉用户需要在自己的电脑上运行，然后停下，不要反复重试。

**关于接口参数**：请求格式依据 BytePlus 官方提供给 ComfyUI 的 Seedance 2.5 接入代码整理。第一次使用先跑 `--dry-run` 检查请求，再拿一条短视频试跑；接口返回的字段和脚本不一致时，按报错信息调整。

用户如果没有 API、不会命令行，就把附带的 `新手说明.md` 发给他，或者走文末的网页版做法。

---

## 2. 设计角色

**核心原则：夸张要长在人身上，而不是穿在身上。**

- 把一两个**身体特征**放大到离谱：发型、胡子、脸型、脖子、体型
- 其他地方保持**普通、写实**，像现实中真有这个人
- **服装固定一套**，每条视频都一样，观众才能一眼认出来
- 要有**反差**：角色气质和他要出现的场景越不搭越好

反面例子：靠戏服、盔甲、cosplay 堆出来的"夸张"，脱掉衣服就是普通人。

先给出 2～3 个角色方向（一眼印象、关键特征、反差点、适合什么场景），等用户选定一个再继续。

**案例（闻先生）**：明朝书生的脑袋加打工人的身子。巨大的古代发髻横插一根绿玉簪，小圆墨镜，细长胡须；穿大两号的米色亚麻西装，挂蓝色工牌，白袜配黑拖鞋，一脸疲惫的面瘫。

---

## 3. 生成角色设定图

用 ChatGPT（或其他生图工具）生成，英文提示词更稳定。

**设定图**（方括号换成角色描述）：
```
Professional character reference sheet of an original fictional character, photorealistic photography, neutral light grey studio background, soft even lighting. Top row: five full-body views of the same person standing straight — front, three-quarter front, side profile, three-quarter back, back. Bottom row: three close-up portraits — front face, three-quarter face, and one expressive shot [a gesture that fits the character]. [Character description: age, build, face, hair, the one or two exaggerated features, full outfit, shoes, accessories, expression]. Real person, realistic skin texture and hair detail, identical in every view, no text, not resembling any real person.
```

**正脸半身照**（同一个对话里接着发）：
```
Keep exactly the same character: same face, same hair, same outfit and accessories. Generate one photorealistic front-facing portrait from the waist up, neutral light grey studio background, soft even lighting, sharp detail, no text.
```

**检查清单**（用 Read 查看用户发回的图）：
- 各角度是不是同一个人：发型、服装颜色、配饰位置一致
- 标志性特征在每个角度都清楚
- 脸普通、写实，**不像任何明星或真人**，像的话重新生成
- 没有乱码文字（比如工牌上的字）
- 夸张的发型够不够大

---

## 4. 存成角色档案

同一个角色以后会反复用，所以要把设定图、正脸照和一段**固定的外貌描述**存成档案。每次换人都调用同一份档案，角色才不会走样。

```bash
python3 seedance_swap.py character new 闻先生 \
  --sheet 设定图.png --face 正脸照.png \
  --appearance "头顶一个巨大的黑色古代发髻，横插一根长长的绿色玉簪；极小的圆形黑色墨镜；细长的黑色山羊胡垂到胸口；瘦长脸，脖子细长，面无表情；穿大两号的米色亚麻西装和白衬衫，挂蓝色挂绳工牌，白袜子配黑色拖鞋。"
```
- 档案保存在 `characters/闻先生/`，包括 `character.json`、`sheet.png` 和 `face.png`
- **外貌描述**要写成提示词里直接能用的一段中文：标志特征放最前面，接着写脸、体型、表情、整套服装和鞋
- 图片已经上传到控制台素材库的，`--sheet`、`--face` 可以直接填 `asset://素材ID`
- 用 `character show characters/闻先生` 查看档案
- 用户以后说"用闻先生换这条"，就直接用这个档案，不用重新描述

---

## 5. 挑选并检查视频

好换的视频：
- **人越少越好**，一个人最稳；多人见第 7 节
- **镜头稳**，不剧烈晃动、不频繁切镜头
- **头顶有空间**，尤其是有高发型的角色
- **时长 1.8～30 秒**（Seedance 2.5 参考视频的范围）
- 动作清楚、拖影少；快速动作的手部容易糊

**最出效果的是反差**，比如面瘫古人在拳馆狂打空拳。

```bash
python3 seedance_swap.py check 原视频.mp4 work
```
- 打印分辨率、像素数、时长，是否带音频
- **像素（宽×高）低于 409,600 时自动放大**到短边 720，输出 `work/upscaled.mp4`。放大只是为了满足接口要求，原本的模糊不会变清楚
- 超过 30 秒会提示：先在镜头切换或动作停顿处切成两段，分别生成
- 生成 8 帧预览图 `work/preview.jpg`。**写提示词前必须用 Read 查看**：要换的人在什么位置、穿什么、在做什么，是否光着上身，手里拿着什么，头顶空间够不够

---

## 6. 上传参考视频

**参考视频必须是公开链接或控制台素材库的 `asset://素材ID`**，不能直接用本地文件。让用户把 `work/upscaled.mp4`（没放大就用原视频）上传到控制台素材库，把素材 ID 告诉你。

参考图（角色档案里的本地图片）脚本会自动转成 base64 发送，不用上传。

**写实人脸的注意事项**：如果任务因为"真人人脸"被拦截，即使角色是 AI 生成的，也要把设定图和正脸照上传到控制台的**私有虚拟人像库**，再用 `character new` 把档案里的图换成对应的 `asset://` ID。

---

## 7. 生成提示词

用 `prompt` 命令根据角色档案自动生成，@图片 的编号会自动对齐，不会写错。

**换一个人**：
```bash
python3 seedance_swap.py prompt --char characters/闻先生 --target "画面中央在拳馆里打空拳的赤膊男子" \
  --extra "他穿着完整的西装，不要赤膊，不要肌肉。" --out work/prompt.txt
```

**换多个人**：每个 `--char` 后面跟一个对应的 `--target`，顺序一一对应：
```bash
python3 seedance_swap.py prompt \
  --char characters/闻先生 --target "左边穿黑外套的男子" \
  --char characters/铁梅婆婆 --target "右边穿红裙子的女子" \
  --keep "背景里的路人" --out work/prompt.txt
```
- `--target`：用**位置、衣着、动作**锁定要换的人，越具体越不容易换错
- `--keep`：写明哪些人不换
- `--extra`：按视频情况追加的句子，可以写多条：
  - 原视频的人**光着上身**："他穿着[服装]，衣服完整穿着，不要赤膊，不要肌肉。"
  - 有**缠手、手套**要保留："手上保留[细节]。"
  - **动作幅度大**："服装随动作自然摆动，[头发、胡子]随动作轻微晃动。"
  - 有**高发型**："发型不要被画面边缘切掉。"
- 生成后打印全文和字数。超过 800 字会提醒精简，太长容易触发审核

**多人替换的建议**：
- 一次最多换 3～4 个人，人越多越容易换错、特征混在一起
- 每个角色带 1～2 张图就够了（一次最多 30 张参考图）
- 人更多，或者第一次跑时换错了：**分两轮**。第一轮只换一部分人，跑完后把 `work/swapped.mp4.url.txt` 里的结果链接作为第二轮的参考视频，再换剩下的人（第二轮用 `--keep` 写明第一轮已经换好的角色）。这个链接大约 24 小时有效，费用也会翻倍，要先告诉用户

---

## 8. 调用 API 生成

先检查请求内容，确认角色和图片编号对得上：
```bash
python3 seedance_swap.py run asset://视频素材ID --char characters/闻先生 --prompt-file work/prompt.txt --dry-run
```
确认无误后正式提交（多人就写多个 `--char`，顺序和生成提示词时一致）：
```bash
python3 seedance_swap.py run asset://视频素材ID --char characters/闻先生 --prompt-file work/prompt.txt --out work/swapped.mp4 --resolution 1080p
```
- 使用视频编辑模式，比例和时长自动跟随原视频
- `--audio keep`（默认）不生成新音频，对比视频会用原声；`--audio generate` 让模型生成音频
- 每 15 秒查询一次进度，完成后自动下载到 `--out`，结果链接另存到 `--out.url.txt`
- 中途中断或超时，用打印出的任务 ID 继续：`python3 seedance_swap.py query 任务ID --out work/swapped.mp4`
- 提交前告诉用户这次会产生费用，按生成秒数和分辨率计费，以控制台价格为准

---

## 9. 检查成片

```bash
python3 -c "import seedance_swap as s; s.grid('work/swapped.mp4','work/swapped_preview.jpg')"
```
用 Read 查看预览图，检查：
- 角色的脸、发型、标志特征前后是否一致
- 动作是否跟原视频同步
- 场景和道具有没有被改动
- 多人时：有没有换错人、角色互换或特征混在一起
- 手部有没有严重变形，发型有没有被切掉

| 问题 | 怎么改 |
|---|---|
| 人物长相跑偏 | 把档案里的外貌描述写得更具体，标志特征放最前面，然后重建档案 |
| 生成了肌肉、赤膊 | `--extra` 加上"衣服完整穿着，不要赤膊" |
| 多出了道具 | 提示词里已有"不要额外添加道具"，再用 `--extra` 点名这个道具 |
| 场景被改了 | `--extra` 把要保留的场景元素逐项写进去 |
| 多人换错、互换 | `--target` 写得更具体（位置加衣着）；减少单轮人数，分两轮 |
| 审核拦截、真人人脸报错 | 检查原视频和参考图；把角色图放进私有虚拟人像库再用 asset ID；精简提示词 |
| HTTP 401 / 403 | API Key 不对，或者模型还没开通 |
| 参考视频报错 | 检查像素（≥409,600）、时长（1.8～30 秒），以及链接是否公开可访问 |

---

## 10. 做对比视频

```bash
python3 seedance_swap.py compare 原视频.mp4 work/swapped.mp4 --out work/对比视频.mp4
```
- 左边原视频，右边换人后，顶部各有一个半透明标签（"原视频"/"AI 换人后"），可以用 `--left` `--right` 改文字
- 两边裁成同样比例，没有黑边；声音默认用原视频的原声，`--audio generated` 改用生成的声音
- 自动查找中文字体（macOS 苹方、Windows 微软雅黑、Linux 用 fc-list），找不到时用 `--font 字体路径` 指定
- 做完抽一帧检查：两边动作是否同步，标签有没有挡住角色的脸和发型

把**对比视频**和**成片**都发给用户。

---

## 11. 写发布文案

**角色号本身（TikTok / IG）**：
- 发**成片**，屏幕字幕放在画面上三分之一，不要挡住角色的标志特征；最多两行，前 2 秒就出现
- 字幕走角色人设，比如闻先生是"面瘫古人吐槽现代生活"
- **必须打开平台的 AI 生成内容标签**：TikTok 发布时打开 "AI-generated content"，IG 打开 "AI info / Made with AI" 标签。写实的 AI 内容不标注，可能被限流或删除

**教程号（推特等，讲"怎么做出来的"）**，用两条推接力：
1. **引子推**：外网案例加一个能查到的惊人数字，比如"9 条视频，46 万粉，播放破亿。主角是一个不存在的人。"，配对方主页截图
2. **引用推**：引用自己的引子推，第一句"上面这个号的打法，我们跑通了"，接着用一两句讲清方法，配**对比视频和设定图**
3. **回复串**：① 做角色 ② 挑视频 ③ 换人（附提示词原文）④ 踩过的坑，最后一条贴来源链接

**写法规则**：
- 一行一句，直接下判断，不讲故事，不写感慨
- 数字具体、可查，不确定的写"博主说"
- 工具要点名，提示词给原文，方便收藏
- 不编造经历和数据

先给用户 2～3 个不同角度的版本，让他挑一个，再按他的反馈改。

---

## 附：没有 API 时的网页版做法

在 Seedance 2.5 网页版"全能参考"里，依次上传原视频（@视频1）和角色图（@图片1、@图片2……，多角色按档案顺序上传），比例选"跟随参考视频"，时长和原视频一致，粘贴第 7 节生成的提示词。下载成片后，仍然可以用第 10 节的命令做对比视频。

---

## seedance_swap.py

```python
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
```
