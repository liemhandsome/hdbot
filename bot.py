#!/usr/bin/env python3
"""
Discord Bot - HD Compiler
Dùng monkey network (mitmproxy/requests patching) để bypass nếu cần.
Lấy compiler từ GitHub, nhận file .asm từ Discord, trả kết quả.

Cài đặt:
    pip install discord.py requests

Dùng:
    BOT_TOKEN=xxx python bot.py
"""

import discord
import subprocess
import tempfile
import os
import sys
import shutil
import asyncio
import requests

# ── CẤU HÌNH ────────────────────────────────────────────────
BOT_TOKEN    = os.environ.get("BOT_TOKEN", "MTM5NDMyMTc5NjA5ODE2Mjc0OA.Gc4WfH.PqPZBdGXhOAtmcUerkdMh34ox-pHerEcPhKuL8")
GITHUB_REPO  = "https://github.com/liemhandsome/hdbot"
COMPILER_DIR = os.path.join(os.path.dirname(__file__), "hdcompiler")
# Monkey-patch network: tất cả request qua proxy nếu được set
PROXY = os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY")
if PROXY:
    proxies = {"http": PROXY, "https": PROXY}
    _orig_get = requests.get
    def _patched_get(url, **kw):
        kw.setdefault("proxies", proxies)
        kw.setdefault("verify", False)
        return _orig_get(url, **kw)
    requests.get = _patched_get
    print(f"[monkey] Proxy đã bật: {PROXY}")

# ── CLONE / UPDATE COMPILER ──────────────────────────────────
def ensure_compiler():
    """Clone hoặc pull repo compiler từ GitHub."""
    if os.path.isdir(os.path.join(COMPILER_DIR, ".git")):
        print("[compiler] Đang pull cập nhật...")
        subprocess.run(["git", "-C", COMPILER_DIR, "pull"], check=True)
    else:
        print(f"[compiler] Đang clone {GITHUB_REPO} ...")
        os.makedirs(COMPILER_DIR, exist_ok=True)
        subprocess.run(["git", "clone", GITHUB_REPO, COMPILER_DIR], check=True)
    print("[compiler] Sẵn sàng.")

# ── CHẠY COMPILER ────────────────────────────────────────────
def run_compiler(asm_text: str, model: str = "580vnx", fmt: str = "hex") -> tuple[str, str]:
    """
    Chạy compiler với asm_text qua stdin.
    Trả về (stdout, stderr).
    model: '580vnx' | '570esp'
    fmt  : 'hex'    | 'key'
    """
    if model == "580vnx":
        script = os.path.join(COMPILER_DIR, "580vnx", "compiler_.py")
    else:
        script = os.path.join(COMPILER_DIR, "570esp", "compiler.py")

    if not os.path.isfile(script):
        return "", f"Không tìm thấy compiler: {script}"

    env = os.environ.copy()
    env["PYTHONPATH"] = COMPILER_DIR

    try:
        proc = subprocess.run(
            [sys.executable, script, "-f", fmt],
            input=asm_text,
            capture_output=True,
            text=True,
            timeout=30,
            cwd=os.path.dirname(script),
            env=env,
        )
        return proc.stdout.strip(), proc.stderr.strip()
    except subprocess.TimeoutExpired:
        return "", "Timeout: compiler chạy quá 30 giây."
    except Exception as ex:
        return "", str(ex)

# ── DISCORD BOT ───────────────────────────────────────────────
intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

HELP_TEXT = """```
HD Compiler Bot
───────────────
!compile [model] [fmt]
  Đính kèm file .asm hoặc paste code trong code block.
  model : 580vnx (mặc định) | 570esp
  fmt   : hex (mặc định)    | key

!update   – Pull compiler mới nhất từ GitHub
!help     – Hiển thị trợ giúp này

Ví dụ:
  !compile                  ← dùng file đính kèm
  !compile 580vnx key       ← output dạng key-press
```"""

@client.event
async def on_ready():
    print(f"[bot] Đăng nhập: {client.user}")

@client.event
async def on_message(msg: discord.Message):
    if msg.author.bot:
        return

    content = msg.content.strip()

    # ── !help ──
    if content == "!help":
        await msg.reply(HELP_TEXT)
        return

    # ── !update ──
    if content == "!update":
        await msg.reply("⏳ Đang pull từ GitHub...")
        try:
            ensure_compiler()
            await msg.reply("✅ Compiler đã được cập nhật.")
        except Exception as ex:
            await msg.reply(f"❌ Lỗi:\n```{ex}```")
        return

    # ── !compile ──
    if content.startswith("!compile"):
        parts  = content.split()
        model  = "580vnx"
        fmt    = "hex"
        for p in parts[1:]:
            if p in ("580vnx", "570esp"):
                model = p
            elif p in ("hex", "key"):
                fmt = p

        asm_text = None

        # 1. File đính kèm .asm
        for att in msg.attachments:
            if att.filename.endswith(".asm") or att.filename.endswith(".txt"):
                asm_text = (await att.read()).decode("utf-8", errors="replace")
                break

        # 2. Code block trong message
        if asm_text is None:
            txt = msg.content
            if "```" in txt:
                start = txt.find("```") + 3
                # bỏ tên ngôn ngữ nếu có
                if txt[start:start+10].split("\n")[0].isalpha():
                    start = txt.index("\n", start) + 1
                end = txt.rfind("```")
                asm_text = txt[start:end].strip()

        if not asm_text:
            await msg.reply("❓ Vui lòng đính kèm file `.asm` hoặc paste code trong ` ``` `.")
            return

        await msg.reply(f"⚙️ Đang compile `{model}` / `{fmt}`...")

        stdout, stderr = run_compiler(asm_text, model, fmt)

        if stdout:
            # Nếu output dài, gửi file
            if len(stdout) > 1800:
                with tempfile.NamedTemporaryFile(suffix=".txt", delete=False, mode="w") as f:
                    f.write(stdout)
                    fname = f.name
                await msg.reply(
                    "✅ Kết quả (file):",
                    file=discord.File(fname, filename="output.txt")
                )
                os.unlink(fname)
            else:
                await msg.reply(f"✅ Kết quả:\n```\n{stdout}\n```")
        
        if stderr:
            # Chỉ hiện 1500 ký tự đầu stderr
            preview = stderr[:1500]
            await msg.reply(f"⚠️ Lỗi/Log:\n```\n{preview}\n```")

        if not stdout and not stderr:
            await msg.reply("⚠️ Compiler không có output.")

# ── MAIN ─────────────────────────────────────────────────────
if __name__ == "__main__":
    try:
        ensure_compiler()
    except Exception as ex:
        print(f"[WARN] Không clone được compiler: {ex}")
        print("       Bot vẫn chạy, dùng !update để thử lại.")

    client.run(BOT_TOKEN)
