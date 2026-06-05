import discord
from discord.ext import commands
from discord import app_commands, ui
import sqlite3
import os
import re
import random
from datetime import datetime

# ==========================================
# ⚙️ إعدادات البوت والصلاحيات الأساسية
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

# تحديث قاعدة البيانات لدعم الرومات الجديدة
def setup_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (discord_id INTEGER PRIMARY KEY, username TEXT UNIQUE, verified INTEGER DEFAULT 0, account_type TEXT DEFAULT 'شخصي', notifications INTEGER DEFAULT 1)''')
    c.execute('''CREATE TABLE IF NOT EXISTS follows (follower_id INTEGER, followed_id INTEGER, PRIMARY KEY(follower_id, followed_id))''')
    c.execute('''CREATE TABLE IF NOT EXISTS settings (guild_id INTEGER PRIMARY KEY, app_channel INTEGER, tweet_channel INTEGER, market_channel INTEGER, gram_channel INTEGER, verify_channel INTEGER, admin_channel INTEGER, embed_color TEXT, admin_role INTEGER, panel_img TEXT, apps_img TEXT, signature TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS tweets (message_id INTEGER PRIMARY KEY, author_id INTEGER, comments_open INTEGER DEFAULT 1)''')
    c.execute('''CREATE TABLE IF NOT EXISTS tweet_likes (message_id INTEGER, user_id INTEGER, PRIMARY KEY(message_id, user_id))''')
    c.execute('''CREATE TABLE IF NOT EXISTS tweet_rts (message_id INTEGER, user_id INTEGER, PRIMARY KEY(message_id, user_id))''')
    c.execute('''CREATE TABLE IF NOT EXISTS hashtags (tag TEXT PRIMARY KEY, count INTEGER DEFAULT 0)''')
    
    # محاولة إضافة الأعمدة الجديدة إن لم تكن موجودة
    try: c.execute("ALTER TABLE settings ADD COLUMN market_channel INTEGER")
    except sqlite3.OperationalError: pass
    try: c.execute("ALTER TABLE settings ADD COLUMN gram_channel INTEGER")
    except sqlite3.OperationalError: pass
    try: c.execute("ALTER TABLE settings ADD COLUMN apps_img TEXT")
    except sqlite3.OperationalError: pass
    
    conn.commit()
    conn.close()

setup_db()

# دالة مساعدة للحصول على يوزر الشخص من اسمه
def get_user_id_by_username(username):
    res = query_db("SELECT discord_id FROM users WHERE username = ?", (username.lower(),), one=True)
    return res[0] if res else None

async def send_notification(target_id, text, embed_title="🔔 إشعار جديد - U app", color=discord.Color.blue(), view=None):
    status = query_db("SELECT notifications FROM users WHERE discord_id = ?", (target_id,), one=True)
    if status and status[0] == 0: return
    try:
        user = bot.get_user(target_id) or await bot.fetch_user(target_id)
        if user:
            embed = discord.Embed(title=embed_title, description=text, color=color)
            await user.send(embed=embed, view=view)
    except Exception:
        pass

def secure_text(text):
    urls = re.findall(r'https?://\S+', text)
    for url in urls:
        if "discord" not in url and not any(ext in url.lower() for ext in ['.png', '.jpg', '.jpeg', '.gif', '.webp']):
            return False
    return True

# ==========================================
# 🎛️ النوافذ المنبثقة (Modals) الأساسية للتطبيقات
# ==========================================

class RegisterModal(ui.Modal, title="إنشاء حساب U-Phone"):
    username = ui.TextInput(label="اسم المستخدم (بدون @)", min_length=3, max_length=15)
    async def on_submit(self, interaction: discord.Interaction):
        user_input = self.username.value.strip().lower()
        if not re.match(r"^[a-zA-Z0-9_]+$", user_input):
            return await interaction.response.send_message("❌ اليوزر يجب أن يحتوي على أحرف وأرقام فقط!", ephemeral=True)
        try:
            query_db("INSERT INTO users (discord_id, username) VALUES (?, ?)", (interaction.user.id, user_input), commit=True)
            await interaction.response.send_message(f"🎉 تم إنشاء حسابك بنجاح: `@{user_input}`", ephemeral=True)
        except sqlite3.IntegrityError:
            await interaction.response.send_message("❌ اليوزر مستخدم بالفعل!", ephemeral=True)

class TweetModal(ui.Modal, title="كتابة تغريدة 🐦"):
    content = ui.TextInput(label="محتوى التغريدة", style=discord.TextStyle.paragraph, max_length=280)
    media = ui.TextInput(label="رابط صورة (اختياري)", required=False)
    comments = ui.TextInput(label="فتح التعليقات؟ (نعم / لا)", min_length=2, max_length=3)
    
    async def on_submit(self, interaction: discord.Interaction):
        user_data = query_db("SELECT username, verified, account_type FROM users WHERE discord_id = ?", (interaction.user.id,), one=True)
        if not user_data: return await interaction.response.send_message("❌ سجل حسابك أولاً!", ephemeral=True)
        
        if self.comments.value.strip() not in ["نعم", "لا"]:
            return await interaction.response.send_message("❌ اكتب نعم أو لا فقط!", ephemeral=True)
            
        text = self.content.value
        media_url = self.media.value.strip() if self.media.value else None
        if not secure_text(text) or (media_url and not secure_text(media_url)):
            return await interaction.response.send_message("❌ تم حظر روابط خارجية!", ephemeral=True)
            
        settings = query_db("SELECT tweet_channel, embed_color, signature FROM settings WHERE guild_id = ?", (interaction.guild.id,), one=True)
        t_chan = interaction.guild.get_channel(settings[0])
        color = int(settings[1], 16)
        
        badge = " 🏛️" if user_data[2] == "حساب حكومي" else " 💼" if user_data[2] == "حساب تجاري" else " ☑️" if user_data[1] else ""
        embed = discord.Embed(description=text, color=color, timestamp=datetime.utcnow())
        embed.set_author(name=f"{interaction.user.display_name} (@{user_data[0]}){badge}", icon_url=interaction.user.display_avatar.url)
        if media_url: embed.set_image(url=media_url)
        embed.set_footer(text="U app | Twitter")
        embed.add_field(name="📊 إحصائيات:", value="❤️ الإعجابات: **0** | 🔁 إعادة النشر: **0**")
        
        msg = await t_chan.send(embed=embed)
        if settings[2]: await t_chan.send(content=settings[2])
        
        is_open = 1 if self.comments.value.strip() == "نعم" else 0
        await msg.edit(view=TweetActionView(msg.id))
        query_db("INSERT INTO tweets (message_id, author_id, comments_open) VALUES (?, ?, ?)", (msg.id, interaction.user.id, is_open), commit=True)
        
        # نظام المنشن
        mentions = re.findall(r'@([a-zA-Z0-9_]+)', text)
        for m in set(mentions):
            if m.lower() != user_data[0]:
                tid = get_user_id_by_username(m)
                if tid: await send_notification(tid, f"👤 قام `@{user_data[0]}` بذكرك في تغريدة!\n🔗 [انتقال للتغريدة]({msg.jump_url})")
                
        await interaction.response.send_message("✅ تم النشر!", ephemeral=True)

class ShadowMailModal(ui.Modal, title="رسالة مجهولة 🥷"):
    target = ui.TextInput(label="يوزر المستهدف (بدون @)")
    content = ui.TextInput(label="الرسالة", style=discord.TextStyle.paragraph)
    
    async def on_submit(self, interaction: discord.Interaction):
        tid = get_user_id_by_username(self.target.value.strip())
        if not tid: return await interaction.response.send_message("❌ اليوزر غير موجود!", ephemeral=True)
        
        embed = discord.Embed(title="⚠️ رسالة مشفرة من جهة مجهولة", description=self.content.value, color=discord.Color.darker_grey())
        await send_notification(tid, text="", embed_title="⚠️ رسالة مشفرة", color=discord.Color.darker_grey())
        
        target_user = bot.get_user(tid) or await bot.fetch_user(tid)
        await target_user.send(embed=embed)
        await interaction.response.send_message("🥷 تم تشفير وإرسال الرسالة.", ephemeral=True)

class ChatAppModal(ui.Modal, title="محادثة شات أب 💬"):
    target = ui.TextInput(label="يوزر المستهدف (بدون @)")
    content = ui.TextInput(label="الرسالة", style=discord.TextStyle.paragraph)
    
    async def on_submit(self, interaction: discord.Interaction):
        sender = query_db("SELECT username FROM users WHERE discord_id = ?", (interaction.user.id,), one=True)
        if not sender: return await interaction.response.send_message("❌ سجل حسابك أولاً!", ephemeral=True)
        
        tid = get_user_id_by_username(self.target.value.strip())
        if not tid: return await interaction.response.send_message("❌ اليوزر غير موجود!", ephemeral=True)
        
        target_user = bot.get_user(tid) or await bot.fetch_user(tid)
        embed = discord.Embed(title="💬 محادثة شات أب جديدة", description=f"**من:** `@{sender[0]}`\n\n**الرسالة:**\n{self.content.value}", color=discord.Color.green())
        
        await target_user.send(embed=embed, view=ChatQuickReplyView(interaction.user.id, sender[0]))
        await interaction.response.send_message("✅ تم الإرسال للخاص!", ephemeral=True)

class ChatQuickReplyModal(ui.Modal, title="الرد السريع ↩️"):
    content = ui.TextInput(label="رسالتك", style=discord.TextStyle.paragraph)
    def __init__(self, target_id, sender_name):
        super().__init__()
        self.target_id = target_id
        self.sender_name = sender_name
        
    async def on_submit(self, interaction: discord.Interaction):
        sender = query_db("SELECT username FROM users WHERE discord_id = ?", (interaction.user.id,), one=True)
        target_user = bot.get_user(self.target_id) or await bot.fetch_user(self.target_id)
        
        embed = discord.Embed(title="💬 رد جديد - شات أب", description=f"**من:** `@{sender[0]}`\n\n**الرسالة:**\n{self.content.value}", color=discord.Color.green())
        await target_user.send(embed=embed, view=ChatQuickReplyView(interaction.user.id, sender[0]))
        await interaction.response.send_message("✅ تم إرسال الرد!", ephemeral=True)

class ChatQuickReplyView(ui.View):
    def __init__(self, target_id, target_name):
        super().__init__(timeout=None)
        self.target_id = target_id
        self.target_name = target_name
    @ui.button(label="الرد السريع ↩️", style=discord.ButtonStyle.success)
    async def reply(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(ChatQuickReplyModal(self.target_id, self.target_name))

class MarketModal(ui.Modal):
    title_inp = ui.TextInput(label="العنوان والسلعة")
    desc = ui.TextInput(label="التفاصيل والسعر", style=discord.TextStyle.paragraph)
    img = ui.TextInput(label="رابط صورة (اختياري)", required=False)
    
    def __init__(self, is_dark: bool):
        super().__init__(title="سوق الإنترنت المظلم ☠️" if is_dark else "سوق المدينة 🚗")
        self.is_dark = is_dark

    async def on_submit(self, interaction: discord.Interaction):
        user = query_db("SELECT username FROM users WHERE discord_id = ?", (interaction.user.id,), one=True)
        if not user: return await interaction.response.send_message("❌ سجل حسابك!", ephemeral=True)
        
        settings = query_db("SELECT market_channel, signature FROM settings WHERE guild_id = ?", (interaction.guild.id,), one=True)
        m_chan = interaction.guild.get_channel(settings[0])
        
        embed = discord.Embed(title=self.title_inp.value, description=self.desc.value, color=discord.Color.dark_theme() if self.is_dark else discord.Color.gold())
        if self.img.value: embed.set_image(url=self.img.value)
        
        if self.is_dark:
            embed.set_author(name="🥷 تاجر مجهول")
            view = MarketDarkView(interaction.user.id)
        else:
            embed.set_author(name=f"إعلان من: @{user[0]}")
            view = MarketLegalView(interaction.user.id, user[0])
            
        await m_chan.send(embed=embed, view=view)
        if settings[1]: await m_chan.send(content=settings[1])
        await interaction.response.send_message("✅ تم نشر إعلانك بالسوق!", ephemeral=True)

class MarketLegalView(ui.View):
    def __init__(self, owner_id, owner_name):
        super().__init__(timeout=None)
        self.owner_id = owner_id
        self.owner_name = owner_name
    @ui.button(label="تواصل مع البائع 📞", style=discord.ButtonStyle.primary)
    async def contact(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(ChatQuickReplyModal(self.owner_id, self.owner_name))

class MarketDarkView(ui.View):
    def __init__(self, owner_id):
        super().__init__(timeout=None)
        self.owner_id = owner_id
    @ui.button(label="شراء سري 💼", style=discord.ButtonStyle.danger)
    async def secret_buy(self, interaction: discord.Interaction, button: ui.Button):
        buyer = query_db("SELECT username FROM users WHERE discord_id = ?", (interaction.user.id,), one=True)
        await send_notification(self.owner_id, f"💼 العضو `@{buyer[0] if buyer else 'مجهول'}` مهتم بشراء سلعتك بالإنترنت المظلم، تواصل معه بحذر!", color=discord.Color.dark_red(), view=ChatQuickReplyView(interaction.user.id, buyer[0] if buyer else "مجهول"))
        await interaction.response.send_message("✅ تم إرسال رغبة الشراء للبائع سرياً.", ephemeral=True)

class GramModal(ui.Modal, title="نشر يوميات 📸"):
    content = ui.TextInput(label="التعليق على الصورة", max_length=100)
    img = ui.TextInput(label="رابط الصورة (إلزامي)")
    
    async def on_submit(self, interaction: discord.Interaction):
        user = query_db("SELECT username FROM users WHERE discord_id = ?", (interaction.user.id,), one=True)
        settings = query_db("SELECT gram_channel FROM settings WHERE guild_id = ?", (interaction.guild.id,), one=True)
        g_chan = interaction.guild.get_channel(settings[0])
        
        embed = discord.Embed(description=self.content.value, color=discord.Color.purple())
        embed.set_author(name=f"📸 ستوري: @{user[0]}")
        embed.set_image(url=self.img.value)
        await g_chan.send(embed=embed, view=GramLikeView())
        await interaction.response.send_message("✅ تم نشر الستوري!", ephemeral=True)

class GramLikeView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)
    @ui.button(label="دعم وتفاعل 👍", style=discord.ButtonStyle.secondary)
    async def support(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_message("❤️ تم إرسال تفاعلك للمشهور!", ephemeral=True)

# ==========================================
# 🎮 ألعاب U-Play المتكاملة
# ==========================================

class RPSView(ui.View):
    def __init__(self, original_menu):
        super().__init__(timeout=None)
        self.original_menu = original_menu
        
    async def play(self, interaction, user_choice):
        choices = {'rock': '🪨 حجر', 'paper': '📄 ورقة', 'scissors': '✂️ مقص'}
        bot_choice = random.choice(list(choices.keys()))
        
        res = "تعادل 🤝"
        if (user_choice == 'rock' and bot_choice == 'scissors') or \
           (user_choice == 'paper' and bot_choice == 'rock') or \
           (user_choice == 'scissors' and bot_choice == 'paper'):
            res = "أنت الفائز! 🎉"
        elif user_choice != bot_choice:
            res = "البوت فاز! 🤖"
            
        embed = discord.Embed(title="✊ حجر ورقة مقص", description=f"أنت اخترت: {choices[user_choice]}\nالبوت اختار: {choices[bot_choice]}\n\n**النتيجة: {res}**", color=discord.Color.blue())
        await interaction.response.edit_message(embed=embed, view=self.original_menu)

    @ui.button(emoji="🪨", style=discord.ButtonStyle.primary)
    async def btn_rock(self, interaction, button): await self.play(interaction, 'rock')
    @ui.button(emoji="📄", style=discord.ButtonStyle.primary)
    async def btn_paper(self, interaction, button): await self.play(interaction, 'paper')
    @ui.button(emoji="✂️", style=discord.ButtonStyle.primary)
    async def btn_scis(self, interaction, button): await self.play(interaction, 'scissors')

class TicTacToeView(ui.View):
    def __init__(self, original_menu):
        super().__init__(timeout=None)
        self.board = [0]*9
        self.original_menu = original_menu
        for i in range(9):
            btn = ui.Button(label=" ", style=discord.ButtonStyle.secondary, custom_id=str(i), row=i//3)
            btn.callback = self.btn_click
            self.add_item(btn)

    async def btn_click(self, interaction: discord.Interaction):
        idx = int(interaction.data['custom_id'])
        if self.board[idx] != 0: return await interaction.response.defer()
        
        self.board[idx] = 1 # User is 1 (X)
        self.children[idx].label = "X"
        self.children[idx].style = discord.ButtonStyle.success
        self.children[idx].disabled = True
        
        # Bot move (random empty)
        empty = [i for i, x in enumerate(self.board) if x == 0]
        if empty:
            bot_mv = random.choice(empty)
            self.board[bot_mv] = 2 # Bot is 2 (O)
            self.children[bot_mv].label = "O"
            self.children[bot_mv].style = discord.ButtonStyle.danger
            self.children[bot_mv].disabled = True
            
        await interaction.response.edit_message(view=self)

class GuessNumberModal(ui.Modal, title="تخمين الرقم 🔢"):
    guess = ui.TextInput(label="خمن رقم من 1 إلى 50")
    def __init__(self, original_menu):
        super().__init__()
        self.original_menu = original_menu
        self.secret = random.randint(1, 50)
        
    async def on_submit(self, interaction: discord.Interaction):
        try: val = int(self.guess.value)
        except: return await interaction.response.send_message("❌ ادخل رقماً!", ephemeral=True)
        
        res = "مبروك جبتها! 🎉" if val == self.secret else f"خطأ! الرقم كان {self.secret} 🤖"
        embed = discord.Embed(title="🔢 نتيجة التخمين", description=res, color=discord.Color.orange())
        await interaction.response.edit_message(embed=embed, view=self.original_menu)

# ==========================================
# 📱 القوائم المنسدلة (U-Phone UI)
# ==========================================

def get_app_menu(app_id):
    select = ui.Select(placeholder="اختر الإجراء المطلوب 👇", custom_id="app_sub_menu")
    
    if app_id == "tw":
        select.add_option(label="كتابة تغريدة", value="tw_write", emoji="📝")
        select.add_option(label="حسابي والترند", value="tw_profile", emoji="👤")
        select.add_option(label="الإشعارات", value="tw_notif", emoji="⚙️")
    elif app_id == "sh":
        select.add_option(label="إرسال رسالة مجهولة", value="sh_send", emoji="✉️")
    elif app_id == "ch":
        select.add_option(label="بدء محادثة جديدة", value="ch_new", emoji="💬")
    elif app_id == "mk":
        select.add_option(label="نشر إعلان قانوني", value="mk_legal", emoji="🚗")
        select.add_option(label="نشر إعلان مظلم", value="mk_dark", emoji="☠️")
    elif app_id == "gr":
        select.add_option(label="نشر ستوري", value="gr_story", emoji="📸")
    elif app_id == "pl":
        select.add_option(label="حجر ورقة مقص", value="pl_rps", emoji="✊")
        select.add_option(label="إكس أو", value="pl_xo", emoji="❌")
        select.add_option(label="تخمين الرقم", value="pl_guess", emoji="🔢")
    elif app_id == "id":
        select.add_option(label="إنشاء حساب", value="id_reg", emoji="📝")
        select.add_option(label="تقديم عضوية", value="id_verify", emoji="🏅")
        
    select.add_option(label="العودة للشاشة الرئيسية", value="back_main", emoji="🔙")
    select.add_option(label="إغلاق الجوال", value="close_phone", emoji="❌")
    
    view = ui.View(timeout=None)
    view.add_item(select)
    return view

class MainAppSelect(ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="تويتر", description="التدوين والمنشن", value="app_tw", emoji="🐦"),
            discord.SelectOption(label="شات أب", description="مراسلات شخصية", value="app_ch", emoji="💬"),
            discord.SelectOption(label="رسائل مجهولة", description="رسائل مشفرة وسرية", value="app_sh", emoji="🥷"),
            discord.SelectOption(label="سوق المدينة", description="إعلانات وممنوعات", value="app_mk", emoji="🛒"),
            discord.SelectOption(label="يو غرام", description="يوميات وستوريات", value="app_gr", emoji="📸"),
            discord.SelectOption(label="U-Play", description="ألعاب وتسلية", value="app_pl", emoji="🎮"),
            discord.SelectOption(label="إدارة الهوية", description="التسجيل والتوثيق", value="app_id", emoji="🛂"),
            discord.SelectOption(label="إغلاق الجوال", value="close_phone", emoji="❌")
        ]
        super().__init__(placeholder="📱 الشاشة الرئيسية - اختر تطبيقاً...", options=options, custom_id="main_apps_select")

    async def callback(self, interaction: discord.Interaction):
        val = self.values[0]
        if val == "close_phone":
            await interaction.message.delete()
        elif val.startswith("app_"):
            app_code = val.split("_")[1]
            embed = discord.Embed(title=f"📱 تطبيق مفتوح", description="الرجاء اختيار الإجراء من القائمة بالأسفل:", color=discord.Color.dark_grey())
            await interaction.response.edit_message(embed=embed, view=get_app_menu(app_code))

class MainAppMenuReceiver(commands.Cog):
    def __init__(self, bot): self.bot = bot
    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        if not interaction.is_select_menu() or interaction.data['custom_id'] != "app_sub_menu": return
        val = interaction.data['values'][0]
        
        # خيارات العودة والإغلاق
        if val == "close_phone": return await interaction.message.delete()
        if val == "back_main":
            settings = query_db("SELECT apps_img FROM settings WHERE guild_id = ?", (interaction.guild.id,), one=True)
            embed = discord.Embed(color=discord.Color.dark_theme()).set_image(url=settings[0] if settings else None)
            view = ui.View(timeout=None)
            view.add_item(MainAppSelect())
            return await interaction.response.edit_message(embed=embed, view=view)
            
        # استدعاء المودلز
        if val == "id_reg": await interaction.response.send_modal(RegisterModal())
        elif val == "id_verify": await interaction.response.send_message("تقديم العضوية يتطلب تواصل إداري.", ephemeral=True)
        elif val == "tw_write": await interaction.response.send_modal(TweetModal())
        elif val == "sh_send": await interaction.response.send_modal(ShadowMailModal())
        elif val == "ch_new": await interaction.response.send_modal(ChatAppModal())
        elif val == "mk_legal": await interaction.response.send_modal(MarketModal(False))
        elif val == "mk_dark": await interaction.response.send_modal(MarketModal(True))
        elif val == "gr_story": await interaction.response.send_modal(GramModal())
        
        # استدعاء الألعاب
        elif val == "pl_rps":
            embed = discord.Embed(title="✊ حجر ورقة مقص", description="اختر حركتك!")
            await interaction.response.edit_message(embed=embed, view=RPSView(get_app_menu('pl')))
        elif val == "pl_xo":
            embed = discord.Embed(title="❌ إكس أو ضد البوت", description="أنت X، ابدأ اللعب!")
            await interaction.response.edit_message(embed=embed, view=TicTacToeView(get_app_menu('pl')))
        elif val == "pl_guess":
            await interaction.response.send_modal(GuessNumberModal(get_app_menu('pl')))

class StartPhoneView(ui.View):
    def __init__(self): super().__init__(timeout=None)
    @ui.button(label="تشغيل الجوال 📱", style=discord.ButtonStyle.primary, custom_id="btn_start_phone")
    async def start(self, interaction: discord.Interaction, button: ui.Button):
        settings = query_db("SELECT apps_img FROM settings WHERE guild_id = ?", (interaction.guild.id,), one=True)
        embed = discord.Embed(color=discord.Color.dark_theme()).set_image(url=settings[0] if settings else None)
        view = ui.View(timeout=None)
        view.add_item(MainAppSelect())
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

# ==========================================
# 🛑 أوامر السلاش (التسطيب)
# ==========================================

@bot.event
async def on_ready():
    await bot.add_cog(MainAppMenuReceiver(bot))
    bot.add_view(StartPhoneView())
    print(f'✅ البوت جاهز: {bot.user.name}')
    await bot.tree.sync()

@bot.tree.command(name="تسطيب_الجوال", description="إعداد منظومة الجوال بالكامل")
@app_commands.checks.has_permissions(administrator=True)
async def setup_cmd(interaction: discord.Interaction, 
                    روم_الجوال: discord.TextChannel, 
                    روم_التغريدات: discord.TextChannel, 
                    روم_السوق: discord.TextChannel,
                    روم_اليوميات: discord.TextChannel,
                    صورة_الغلاف: str, 
                    صورة_الشاشة_الداخلية: str):
    
    query_db('''INSERT OR REPLACE INTO settings (guild_id, app_channel, tweet_channel, market_channel, gram_channel, panel_img, apps_img) 
              VALUES (?, ?, ?, ?, ?, ?, ?)''', 
              (interaction.guild.id, روم_الجوال.id, روم_التغريدات.id, روم_السوق.id, روم_اليوميات.id, صورة_الغلاف, صورة_الشاشة_الداخلية), commit=True)

    embed = discord.Embed(color=discord.Color.dark_theme()).set_image(url=صورة_الغلاف)
    await روم_الجوال.send(embed=embed, view=StartPhoneView())
    await interaction.response.send_message("✅ تم إعداد جوال المدينة وتسطيب التطبيقات بنجاح!", ephemeral=True)

token = os.getenv("DISCORD_TOKEN")
if token: bot.run(token)
else: print("❌ لم يتم العثور على التوكن!")
