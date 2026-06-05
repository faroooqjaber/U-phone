import discord
from discord.ext import commands
from discord import app_commands, ui
import sqlite3
import os
import re
import random
from datetime import datetime

# ==============================================================================
# 1. إعدادات البوت والنيات (Intents)
# ==============================================================================
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents)
DB_PATH = "twitter_rp.db"

# ==============================================================================
# 2. إدارة قاعدة البيانات (Database Management)
# ==============================================================================
def query_db(query, args=(), one=False, commit=False):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute(query, args)
        if commit:
            conn.commit()
        res = cursor.fetchone() if one else cursor.fetchall()
        return res
    except Exception as e:
        print(f"[DB Error] {e}")
        return None
    finally:
        conn.close()

def setup_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (discord_id INTEGER PRIMARY KEY, username TEXT UNIQUE, verified INTEGER DEFAULT 0, account_type TEXT DEFAULT 'شخصي', notifications INTEGER DEFAULT 1, fame_points INTEGER DEFAULT 0)''')
    c.execute('''CREATE TABLE IF NOT EXISTS follows (follower_id INTEGER, followed_id INTEGER, PRIMARY KEY(follower_id, followed_id))''')
    c.execute('''CREATE TABLE IF NOT EXISTS settings (guild_id INTEGER PRIMARY KEY, app_channel INTEGER, tweet_channel INTEGER, market_channel INTEGER, gram_channel INTEGER, verify_channel INTEGER, admin_role INTEGER, embed_color TEXT DEFAULT '00acee', panel_img TEXT, apps_img TEXT, signature TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS tweets (message_id INTEGER PRIMARY KEY, author_id INTEGER, comments_open INTEGER DEFAULT 1)''')
    c.execute('''CREATE TABLE IF NOT EXISTS tweet_likes (message_id INTEGER, user_id INTEGER, PRIMARY KEY(message_id, user_id))''')
    c.execute('''CREATE TABLE IF NOT EXISTS tweet_rts (message_id INTEGER, user_id INTEGER, PRIMARY KEY(message_id, user_id))''')
    c.execute('''CREATE TABLE IF NOT EXISTS hashtags (tag TEXT PRIMARY KEY, count INTEGER DEFAULT 0)''')
    try: c.execute("ALTER TABLE settings ADD COLUMN market_channel INTEGER")
    except: pass
    try: c.execute("ALTER TABLE settings ADD COLUMN gram_channel INTEGER")
    except: pass
    try: c.execute("ALTER TABLE settings ADD COLUMN apps_img TEXT")
    except: pass
    conn.commit()
    conn.close()

setup_db()

# ==============================================================================
# 3. دوال المساعدة والإشعارات
# ==============================================================================
async def send_notification(target_id, text, embed_title="🔔 إشعار جديد - U-Phone", color=discord.Color.blue(), view=None):
    status = query_db("SELECT notifications FROM users WHERE discord_id = ?", (target_id,), one=True)
    if status and status[0] == 0: return 
    try:
        user = bot.get_user(int(target_id)) or await bot.fetch_user(int(target_id))
        if user:
            embed = discord.Embed(title=embed_title, description=text, color=color)
            await user.send(embed=embed, view=view)
    except: pass

def secure_text(text):
    urls = re.findall(r'https?://\S+', text)
    for url in urls:
        if "discord" not in url and not any(ext in url.lower() for ext in ['.png', '.jpg', '.jpeg', '.gif', '.webp']):
            return False
    return True

# ==============================================================================
# 4. النماذج (Modals) لتطبيق تويتر وإدارة الحسابات
# ==============================================================================
class RegisterModal(ui.Modal, title="📝 إنشاء حساب U-Phone"):
    username = ui.TextInput(label="اسم المستخدم (اليوزر بدون @)", placeholder="مثال: omar_rashidi", min_length=3, max_length=15)
    async def on_submit(self, interaction: discord.Interaction):
        user_input = self.username.value.strip().lower()
        if not re.match(r"^[a-zA-Z0-9_]+$", user_input):
            return await interaction.response.send_message("❌ خطأ: اليوزر يجب أن يحتوي على أحرف وأرقام فقط!", ephemeral=True)
        try:
            query_db("INSERT INTO users (discord_id, username) VALUES (?, ?)", (interaction.user.id, user_input), commit=True)
            await interaction.response.send_message(f"🎉 تم إنشاء حسابك بنجاح بـ يوزر: `@{user_input}`", ephemeral=True)
        except sqlite3.IntegrityError:
            await interaction.response.send_message("❌ خطأ: اسم المستخدم مستخدم بالفعل!", ephemeral=True)

class TweetModal(ui.Modal, title="🐦 نشر تغريدة جديدة"):
    content = ui.TextInput(label="محتوى التغريدة", style=discord.TextStyle.paragraph, max_length=280)
    media = ui.TextInput(label="رابط صورة (اختياري)", required=False)
    comments = ui.TextInput(label="هل تريد فتح التعليقات؟ (نعم / لا)", default="نعم", max_length=3)
    
    async def on_submit(self, interaction: discord.Interaction):
        user_data = query_db("SELECT username, verified, account_type FROM users WHERE discord_id = ?", (interaction.user.id,), one=True)
        if not user_data: return await interaction.response.send_message("❌ ليس لديك حساب!", ephemeral=True)
        if self.comments.value.strip() not in ["نعم", "لا"]: return await interaction.response.send_message("❌ اكتب 'نعم' أو 'لا' فقط!", ephemeral=True)
        text = self.content.value
        media_url = self.media.value.strip() if self.media.value else None
        if not secure_text(text) or (media_url and not secure_text(media_url)): return await interaction.response.send_message("❌ روابط خارجية محظورة!", ephemeral=True)
            
        setting = query_db("SELECT tweet_channel FROM settings WHERE guild_id = ?", (interaction.guild.id,), one=True)
        if not setting or not setting[0]: return await interaction.response.send_message("❌ روم التغريدات غير مفعل.", ephemeral=True)
        tweet_chan = interaction.guild.get_channel(setting[0])
        
        tags = re.findall(r'#\w+', text)
        for tag in tags: query_db("INSERT INTO hashtags (tag, count) VALUES (?, 1) ON CONFLICT(tag) DO UPDATE SET count = count + 1", (tag,), commit=True)
            
        badge = " 🏛️" if user_data[1] == 1 and user_data[2] == "حساب حكومي" else " 💼" if user_data[1] == 1 and user_data[2] == "حساب تجاري" else " ☑️" if user_data[1] == 1 else ""
        embed = discord.Embed(description=text, color=discord.Color.blue(), timestamp=datetime.utcnow())
        embed.set_author(name=f"{interaction.user.display_name} (@{user_data[0]}){badge}", icon_url=interaction.user.display_avatar.url)
        if media_url: embed.set_image(url=media_url)
        embed.set_footer(text="U-Phone | Twitter")
        embed.add_field(name="📊 إحصائيات التفاعل:", value="❤️ الإعجابات: **0** | 🔁 إعادة النشر: **0**", inline=False)
        
        msg = await tweet_chan.send(embed=embed)
        view = ui.View(timeout=None)
        view.add_item(ui.Button(label="أعجبني ❤️", style=discord.ButtonStyle.secondary, custom_id=f"tw_like_{msg.id}"))
        view.add_item(ui.Button(label="إعادة نشر 🔁", style=discord.ButtonStyle.secondary, custom_id=f"tw_rt_{msg.id}"))
        view.add_item(ui.Button(label="رد 💬", style=discord.ButtonStyle.secondary, custom_id=f"tw_reply_{msg.id}"))
        await msg.edit(view=view)
        
        query_db("INSERT INTO tweets (message_id, author_id, comments_open) VALUES (?, ?, ?)", (msg.id, interaction.user.id, 1 if self.comments.value == "نعم" else 0), commit=True)
        
        mentions = re.findall(r'@([a-zA-Z0-9_]+)', text)
        for mentioned_user in list(set(mentions)):
            if mentioned_user.lower() != user_data[0].lower():
                target_res = query_db("SELECT discord_id FROM users WHERE username = ?", (mentioned_user.lower(),), one=True)
                if target_res: await send_notification(target_res[0], f"👤 أشار إليك `@{user_data[0]}`!\n🔗 [إضغط هنا]({msg.jump_url})")

        await interaction.response.send_message("✅ تم النشر!", ephemeral=True)

class ReplyModal(ui.Modal, title="💬 الرد على التغريدة"):
    reply_text = ui.TextInput(label="اكتب ردك هنا", style=discord.TextStyle.paragraph, max_length=250)
    def __init__(self, message: discord.Message):
        super().__init__()
        self.message = message
    async def on_submit(self, interaction: discord.Interaction):
        user_data = query_db("SELECT username FROM users WHERE discord_id = ?", (interaction.user.id,), one=True)
        if not user_data: return await interaction.response.send_message("❌ حساب غير مسجل!", ephemeral=True)
        thread = self.message.thread or await self.message.create_thread(name=f"ردود المغردين", auto_archive_duration=60)
        rembed = discord.Embed(description=self.reply_text.value, color=discord.Color.light_grey(), timestamp=datetime.utcnow())
        rembed.set_author(name=f"رد من @{user_data[0]}", icon_url=interaction.user.display_avatar.url)
        await thread.send(embed=rembed)
        await interaction.response.send_message("✅ تم إضافة ردك!", ephemeral=True)

class SearchProfileModal(ui.Modal, title="🔍 البحث عن حساب"):
    username = ui.TextInput(label="يوزر الحساب (بدون @)")
    async def on_submit(self, interaction: discord.Interaction):
        target = self.username.value.strip().lower()
        res = query_db("SELECT discord_id, verified, account_type FROM users WHERE username = ?", (target,), one=True)
        if not res: return await interaction.response.send_message("❌ يوزر غير موجود.", ephemeral=True)
        followers = len(query_db("SELECT follower_id FROM follows WHERE followed_id = ?", (res[0],)))
        following = len(query_db("SELECT followed_id FROM follows WHERE follower_id = ?", (res[0],)))
        acc_str = f"موثق ({res[2]})" if res[1] == 1 else "شخصي"
        embed = discord.Embed(title=f"👤 حساب: @{target}", color=discord.Color.blue())
        embed.add_field(name="الفئة:", value=acc_str, inline=False)
        embed.add_field(name="يتابعه:", value=str(followers), inline=True)
        embed.add_field(name="يتابع:", value=str(following), inline=True)
        view = ui.View(timeout=None).add_item(ui.Button(label="متابعة / إلغاء ➕", style=discord.ButtonStyle.primary, custom_id=f"tw_follow_{res[0]}"))
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

# ==============================================================================
# 5. النماذج (Modals) للتطبيقات الجديدة (Shadow, Chat, Market, Gram)
# ==============================================================================
class ShadowMailModal(ui.Modal, title="🥷 رسالة مجهولة"):
    target = ui.TextInput(label="يوزر المستهدف")
    content = ui.TextInput(label="الرسالة", style=discord.TextStyle.paragraph)
    async def on_submit(self, interaction: discord.Interaction):
        tid = query_db("SELECT discord_id FROM users WHERE username = ?", (self.target.value.strip().lower(),), one=True)
        if not tid: return await interaction.response.send_message("❌ غير موجود!", ephemeral=True)
        embed = discord.Embed(title="⚠️ رسالة مشفرة مجهولة", description=self.content.value, color=discord.Color.dark_theme())
        try:
            user = bot.get_user(tid[0]) or await bot.fetch_user(tid[0])
            await user.send(embed=embed)
            await interaction.response.send_message("🥷 تم الإرسال للمستهدف.", ephemeral=True)
        except: await interaction.response.send_message("❌ المستهدف يغلق الخاص.", ephemeral=True)

class ChatAppModal(ui.Modal, title="💬 شات أب"):
    target = ui.TextInput(label="يوزر المستهدف")
    content = ui.TextInput(label="الرسالة", style=discord.TextStyle.paragraph)
    async def on_submit(self, interaction: discord.Interaction):
        sender = query_db("SELECT username FROM users WHERE discord_id = ?", (interaction.user.id,), one=True)
        if not sender: return await interaction.response.send_message("❌ حسابك غير مسجل!", ephemeral=True)
        tid = query_db("SELECT discord_id FROM users WHERE username = ?", (self.target.value.strip().lower(),), one=True)
        if not tid: return await interaction.response.send_message("❌ غير موجود!", ephemeral=True)
        embed = discord.Embed(title="💬 رسالة جديدة", description=f"**من:** `@{sender[0]}`\n\n{self.content.value}", color=discord.Color.green())
        view = ui.View(timeout=None).add_item(ui.Button(label="الرد ↩️", style=discord.ButtonStyle.success, custom_id=f"ch_reply_{interaction.user.id}_{sender[0]}"))
        try:
            user = bot.get_user(tid[0]) or await bot.fetch_user(tid[0])
            await user.send(embed=embed, view=view)
            await interaction.response.send_message("✅ تم الإرسال!", ephemeral=True)
        except: await interaction.response.send_message("❌ يغلق الخاص.", ephemeral=True)

class ChatQuickReplyModal(ui.Modal, title="↩️ الرد السريع"):
    content = ui.TextInput(label="الرسالة", style=discord.TextStyle.paragraph)
    def __init__(self, target_id, target_name):
        super().__init__()
        self.target_id, self.target_name = int(target_id), target_name
    async def on_submit(self, interaction: discord.Interaction):
        sender = query_db("SELECT username FROM users WHERE discord_id = ?", (interaction.user.id,), one=True)
        embed = discord.Embed(title="💬 رد جديد", description=f"**من:** `@{sender[0]}`\n\n{self.content.value}", color=discord.Color.green())
        view = ui.View(timeout=None).add_item(ui.Button(label="الرد ↩️", style=discord.ButtonStyle.success, custom_id=f"ch_reply_{interaction.user.id}_{sender[0]}"))
        try:
            user = bot.get_user(self.target_id) or await bot.fetch_user(self.target_id)
            await user.send(embed=embed, view=view)
            await interaction.response.send_message("✅ تم الرد!", ephemeral=True)
        except: await interaction.response.send_message("❌ مغلق.", ephemeral=True)

class MarketModal(ui.Modal):
    title_inp = ui.TextInput(label="العنوان")
    desc = ui.TextInput(label="التفاصيل", style=discord.TextStyle.paragraph)
    img = ui.TextInput(label="صورة (اختياري)", required=False)
    def __init__(self, is_dark: bool):
        super().__init__(title="سوق الإنترنت المظلم ☠️" if is_dark else "سوق المدينة 🚗")
        self.is_dark = is_dark
    async def on_submit(self, interaction: discord.Interaction):
        user = query_db("SELECT username FROM users WHERE discord_id = ?", (interaction.user.id,), one=True)
        if not user: return await interaction.response.send_message("❌ حسابك غير مسجل!", ephemeral=True)
        settings = query_db("SELECT market_channel FROM settings WHERE guild_id = ?", (interaction.guild.id,), one=True)
        if not settings or not settings[0]: return await interaction.response.send_message("❌ روم السوق غير مفعل.", ephemeral=True)
        m_chan = interaction.guild.get_channel(settings[0])
        embed = discord.Embed(title=self.title_inp.value, description=self.desc.value, color=discord.Color.dark_theme() if self.is_dark else discord.Color.gold())
        if self.img.value: embed.set_image(url=self.img.value)
        view = ui.View(timeout=None)
        if self.is_dark:
            embed.set_author(name="🥷 تاجر مجهول")
            view.add_item(ui.Button(label="شراء سري 💼", style=discord.ButtonStyle.danger, custom_id=f"mk_buy_{interaction.user.id}"))
        else:
            embed.set_author(name=f"إعلان: @{user[0]}")
            view.add_item(ui.Button(label="تواصل 📞", style=discord.ButtonStyle.primary, custom_id=f"mk_contact_{interaction.user.id}_{user[0]}"))
        await m_chan.send(embed=embed, view=view)
        await interaction.response.send_message("✅ نُشر إعلانك!", ephemeral=True)

class GramModal(ui.Modal, title="📸 يو جرام - يوميات"):
    content = ui.TextInput(label="التعليق", max_length=150)
    img = ui.TextInput(label="رابط الصورة (إلزامي)")
    async def on_submit(self, interaction: discord.Interaction):
        user = query_db("SELECT username FROM users WHERE discord_id = ?", (interaction.user.id,), one=True)
        if not user: return await interaction.response.send_message("❌ غير مسجل!", ephemeral=True)
        settings = query_db("SELECT gram_channel FROM settings WHERE guild_id = ?", (interaction.guild.id,), one=True)
        if not settings or not settings[0]: return await interaction.response.send_message("❌ روم اليوميات غير مفعل.", ephemeral=True)
        g_chan = interaction.guild.get_channel(settings[0])
        embed = discord.Embed(description=self.content.value, color=discord.Color.purple())
        embed.set_author(name=f"📸 ستوري: @{user[0]}").set_image(url=self.img.value)
        view = ui.View(timeout=None).add_item(ui.Button(label="دعم 👍", style=discord.ButtonStyle.secondary, custom_id="gr_like"))
        await g_chan.send(embed=embed, view=view)
        await interaction.response.send_message("✅ تم نشر الستوري!", ephemeral=True)

class ApplyMembershipModal(ui.Modal, title="📝 تقديم عضوية"):
    char_name = ui.TextInput(label="اسم الشخصية IC")
    char_exp = ui.TextInput(label="التفاصيل", style=discord.TextStyle.paragraph)
    async def on_submit(self, interaction: discord.Interaction):
        settings = query_db("SELECT verify_channel FROM settings WHERE guild_id = ?", (interaction.guild.id,), one=True)
        if not settings or not settings[0]: return await interaction.response.send_message("❌ روم التقديم غير مفعل.", ephemeral=True)
        v_chan = interaction.guild.get_channel(settings[0])
        embed = discord.Embed(title="📥 طلب عضوية", color=discord.Color.teal())
        embed.add_field(name="الشخصية:", value=self.char_name.value, inline=False)
        embed.add_field(name="التفاصيل:", value=self.char_exp.value, inline=False)
        view = ui.View(timeout=None)
        view.add_item(ui.Button(label="قبول ✅", style=discord.ButtonStyle.success, custom_id=f"vf_accept_{interaction.user.id}"))
        view.add_item(ui.Button(label="رفض ❌", style=discord.ButtonStyle.danger, custom_id=f"vf_reject_{interaction.user.id}"))
        await v_chan.send(embed=embed, view=view)
        await interaction.response.send_message("✅ تم إرسال الطلب للإدارة!", ephemeral=True)

class GuessNumModal(ui.Modal, title="🔢 تخمين الرقم"):
    guess = ui.TextInput(label="رقم من 1 لـ 50")
    async def on_submit(self, interaction: discord.Interaction):
        secret = random.randint(1, 50)
        try: v = int(self.guess.value)
        except: return await interaction.response.send_message("❌ أرقام فقط!", ephemeral=True)
        await interaction.response.send_message("🎉 مبروووك!" if v == secret else f"🤖 خطأ، الرقم {secret}", ephemeral=True)

# ==============================================================================
# 6. واجهة الهاتف (بدون تعارض الأزرار) - نظام Callback الجديد
# ==============================================================================
class SubAppSelect(ui.Select):
    def __init__(self, app_code):
        options = []
        if app_code == "tw": options = [discord.SelectOption(label="كتابة تغريدة", value="tw_write", emoji="📝"), discord.SelectOption(label="حسابي والترند", value="tw_prof", emoji="👤"), discord.SelectOption(label="بحث عن حساب", value="tw_srch", emoji="🔍"), discord.SelectOption(label="الإشعارات", value="tw_notif", emoji="⚙️")]
        elif app_code == "sh": options = [discord.SelectOption(label="رسالة مجهولة", value="sh_send", emoji="✉️")]
        elif app_code == "ch": options = [discord.SelectOption(label="محادثة جديدة", value="ch_new", emoji="💬")]
        elif app_code == "mk": options = [discord.SelectOption(label="إعلان قانوني", value="mk_legal", emoji="🚗"), discord.SelectOption(label="إعلان مظلم", value="mk_dark", emoji="☠️")]
        elif app_code == "gr": options = [discord.SelectOption(label="نشر ستوري", value="gr_post", emoji="📸")]
        elif app_code == "pl": options = [discord.SelectOption(label="تخمين الرقم", value="pl_gn", emoji="🔢")]
        elif app_code == "id": options = [discord.SelectOption(label="إنشاء حساب", value="id_reg", emoji="📝"), discord.SelectOption(label="تقديم عضوية", value="id_ver", emoji="🏅")]
        
        options.extend([discord.SelectOption(label="عودة للشاشة", value="back_home", emoji="🔙"), discord.SelectOption(label="إغلاق الهاتف", value="close_phone", emoji="❌")])
        super().__init__(placeholder="اختر الإجراء...", options=options)

    async def callback(self, interaction: discord.Interaction):
        val = self.values[0]
        if val == "close_phone": return await interaction.message.delete()
        if val == "back_home":
            img = query_db("SELECT apps_img FROM settings WHERE guild_id = ?", (interaction.guild.id,), one=True)
            embed = discord.Embed(title="📱 شاشة التطبيقات", color=discord.Color.from_rgb(30,30,30))
            if img and img[0]: embed.set_image(url=img[0])
            view = ui.View(timeout=None).add_item(MainAppSelect())
            return await interaction.response.edit_message(embed=embed, view=view)

        if val == "tw_write": await interaction.response.send_modal(TweetModal())
        elif val == "tw_srch": await interaction.response.send_modal(SearchProfileModal())
        elif val == "tw_prof":
            data = query_db("SELECT username, verified, account_type FROM users WHERE discord_id = ?", (interaction.user.id,), one=True)
            if not data: return await interaction.response.send_message("❌ لا يوجد حساب!", ephemeral=True)
            flws = len(query_db("SELECT follower_id FROM follows WHERE followed_id = ?", (interaction.user.id,)))
            em = discord.Embed(title=f"👤 حسابي: @{data[0]}", color=discord.Color.blue())
            em.add_field(name="المتابعون:", value=str(flws), inline=True).add_field(name="الفئة:", value=data[2], inline=True)
            await interaction.response.send_message(embed=em, ephemeral=True)
        elif val == "tw_notif":
            sts = query_db("SELECT notifications FROM users WHERE discord_id = ?", (interaction.user.id,), one=True)
            new_sts = 0 if sts and sts[0] == 1 else 1
            query_db("UPDATE users SET notifications = ? WHERE discord_id = ?", (new_sts, interaction.user.id), commit=True)
            await interaction.response.send_message(f"⚙️ الإشعارات: {'مفعلة' if new_sts else 'معطلة'}", ephemeral=True)
        elif val == "sh_send": await interaction.response.send_modal(ShadowMailModal())
        elif val == "ch_new": await interaction.response.send_modal(ChatAppModal())
        elif val == "mk_legal": await interaction.response.send_modal(MarketModal(False))
        elif val == "mk_dark": await interaction.response.send_modal(MarketModal(True))
        elif val == "gr_post": await interaction.response.send_modal(GramModal())
        elif val == "id_reg": await interaction.response.send_modal(RegisterModal())
        elif val == "id_ver": await interaction.response.send_modal(ApplyMembershipModal())
        elif val == "pl_gn": await interaction.response.send_modal(GuessNumModal())

class MainAppSelect(ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="تويتر المدينة", value="app_tw", emoji="🐦"),
            discord.SelectOption(label="شات أب", value="app_ch", emoji="💬"),
            discord.SelectOption(label="رسائل مجهولة", value="app_sh", emoji="🥷"),
            discord.SelectOption(label="سوق المدينة", value="app_mk", emoji="🛒"),
            discord.SelectOption(label="يو غرام (يوميات)", value="app_gr", emoji="📸"),
            discord.SelectOption(label="U-Play ألعاب", value="app_pl", emoji="🎮"),
            discord.SelectOption(label="الهوية والتقديم", value="app_id", emoji="🛂"),
            discord.SelectOption(label="إغلاق الهاتف", value="close_phone", emoji="❌")
        ]
        super().__init__(placeholder="📱 اضغط هنا لفتح التطبيقات...", options=options)

    async def callback(self, interaction: discord.Interaction):
        val = self.values[0]
        if val == "close_phone": return await interaction.message.delete()
        app_code = val.split('_')[1]
        view = ui.View(timeout=None).add_item(SubAppSelect(app_code))
        embed = discord.Embed(title=f"📱 تطبيق {app_code.upper()}", description="اختر الإجراء من القائمة:", color=discord.Color.dark_grey())
        await interaction.response.edit_message(embed=embed, view=view)

class StartPhoneView(ui.View):
    def __init__(self): super().__init__(timeout=None)
    @ui.button(label="تشغيل الهاتف 📱", style=discord.ButtonStyle.primary, custom_id="start_os_btn")
    async def boot(self, interaction: discord.Interaction, button: ui.Button):
        img = query_db("SELECT apps_img FROM settings WHERE guild_id = ?", (interaction.guild.id,), one=True)
        embed = discord.Embed(title="📱 شاشة التطبيقات الذكية", color=discord.Color.from_rgb(30,30,30))
        if img and img[0]: embed.set_image(url=img[0])
        view = ui.View(timeout=None).add_item(MainAppSelect())
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

# ==============================================================================
# 7. معالج الأزرار الثابتة (لايكات تويتر والأسواق) - معزول لتجنب الأخطاء
# ==============================================================================
class DynamicButtonHandler(commands.Cog):
    def __init__(self, bot): self.bot = bot
    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        if interaction.type != discord.InteractionType.component: return
        custom_id = interaction.data.get('custom_id', '')
        if not custom_id: return

        if custom_id.startswith('tw_like_'):
            msg_id = int(custom_id.split('_')[2])
            liked = query_db("SELECT 1 FROM tweet_likes WHERE message_id = ? AND user_id = ?", (msg_id, interaction.user.id), one=True)
            if liked: query_db("DELETE FROM tweet_likes WHERE message_id = ? AND user_id = ?", (msg_id, interaction.user.id), commit=True)
            else: query_db("INSERT INTO tweet_likes (message_id, user_id) VALUES (?, ?)", (msg_id, interaction.user.id), commit=True)
            likes = query_db("SELECT COUNT(*) FROM tweet_likes WHERE message_id = ?", (msg_id,), one=True)[0]
            rts = query_db("SELECT COUNT(*) FROM tweet_rts WHERE message_id = ?", (msg_id,), one=True)[0]
            em = interaction.message.embeds[0]
            em.set_field_at(0, name="📊 التفاعل:", value=f"❤️ الإعجابات: **{likes}** | 🔁 إعادة النشر: **{rts}**", inline=False)
            await interaction.response.edit_message(embed=em)

        elif custom_id.startswith('tw_rt_'):
            msg_id = int(custom_id.split('_')[2])
            rted = query_db("SELECT 1 FROM tweet_rts WHERE message_id = ? AND user_id = ?", (msg_id, interaction.user.id), one=True)
            if rted: query_db("DELETE FROM tweet_rts WHERE message_id = ? AND user_id = ?", (msg_id, interaction.user.id), commit=True)
            else: query_db("INSERT INTO tweet_rts (message_id, user_id) VALUES (?, ?)", (msg_id, interaction.user.id), commit=True)
            likes = query_db("SELECT COUNT(*) FROM tweet_likes WHERE message_id = ?", (msg_id,), one=True)[0]
            rts = query_db("SELECT COUNT(*) FROM tweet_rts WHERE message_id = ?", (msg_id,), one=True)[0]
            em = interaction.message.embeds[0]
            em.set_field_at(0, name="📊 التفاعل:", value=f"❤️ الإعجابات: **{likes}** | 🔁 إعادة النشر: **{rts}**", inline=False)
            await interaction.response.edit_message(embed=em)

        elif custom_id.startswith('tw_reply_'):
            msg_id = int(custom_id.split('_')[2])
            st = query_db("SELECT comments_open FROM tweets WHERE message_id = ?", (msg_id,), one=True)
            if st and st[0] == 0: return await interaction.response.send_message("❌ التعليقات مغلقة!", ephemeral=True)
            await interaction.response.send_modal(ReplyModal(interaction.message))

        elif custom_id.startswith('tw_follow_'):
            target_id = int(custom_id.split('_')[2])
            if interaction.user.id == target_id: return await interaction.response.send_message("❌ مستحيل تتابع نفسك!", ephemeral=True)
            is_f = query_db("SELECT 1 FROM follows WHERE follower_id = ? AND followed_id = ?", (interaction.user.id, target_id), one=True)
            if is_f:
                query_db("DELETE FROM follows WHERE follower_id = ? AND followed_id = ?", (interaction.user.id, target_id), commit=True)
                await interaction.response.send_message("❌ تم الإلغاء.", ephemeral=True)
            else:
                query_db("INSERT INTO follows (follower_id, followed_id) VALUES (?, ?)", (interaction.user.id, target_id), commit=True)
                await interaction.response.send_message("✅ تمت المتابعة!", ephemeral=True)

        elif custom_id.startswith('ch_reply_'):
            p = custom_id.split('_')
            await interaction.response.send_modal(ChatQuickReplyModal(p[2], p[3]))
            
        elif custom_id.startswith('mk_buy_'):
            oid = int(custom_id.split('_')[2])
            b = query_db("SELECT username FROM users WHERE discord_id = ?", (interaction.user.id,), one=True)
            view = ui.View(timeout=None).add_item(ui.Button(label="تواصل", style=discord.ButtonStyle.success, custom_id=f"ch_reply_{interaction.user.id}_{b[0] if b else 'مجهول'}"))
            await send_notification(oid, f"💼 المشتري `@{b[0] if b else 'مجهول'}` مهتم بسلعتك بالديب ويب!", color=discord.Color.dark_red(), view=view)
            await interaction.response.send_message("✅ أرسلنا طلبك للبائع.", ephemeral=True)
            
        elif custom_id.startswith('mk_contact_'):
            p = custom_id.split('_')
            await interaction.response.send_modal(ChatQuickReplyModal(p[2], p[3]))
            
        elif custom_id == "gr_like":
            await interaction.response.send_message("❤️ إرسال تفاعل!", ephemeral=True)

        elif custom_id.startswith('vf_accept_') or custom_id.startswith('vf_reject_'):
            d = query_db("SELECT admin_role FROM settings WHERE guild_id = ?", (interaction.guild.id,), one=True)
            r = interaction.guild.get_role(d[0]) if d else None
            if not r or r not in interaction.user.roles: return await interaction.response.send_message("❌ ليست لديك صلاحية!", ephemeral=True)
            tid = int(custom_id.split('_')[2])
            act = "قبول ✅" if "accept" in custom_id else "رفض ❌"
            em = interaction.message.embeds[0]
            em.title = f"تم {act} الطلب"
            em.color = discord.Color.green() if "accept" in custom_id else discord.Color.red()
            await interaction.response.edit_message(embed=em, view=None)

# ==============================================================================
# 8. الأوامر والتسطيب
# ==============================================================================
@bot.tree.command(name="تسطيب_الجوال", description="إعداد وتهيئة منظومة الجوال بالكامل")
@app_commands.checks.has_permissions(administrator=True)
async def setup_cmd(interaction: discord.Interaction, 
                    روم_الجوال: discord.TextChannel, روم_التغريدات: discord.TextChannel,
                    روم_السوق: discord.TextChannel, روم_اليوميات: discord.TextChannel,
                    روم_التقديمات: discord.TextChannel, رتبة_المسؤولين: discord.Role,
                    توقيع_الخط: str, صورة_الغلاف: str, صورة_الشاشة: str):
    await interaction.response.defer(ephemeral=True)
    query_db('''INSERT OR REPLACE INTO settings (guild_id, app_channel, tweet_channel, market_channel, gram_channel, verify_channel, admin_role, signature, panel_img, apps_img) VALUES (?,?,?,?,?,?,?,?,?,?)''',
             (interaction.guild.id, روم_الجوال.id, روم_التغريدات.id, روم_السوق.id, روم_اليوميات.id, روم_التقديمات.id, رتبة_المسؤولين.id, توقيع_الخط, صورة_الغلاف, صورة_الشاشة), commit=True)
    
    embed = discord.Embed(title="URG | OS Phone", description="اضغط الزر للتشغيل").set_image(url=صورة_الغلاف)
    await روم_الجوال.send(embed=embed, view=StartPhoneView())
    if توقيع_الخط: await روم_الجوال.send(توقيع_الخط)
    await interaction.followup.send("✅ تم التسطيب بالكامل بنجاح!", ephemeral=True)

@bot.event
async def on_ready():
    bot.add_view(StartPhoneView())
    await bot.add_cog(DynamicButtonHandler(bot))
    await bot.tree.sync()
    print("=========================================")
    print(f"✅ URG OS IS ONLINE! Logged in as {bot.user}")
    print("=========================================")

token = os.getenv("DISCORD_TOKEN")
if token: bot.run(token)
else: print("❌ لم يتم العثور على التوكن!")
