#!/usr/bin/env python3
import discord
from discord import app_commands
import subprocess, tempfile, os, sys, requests

# ── CẤU HÌNH ────────────────────────────────────────────────
BOT_TOKEN    = os.environ.get("BOT_TOKEN", "")
GITHUB_REPO  = "https://github.com/liemhandsome/hdcompiler"
COMPILER_DIR = os.path.join(os.path.dirname(__file__), "hdcompiler")

# ── CLONE COMPILER ───────────────────────────────────────────
def ensure_compiler():
    if os.path.isdir(os.path.join(COMPILER_DIR, ".git")):
        subprocess.run(["git", "-C", COMPILER_DIR, "pull"], check=True)
    else:
        os.makedirs(COMPILER_DIR, exist_ok=True)
        subprocess.run(["git", "clone", GITHUB_REPO, COMPILER_DIR], check=True)

# ── CHẠY COMPILER ────────────────────────────────────────────
def run_compiler(asm_text: str, model="580vnx", fmt="hex"):
    if model == "580vnx":
        script = os.path.join(COMPILER_DIR, "580vnx", "compiler_.py")
    else:
        script = os.path.join(COMPILER_DIR, "570esp", "compiler.py")
    if not os.path.isfile(script):
        return "", f"Không tìm thấy compiler: {script}"
    try:
        proc = subprocess.run(
            [sys.executable, script, "-f", fmt],
            input=asm_text, capture_output=True, text=True, timeout=30,
            cwd=os.path.dirname(script),
        )
        return proc.stdout.strip(), proc.stderr.strip()
    except subprocess.TimeoutExpired:
        return "", "Timeout: quá 30 giây."
    except Exception as ex:
        return "", str(ex)

# ── BOT SETUP ────────────────────────────────────────────────
intents = discord.Intents.default()
intents.message_content = True

class HDBot(discord.Client):
    def __init__(self):
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
    async def setup_hook(self):
        await self.tree.sync()
        print("[bot] Slash commands đã sync")

client = HDBot()

# ── SLASH: /compile ──────────────────────────────────────────
@client.tree.command(name="compile", description="Compile code ASM cho máy tính Casio")
@app_commands.describe(
    code  = "Code ASM cần compile",
    model = "Model máy tính (mặc định: 580vnx)",
    fmt   = "Format output (mặc định: hex)",
)
@app_commands.choices(
    model=[
        app_commands.Choice(name="580vnx", value="580vnx"),
        app_commands.Choice(name="570esp", value="570esp"),
    ],
    fmt=[
        app_commands.Choice(name="hex", value="hex"),
        app_commands.Choice(name="key", value="key"),
    ]
)
async def slash_compile(
    interaction: discord.Interaction,
    code: str,
    model: str = "580vnx",
    fmt: str = "hex",
):
    await interaction.response.defer()
    stdout, stderr = run_compiler(code, model, fmt)
    if stdout:
        if len(stdout) > 1800:
            with tempfile.NamedTemporaryFile(suffix=".txt", delete=False, mode="w") as f:
                f.write(stdout)
                fname = f.name
            await interaction.followup.send("✅ Kết quả:", file=discord.File(fname, "output.txt"))
            os.unlink(fname)
        else:
            await interaction.followup.send(f"✅ Kết quả:\n```\n{stdout}\n```")
    if stderr:
        await interaction.followup.send(f"⚠️ Lỗi:\n```\n{stderr[:1500]}\n```")
    if not stdout and not stderr:
        await interaction.followup.send("⚠️ Không có output.")

# ── SLASH: /update ───────────────────────────────────────────
@client.tree.command(name="update", description="Pull compiler mới nhất từ GitHub")
async def slash_update(interaction: discord.Interaction):
    await interaction.response.defer()
    try:
        ensure_compiler()
        await interaction.followup.send("✅ Compiler đã cập nhật!")
    except Exception as ex:
        await interaction.followup.send(f"❌ Lỗi:\n```{ex}```")

# ── SLASH: /help ─────────────────────────────────────────────
@client.tree.command(name="help", description="Hướng dẫn dùng bot")
async def slash_help(interaction: discord.Interaction):
    await interaction.response.send_message("""```
HD Compiler Bot
───────────────
Slash commands:
  /compile code:<code> [model] [fmt]
  /update
  /help

Prefix commands:
  !c <code>     compile nhanh
  !compile      compile file .asm đính kèm
```""")

# ── PREFIX COMMANDS ───────────────────────────────────────────
@client.event
async def on_ready():
    print(f"[bot] Đăng nhập: {client.user}")

@client.event
async def on_message(msg: discord.Message):
    if msg.author.bot:
        return
    content = msg.content.strip()

    if content.startswith("!c "):
        asm_text = content[3:].strip()
        await msg.reply("⚙️ Đang compile...")
        stdout, stderr = run_compiler(asm_text)
        if stdout:
            await msg.reply(f"✅\n```\n{stdout}\n```")
        if stderr:
            await msg.reply(f"⚠️\n```\n{stderr[:1500]}\n```")
        return

    if content.startswith("!compile"):
        parts = content.split()
        model, fmt = "580vnx", "hex"
        for p in parts[1:]:
            if p in ("580vnx", "570esp"): model = p
            elif p in ("hex", "key"):     fmt = p
        asm_text = None
        for att in msg.attachments:
            if att.filename.endswith((".asm", ".txt")):
                asm_text = (await att.read()).decode("utf-8", errors="replace")
                break
        if asm_text is None and "```" in content:
            start = content.find("```") + 3
            if content[start:start+10].split("\n")[0].isalpha():
                start = content.index("\n", start) + 1
            end = content.rfind("```")
            asm_text = content[start:end].strip()
        if not asm_text:
            await msg.reply("❓ Đính kèm file `.asm` hoặc paste code trong ` ``` `")
            return
        await msg.reply("⚙️ Đang compile...")
        stdout, stderr = run_compiler(asm_text, model, fmt)
        if stdout:
            await msg.reply(f"✅\n```\n{stdout}\n```")
        if stderr:
            await msg.reply(f"⚠️\n```\n{stderr[:1500]}\n```")

# ── MAIN ─────────────────────────────────────────────────────
if __name__ == "__main__":
    try:
        ensure_compiler()
    except Exception as ex:
        print(f"[WARN] {ex}")
    client.run(BOT_TOKEN)
