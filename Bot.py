import os
import subprocess, sys
def _ensure(pkg, mod=None):
    mod = mod or pkg
    try: __import__(mod)
    except ImportError: subprocess.check_call([sys.executable, "-m", "pip", "install", pkg])
for _p, _m in [("discord.py", "discord"), ("aiohttp", "aiohttp")]:
    _ensure(_p, _m)

# ============================================================
#  設定
# ============================================================
TOKEN            = "MTU1NjI1NTg0MTY2ODMwMDgzMA.GGk0E8.shn6XgYEE9ONwTm70tzNYtx4sQ7uhe42W4BY9Q"
GUILD_ID         = 1514282021365616892
BUYER_ROLE_ID    = 1532321061247385640
SCRIPT_URL       = "https://gist.githubusercontent.com/hubsilent45-boop/6658746c2316d2d3da64dc5eae6c493e/raw/loader.lua"
MAIN_SCRIPT_PATH = "main.lua"
API_PORT         = int(os.getenv("PORT", 8080))
# ============================================================

import sqlite3, secrets, string, asyncio, datetime as dt
import discord
from discord import app_commands
from discord.ext import commands
from aiohttp import web

DB_PATH = "licenses.db"
DROPS = {}

# ---------- main.lua メモリキャッシュ ----------
_MAIN_CACHE = None
_MAIN_CACHE_MTIME = 0

def get_main_script():
    global _MAIN_CACHE, _MAIN_CACHE_MTIME
    if not os.path.exists(MAIN_SCRIPT_PATH):
        return None
    mtime = os.path.getmtime(MAIN_SCRIPT_PATH)
    if _MAIN_CACHE is None or mtime != _MAIN_CACHE_MTIME:
        with open(MAIN_SCRIPT_PATH, "r", encoding="utf-8") as f:
            _MAIN_CACHE = f.read()
        _MAIN_CACHE_MTIME = mtime
    return _MAIN_CACHE

def db_init():
    con = sqlite3.connect(DB_PATH)
    con.execute("""CREATE TABLE IF NOT EXISTS keys (
        key TEXT PRIMARY KEY, discord_id INTEGER, hwid TEXT, note TEXT,
        created_at INTEGER, expires_at INTEGER, banned INTEGER DEFAULT 0, last_used INTEGER)""")
    con.commit(); con.close()

def db():
    con = sqlite3.connect(DB_PATH); con.row_factory = sqlite3.Row; return con

def now_ts(): return int(dt.datetime.now().timestamp())

def gen_key(prefix="LUA"):
    a = string.ascii_uppercase + string.digits
    b = "".join(secrets.choice(a) for _ in range(24))
    return f"{prefix}-{b[:6]}-{b[6:12]}-{b[12:18]}-{b[18:24]}"

def get_user_key(discord_id):
    con = db()
    row = con.execute(
        "SELECT * FROM keys WHERE discord_id=? ORDER BY created_at DESC LIMIT 1",
        (discord_id,)
    ).fetchone()
    con.close()
    return row

db_init()

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree
def is_admin(i): return i.user.guild_permissions.administrator

# ============================================================
#  モーダル
# ============================================================

class RedeemModal(discord.ui.Modal):
    key_input = discord.ui.TextInput(label="キー", placeholder="LUA-XXXXXX-XXXXXX-XXXXXX-XXXXXX", required=True)
    def __init__(self):
        super().__init__(title="キーを入力")

    async def on_submit(self, interaction: discord.Interaction):
        key = self.key_input.value.strip()
        con = db()
        row = con.execute("SELECT * FROM keys WHERE key=?", (key,)).fetchone()
        if not row:
            con.close()
            return await interaction.response.send_message("❌ キーが見つかりません。", ephemeral=True)
        if row["banned"]:
            con.close()
            return await interaction.response.send_message("🚫 このキーはBANされています。", ephemeral=True)
        if row["expires_at"] != 0 and row["expires_at"] < now_ts():
            con.close()
            return await interaction.response.send_message("⏰ このキーは期限切れです。", ephemeral=True)

        con.execute("UPDATE keys SET discord_id=? WHERE key=?", (interaction.user.id, key))
        con.commit()
        role_msg = ""
        if BUYER_ROLE_ID:
            try:
                role = interaction.guild.get_role(BUYER_ROLE_ID)
                if role:
                    await interaction.user.add_roles(role)
                    role_msg = f"\n{role.mention} を付与しました。"
            except Exception as e:
                print("role error:", e)
        con.close()
        e = discord.Embed(title="✅ キー認証成功", color=0x00ff88)
        e.add_field(name="キー", value=f"`{key}`", inline=False)
        e.add_field(name="期限", value=("無期限" if row['expires_at'] == 0 else f"<t:{row['expires_at']}:R>"))
        e.set_footer(text="「Get Script」からローダーを取得してください。")
        await interaction.response.send_message(content=role_msg or None, embed=e, ephemeral=True)

# ============================================================
#  パネル
# ============================================================

class PanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Redeem Key", emoji="🔑", style=discord.ButtonStyle.success, custom_id="panel_redeem", row=0)
    async def redeem(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(RedeemModal())

    @discord.ui.button(label="Get Script", emoji="📜", style=discord.ButtonStyle.primary, custom_id="panel_script", row=0)
    async def script(self, interaction: discord.Interaction, button: discord.ui.Button):
        row = get_user_key(interaction.user.id)
        if not row:
            return await interaction.response.send_message(
                "❌ キーがありません。キーを取得してください。", ephemeral=True
            )
        if row["banned"]:
            return await interaction.response.send_message("🚫 あなたのキーはBANされています。", ephemeral=True)
        if row["expires_at"] != 0 and row["expires_at"] < now_ts():
            return await interaction.response.send_message("⏰ あなたのキーは期限切れです。", ephemeral=True)

        try:
            dm = await interaction.user.create_dm()
            code = f'loadstring(game:HttpGet("{SCRIPT_URL}"))()'
            msg = (
                f"📜 **Silent Hub Loader**\n\n"
                f"🔑 **あなたのキー:**\n`{row['key']}`\n\n"
                f"📥 **ローダー（タップでコピー）:**\n`{code}`"
            )
            await dm.send(msg)
            await interaction.response.send_message("✅ DMに送りました。", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message("⚠️ DMを開放してください。", ephemeral=True)

    @discord.ui.button(label="Get Role", emoji="👤", style=discord.ButtonStyle.primary, custom_id="panel_role", row=0)
    async def role_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not BUYER_ROLE_ID:
            return await interaction.response.send_message("⚠️ ロールが設定されていません（管理者へ）。", ephemeral=True)
        try:
            role = interaction.guild.get_role(BUYER_ROLE_ID)
            await interaction.user.add_roles(role)
            await interaction.response.send_message(f"✅ {role.mention} を付与しました。", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ 失敗: {e}", ephemeral=True)

    @discord.ui.button(label="Reset HWID", emoji="⚙️", style=discord.ButtonStyle.secondary, custom_id="panel_reset", row=0)
    async def reset_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        row = get_user_key(interaction.user.id)
        if not row:
            return await interaction.response.send_message(
                "❌ キーがありません。キーを取得してください。", ephemeral=True
            )
        con = db()
        con.execute("UPDATE keys SET hwid=NULL WHERE key=?", (row["key"],))
        con.commit(); con.close()
        e = discord.Embed(title="✅ HWIDをリセットしました", color=0x00ff88)
        e.add_field(name="キー", value=f"`{row['key']}`", inline=False)
        e.description = "次回起動時に再紐付けされます。"
        await interaction.response.send_message(embed=e, ephemeral=True)

    @discord.ui.button(label="Get Stats", emoji="📊", style=discord.ButtonStyle.secondary, custom_id="panel_stats", row=0)
    async def stats_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        row = get_user_key(interaction.user.id)
        if not row:
            return await interaction.response.send_message(
                "❌ キーがありません。キーを取得してください。", ephemeral=True
            )
        e = discord.Embed(title="📊 キー統計", color=0x9b59b6)
        e.add_field(name="キー", value=f"`{row['key']}`", inline=False)
        e.add_field(name="HWID", value=(row['hwid'] or "未紐付け"))
        e.add_field(name="BAN", value=("はい" if row['banned'] else "いいえ"))
        e.add_field(name="期限", value=("無期限" if row['expires_at'] == 0 else f"<t:{row['expires_at']}:R>"))
        e.add_field(name="最終使用", value=(f"<t:{row['last_used']}:R>" if row['last_used'] else "未使用"))
        if row['note']: e.add_field(name="メモ", value=row['note'], inline=False)
        await interaction.response.send_message(embed=e, ephemeral=True)

# ============================================================
#  キードロップ
# ============================================================

class DropView(discord.ui.View):
    def __init__(self, key: str, note: str = ""):
        super().__init__(timeout=None)
        self.key = key
        self.note = note

    @discord.ui.button(label="キーを受け取る", emoji="🎁", style=discord.ButtonStyle.success, custom_id="drop_claim")
    async def claim(self, interaction: discord.Interaction, button: discord.ui.Button):
        msg_id = interaction.message.id
        if msg_id not in DROPS:
            return await interaction.response.send_message("このキーは既に配布終了しています。", ephemeral=True)
        if DROPS[msg_id]["claimed_by"] is not None:
            return await interaction.response.send_message(
                f"❌ 既に <@{DROPS[msg_id]['claimed_by']}> が受け取りました。", ephemeral=True
            )
        DROPS[msg_id]["claimed_by"] = interaction.user.id
        try:
            dm = await interaction.user.create_dm()
            e = discord.Embed(title="🎁 キーを受け取りました", color=0x00ff88)
            e.add_field(name="キー", value=f"`{self.key}`", inline=False)
            if self.note:
                e.add_field(name="メモ", value=self.note, inline=False)
            e.set_footer(text="このキーはあなた専用です。他人と共有しないでください。")
            await dm.send(embed=e)
            await interaction.response.send_message("✅ DMにキーを送りました。", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message(
                f"⚠️ DMを送れませんでした。DMを開放してください。\nキー: `{self.key}`", ephemeral=True
            )
        try:
            button.disabled = True
            button.label = f"✅ {interaction.user.display_name} が取得済み"
            await interaction.message.edit(view=self)
        except Exception:
            pass
        con = db()
        con.execute("UPDATE keys SET discord_id=? WHERE key=?", (interaction.user.id, self.key))
        con.commit(); con.close()

# ============================================================
#  コマンド
# ============================================================

@tree.command(name="roles", description="ロール一覧を表示（管理者）")
async def roles(i: discord.Interaction):
    if not is_admin(i):
        return await i.response.send_message("管理者のみ。", ephemeral=True)
    lines = []
    for r in i.guild.roles:
        if r.name == "@everyone":
            continue
        lines.append(f"`{r.id}` → {r.name}")
    e = discord.Embed(title="📋 ロール一覧", description="\n".join(lines) or "なし", color=0x9b59b6)
    await i.response.send_message(embed=e, ephemeral=True)

@tree.command(name="setpanel", description="パネルを設置（管理者）")
async def setpanel(i: discord.Interaction):
    if not is_admin(i):
        return await i.response.send_message("管理者のみ。", ephemeral=True)
    e = discord.Embed(
        title="Silent Hub - Control Panel",
        description=(
            "This control panel is for the project: **SILENT HUB**\n"
            "If you're a buyer, click on the buttons below to redeem your key, "
            "get the script or get your role."
        ),
        color=0x00ff88,
    )
    await i.channel.send(embed=e, view=PanelView())
    await i.response.send_message("✅ パネルを設置しました。", ephemeral=True)

@tree.command(name="keydrop", description="キーをチャンネルに落とす（管理者）")
@app_commands.describe(days="有効日数（0で無期限）", note="メモ")
async def keydrop(i: discord.Interaction, days: int = 30, note: str = ""):
    if not is_admin(i):
        return await i.response.send_message("管理者のみ。", ephemeral=True)
    exp = 0 if days <= 0 else now_ts() + days * 86400
    k = gen_key("DROP")
    con = db()
    con.execute("INSERT INTO keys (key,note,created_at,expires_at,banned) VALUES (?,?,?,?,0)",
                (k, note, now_ts(), exp))
    con.commit(); con.close()
    e = discord.Embed(title="🎁 キードロップ！", color=0x00ff88)
    e.description = "下のボタンを押すとキーがDMに届きます。**早い者勝ち！**"
    e.add_field(name="期限", value=("無期限" if exp == 0 else f"<t:{exp}:R>"))
    if note: e.add_field(name="メモ", value=note)
    view = DropView(k, note)
    msg = await i.channel.send(embed=e, view=view)
    DROPS[msg.id] = {"key": k, "claimed_by": None}
    await i.response.send_message("✅ キーをドロップしました。", ephemeral=True)

@tree.command(name="gen", description="キーを生成（管理者）")
@app_commands.describe(amount="生成数", days="有効日数（0で無期限）", note="メモ")
async def gen(i: discord.Interaction, amount: int = 1, days: int = 30, note: str = ""):
    if not is_admin(i): return await i.response.send_message("管理者のみ。", ephemeral=True)
    if not 1 <= amount <= 50: return await i.response.send_message("amount は1〜50。", ephemeral=True)
    exp = 0 if days <= 0 else now_ts() + days * 86400
    con = db(); cur = con.cursor(); keys = []
    for _ in range(amount):
        k = gen_key()
        cur.execute("INSERT INTO keys (key,note,created_at,expires_at,banned) VALUES (?,?,?,?,0)", (k, note, now_ts(), exp))
        keys.append(k)
    con.commit(); con.close()
    e = discord.Embed(title=f"✅ {amount}個のキーを生成", description="\n".join(f"`{k}`" for k in keys), color=0x00ff88)
    e.add_field(name="期限", value=("無期限" if exp == 0 else f"<t:{exp}:R>"))
    if note: e.add_field(name="メモ", value=note)
    await i.response.send_message(embed=e, ephemeral=True)

@tree.command(name="whitelist", description="ユーザーを追加（管理者）")
@app_commands.describe(user="対象", days="有効日数（0で無期限）", note="メモ")
async def whitelist(i: discord.Interaction, user: discord.User, days: int = 30, note: str = ""):
    if not is_admin(i): return await i.response.send_message("管理者のみ。", ephemeral=True)
    exp = 0 if days <= 0 else now_ts() + days * 86400
    k = gen_key("WL")
    con = db()
    con.execute("INSERT INTO keys (key,discord_id,note,created_at,expires_at,banned) VALUES (?,?,?,?,?,0)",
                (k, user.id, note, now_ts(), exp))
    con.commit(); con.close()
    e = discord.Embed(title="✅ ホワイトリスト追加", color=0x00ff88)
    e.add_field(name="ユーザー", value=user.mention, inline=False)
    e.add_field(name="キー", value=f"`{k}`", inline=False)
    e.add_field(name="期限", value=("無期限" if exp == 0 else f"<t:{exp}:R>"))
    await i.response.send_message(embed=e, ephemeral=True)

@tree.command(name="unwhitelist", description="ユーザーを削除（管理者）")
async def unwhitelist(i: discord.Interaction, user: discord.User):
    if not is_admin(i): return await i.response.send_message("管理者のみ。", ephemeral=True)
    con = db(); cur = con.execute("DELETE FROM keys WHERE discord_id=?", (user.id,))
    con.commit(); n = cur.rowcount; con.close()
    await i.response.send_message(f"🗑️ {user.mention} のキーを {n} 件削除。", ephemeral=True)

@tree.command(name="check", description="キー確認（管理者）")
async def check(i: discord.Interaction, key: str):
    if not is_admin(i): return await i.response.send_message("管理者のみ。", ephemeral=True)
    con = db(); r = con.execute("SELECT * FROM keys WHERE key=?", (key,)).fetchone(); con.close()
    if not r: return await i.response.send_message("❌ 見つかりません。", ephemeral=True)
    e = discord.Embed(title="🔍 キー情報", color=0x3498db)
    e.add_field(name="キー", value=f"`{r['key']}`", inline=False)
    e.add_field(name="Discord", value=(f"<@{r['discord_id']}>" if r['discord_id'] else "未紐付け"))
    e.add_field(name="HWID", value=(r['hwid'] or "未紐付け"))
    e.add_field(name="BAN", value=("はい" if r['banned'] else "いいえ"))
    e.add_field(name="期限", value=("無期限" if r['expires_at'] == 0 else f"<t:{r['expires_at']}:R>"))
    if r['note']: e.add_field(name="メモ", value=r['note'], inline=False)
    await i.response.send_message(embed=e, ephemeral=True)

@tree.command(name="ban", description="キーをBAN（管理者）")
async def ban(i: discord.Interaction, key: str):
    if not is_admin(i): return await i.response.send_message("管理者のみ。", ephemeral=True)
    con = db(); cur = con.execute("UPDATE keys SET banned=1 WHERE key=?", (key,))
    con.commit(); n = cur.rowcount; con.close()
    await i.response.send_message(("🚫 BAN。" if n else "❌ 見つかりません。"), ephemeral=True)

@tree.command(name="unban", description="BAN解除（管理者）")
async def unban(i: discord.Interaction, key: str):
    if not is_admin(i): return await i.response.send_message("管理者のみ。", ephemeral=True)
    con = db(); cur = con.execute("UPDATE keys SET banned=0 WHERE key=?", (key,))
    con.commit(); n = cur.rowcount; con.close()
    await i.response.send_message(("✅ 解除。" if n else "❌ 見つかりません。"), ephemeral=True)

@tree.command(name="info", description="自分のキー一覧")
async def info(i: discord.Interaction):
    con = db()
    rows = con.execute("SELECT * FROM keys WHERE discord_id=? ORDER BY created_at DESC", (i.user.id,)).fetchall()
    con.close()
    if not rows: return await i.response.send_message("キーがありません。キーを取得してください。", ephemeral=True)
    e = discord.Embed(title="🗝️ あなたのキー", color=0x9b59b6)
    for r in rows[:10]:
        s = []
        if r['banned']: s.append("BANNED")
        s.append("HWID紐付け済み" if r['hwid'] else "未使用")
        exp = "無期限" if r['expires_at'] == 0 else f"<t:{r['expires_at']}:R>"
        e.add_field(name=f"`{r['key']}`", value=f"状態: {', '.join(s)}\n期限: {exp}", inline=False)
    await i.response.send_message(embed=e, ephemeral=True)

# ============================================================
#  HTTP API
# ============================================================

async def api_validate(req: web.Request) -> web.Response:
    d = await req.json()
    key, hwid = d.get("key", ""), d.get("hwid", "")
    if not key or not hwid:
        return web.json_response({"valid": False, "reason": "missing_params"}, status=400)

    con = db()
    r = con.execute("SELECT * FROM keys WHERE key=?", (key,)).fetchone()
    if not r: con.close(); return web.json_response({"valid": False, "reason": "invalid_key"})
    if r["banned"]: con.close(); return web.json_response({"valid": False, "reason": "banned"})
    if r["expires_at"] != 0 and r["expires_at"] < now_ts():
        con.close(); return web.json_response({"valid": False, "reason": "expired"})

    if r["hwid"] is None:
        con.execute("UPDATE keys SET hwid=?, last_used=? WHERE key=?", (hwid, now_ts(), key)); con.commit()
    elif r["hwid"] != hwid:
        con.close(); return web.json_response({"valid": False, "reason": "hwid_mismatch"})
    else:
        con.execute("UPDATE keys SET last_used=? WHERE key=?", (now_ts(), key)); con.commit()
    con.close()

    script_body = get_main_script()
    if not script_body:
        return web.json_response({"valid": False, "reason": "script_missing"}, status=500)

    return web.json_response({
        "valid": True,
        "expires_at": r["expires_at"],
        "note": r["note"] or "",
        "script": script_body,
    })

async def api_health(req: web.Request) -> web.Response:
    return web.json_response({"ok": True})

async def run_api():
    app = web.Application()
    app.router.add_post("/api/validate", api_validate)
    app.router.add_get("/api/health", api_health)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", API_PORT).start()
    print(f"[API] http://0.0.0.0:{API_PORT}")

@bot.event
async def on_ready():
    get_main_script()
    try:
        if GUILD_ID:
            g = discord.Object(id=GUILD_ID)
            tree.copy_global_to(guild=g)
            await tree.sync(guild=g)
            print(f"[Bot] synced to guild {GUILD_ID}")
        else:
            await tree.sync()
    except Exception as e:
        print("sync error:", e)
    print(f"[Bot] logged in as {bot.user}")

async def main():
    await run_api()
    async with bot:
        await bot.start(TOKEN)

if __name__ == "__main__":
    asyncio.run(main())
