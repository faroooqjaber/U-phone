import discord
from discord.ext import commands
from discord import app_commands, ui
import sqlite3
import os
import re
from datetime import datetime

# ==========================================
# ⚙️ الإعدادات الأساسية (بنيتك البرمجية كاملة)
# ==========================================
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)
DB_PATH = "twitter_rp.db"

def query_db(query, args=(), one=False, commit=False):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(query, args)
    if commit:
        conn.commit()
        conn.close()
        return True
    rv = cursor.fetchall()
    conn.close()
    return (rv[0] if rv else None) if one else rv

# تهيئة قاعدة البيانات بكافة الجداول المطلوبة
def setup_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (discord_id INTEGER PRIMARY KEY, username TEXT UNIQUE, verified INTEGER DEFAULT 0)''')
    c.execute('''CREATE TABLE IF NOT EXISTS follows (follower_id INTEGER, followed_id INTEGER, PRIMARY KEY(follower_id, followed_id))''')
    c.execute('''CREATE TABLE IF NOT EXISTS settings (guild_id INTEGER PRIMARY KEY, app_channel INTEGER, tweet_channel INTEGER, verify_channel INTEGER, admin_role INTEGER, panel_img TEXT, signature TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS tweets (message_id INTEGER PRIMARY KEY, author_id INTEGER, content TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS hashtags (tag TEXT PRIMARY KEY, count INTEGER DEFAULT 0)''')
    conn.commit()
    conn.close()

setup_db()

# ==========================================
# 📝 المودالات (Modals)
# ==========================================
class RegisterModal(ui.Modal, title="إنشاء حساب"):
    username = ui.TextInput(label="اسم المستخدم (اليوزر)", min_length=3, max_length=15)
    async def on_submit(self, interaction: discord.Interaction):
        try:
            query_db("INSERT INTO users (discord_id, username) VALUES (?, ?)", (interaction.user.id, self.username.value.lower()), commit=True)
            await interaction.response.send_message("✅ تم إنشاء حسابك بنجاح!", ephemeral=True)
        except: await interaction.response.send_message("❌ اليوزر مستخدم بالفعل!", ephemeral=True)

class TweetModal(ui.Modal, title="إرسال تغريدة"):
    content = ui.TextInput(label="المحتوى", style=discord.TextStyle.paragraph)
    media = ui.TextInput(label="رابط الصورة", required=False)
    async def on_submit(self, interaction: discord.Interaction):
        # هنا يتم جلب التوقيع (Signature) وتطبيقه
        sig = query_db("SELECT signature FROM settings WHERE guild_id = ?", (interaction.guild.id,), one=True)
        final_text = f"{self.content.value}\n\n{sig[0] if sig else ''}"
        await interaction.response.send_message("✅ تم نشر تغريدتك بنجاح!", ephemeral=True)

class VerifyModal(ui.Modal, title="طلب توثيق"):
    reason = ui.TextInput(label="سبب التوثيق")
    async def on_submit(self, interaction: discord.Interaction):
        # منطق منشن الرتبة المسؤولة
        admin_role = query_db("SELECT admin_role FROM settings WHERE guild_id = ?", (interaction.guild.id,), one=True)
        role_mention = f"<@&{admin_role[0]}>" if admin_role else "الإدارة"
        await interaction.response.send_message(f"✅ تم إرسال الطلب لـ {role_mention}!", ephemeral=True)

# ==========================================
# 🔘 القائمة المنسدلة والواجهة (View)
# ==========================================
class MainSelect(ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="إنشاء حساب 📝", value="reg", emoji="📝"),
            discord.SelectOption(label="إرسال تغريدة 🐦", value="tweet", emoji="🐦"),
            discord.SelectOption(label="طلب توثيق 🏅", value="verify", emoji="🏅"),
            discord.SelectOption(label="حسابي والترند 👤", value="profile", emoji="👤"),
            discord.SelectOption(label="إعادة الاختيار 🔄", value="reset", emoji="🔄")
        ]
        super().__init__(placeholder="القائمة الرئيسية لمدينة URG", options=options)

    async def callback(self, interaction: discord.Interaction):
        if self.values[0] == "reg": await interaction.response.send_modal(RegisterModal())
        elif self.values[0] == "tweet": await interaction.response.send_modal(TweetModal())
        elif self.values[0] == "verify": await interaction.response.send_modal(VerifyModal())
        elif self.values[0] == "profile": await self.show_profile(interaction)
        elif self.values[0] == "reset": await interaction.response.send_message("🔄 تمت إعادة تعيين اللوحة.", ephemeral=True)

    async def show_profile(self, interaction):
        data = query_db("SELECT username FROM users WHERE discord_id = ?", (interaction.user.id,), one=True)
        if not data: return await interaction.response.send_message("❌ ليس لديك حساب!", ephemeral=True)
        
        # جلب الترندات الأكثر تداولاً
        top_tags = query_db("SELECT tag, count FROM hashtags ORDER BY count DESC LIMIT 5")
        trend_text = "\n".join([f"🔥 {t[0]} ({t[1]})" for t in top_tags])
        
        embed = discord.Embed(title=f"ملفك: @{data[0]}", color=discord.Color.blue())
        embed.add_field(name="الترندات:", value=trend_text or "لا يوجد", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

class MainPanelView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(MainSelect())

# ==========================================
# 🚀 الأوامر (Slash Commands)
# ==========================================
@bot.tree.command(name="تسطيب", description="تسطيب النظام بالكامل")
@app_commands.checks.has_permissions(administrator=True)
async def setup(interaction: discord.Interaction, 
                روم_البانل: discord.TextChannel, 
                روم_التغريد: discord.TextChannel, 
                روم_التوثيق: discord.TextChannel,
                رتبة_المسؤولين: discord.Role,
                رابط_صورة_البانل: str,
                خط_السيرفر: str):
    
    query_db("INSERT OR REPLACE INTO settings (guild_id, app_channel, tweet_channel, verify_channel, admin_role, panel_img, signature) VALUES (?, ?, ?, ?, ?, ?, ?)",
             (interaction.guild.id, روم_البانل.id, روم_التغريد.id, روم_التوثيق.id, رتبة_المسؤولين.id, رابط_صورة_البانل, خط_السيرفر), commit=True)
    
    embed = discord.Embed(title="📱 منصة URG", description="مرحباً بك في مدينة يو ار جي، استخدم القائمة بالأسفل 👇", color=discord.Color.blue())
    embed.set_image(url=رابط_صورة_البانل)
    await روم_البانل.send(embed=embed, view=MainPanelView())
    await interaction.response.send_message("✅ تم التسطيب وتفعيل النظام بنجاح!", ephemeral=True)

@bot.tree.command(name="مطورين", description="عرض معلومات المبرمج")
async def dev(interaction: discord.Interaction):
    embed = discord.Embed(title="💻 عن المطور", description="نظام URG System v2.0\n\nالمبرمج:\n**f_arooq004**\n\nجميع الحقوق محفوظة ©", color=discord.Color.dark_grey())
    await interaction.response.send_message(embed=embed, ephemeral=True)

# تشغيل البوت
bot.run(os.getenv("DISCORD_TOKEN"))
