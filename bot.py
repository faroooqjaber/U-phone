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
    """دالة مركزية آمنة للتعامل مع قاعدة البيانات"""
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
    """تهيئة الجداول للأنظمة القديمة والجديدة بدون تعارض"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # جداول تويتر القديمة والأساسية
    c.execute('''CREATE TABLE IF NOT EXISTS users (discord_id INTEGER PRIMARY KEY, username TEXT UNIQUE, verified INTEGER DEFAULT 0, account_type TEXT DEFAULT 'شخصي', notifications INTEGER DEFAULT 1, fame_points INTEGER DEFAULT 0)''')
    c.execute('''CREATE TABLE IF NOT EXISTS follows (follower_id INTEGER, followed_id INTEGER, PRIMARY KEY(follower_id, followed_id))''')
    c.execute('''CREATE TABLE IF NOT EXISTS settings (guild_id INTEGER PRIMARY KEY, app_channel INTEGER, tweet_channel INTEGER, market_channel INTEGER, gram_channel INTEGER, verify_channel INTEGER, admin_role INTEGER, embed_color TEXT DEFAULT '00acee', panel_img TEXT, apps_img TEXT, signature TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS tweets (message_id INTEGER PRIMARY KEY, author_id INTEGER, comments_open INTEGER DEFAULT 1)''')
    c.execute('''CREATE TABLE IF NOT EXISTS tweet_likes (message_id INTEGER, user_id INTEGER, PRIMARY KEY(message_id, user_id))''')
    c.execute('''CREATE TABLE IF NOT EXISTS tweet_rts (message_id INTEGER, user_id INTEGER, PRIMARY KEY(message_id, user_id))''')
    c.execute('''CREATE TABLE IF NOT EXISTS hashtags (tag TEXT PRIMARY KEY, count INTEGER DEFAULT 0)''')
    
    # محاولة حقن أعمدة جديدة في حال كانت قاعدة البيانات قديمة
    try: c.execute("ALTER TABLE settings ADD COLUMN market_channel INTEGER")
    except sqlite3.OperationalError: pass
    try: c.execute("ALTER TABLE settings ADD COLUMN gram_channel INTEGER")
    except sqlite3.OperationalError: pass
    try: c.execute("ALTER TABLE settings ADD COLUMN apps_img TEXT")
    except sqlite3.OperationalError: pass
    
    conn.commit()
    conn.close()

setup_db()

# ==============================================================================
# 3. دوال المساعدة والإشعارات والأمان
# ==============================================================================
async def send_notification(target_id, text, embed_title="🔔 إشعار جديد - U-Phone", color=discord.Color.blue(), view=None):
    """دالة لإرسال إشعارات الخاص باحترام إعدادات المستخدم"""
    status = query_db("SELECT notifications FROM users WHERE discord_id = ?", (target_id,), one=True)
    if status and status[0] == 0: 
        return # الإشعارات معطلة من قبل المستخدم
    try:
        user = bot.get_user(int(target_id)) or await bot.fetch_user(int(target_id))
        if user:
            embed = discord.Embed(title=embed_title, description=text, color=color)
            await user.send(embed=embed, view=view)
    except Exception as e:
        print(f"[Notif Error]: {e}")

def secure_text(text):
    """فحص الروابط لمنع الروابط الخارجية باستثناء الصور"""
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
            await interaction.response.send_message("❌ خطأ: اسم المستخدم هذا مستخدم بالفعل!", ephemeral=True)

class TweetModal(ui.Modal, title="🐦 نشر تغريدة جديدة"):
    content = ui.TextInput(label="محتوى التغريدة", style=discord.TextStyle.paragraph, placeholder="اكتب ما يدور في ذهنك... يمكنك منشن أي شخص بـ @يوزر", max_length=280)
    media = ui.TextInput(label="رابط صورة (اختياري)", placeholder="رابط مباشر للصورة ينتهي بـ .png أو .jpg", required=False)
    comments = ui.TextInput(label="هل تريد فتح التعليقات؟ (نعم / لا)", default="نعم", min_length=2, max_length=3)
    
    async def on_submit(self, interaction: discord.Interaction):
        user_data = query_db("SELECT username, verified, account_type FROM users WHERE discord_id = ?", (interaction.user.id,), one=True)
        if not user_data:
            return await interaction.response.send_message("❌ ليس لديك حساب! قم بإنشاء حساب أولاً.", ephemeral=True)
            
        comments_allowed = self.comments.value.strip()
        if comments_allowed not in ["نعم", "لا"]:
            return await interaction.response.send_message("❌ يجب كتابة 'نعم' أو 'لا' فقط!", ephemeral=True)
            
        text = self.content.value
        media_url = self.media.value.strip() if self.media.value else None
        
        if not secure_text(text) or (media_url and not secure_text(media_url)):
            return await interaction.response.send_message("❌ محظور! لا يُسمح بنشر روابط خارجية، مسموح بالصور فقط.", ephemeral=True)
            
        setting = query_db("SELECT tweet_channel FROM settings WHERE guild_id = ?", (interaction.guild.id,), one=True)
        if not setting or not setting[0]: 
            return await interaction.response.send_message("❌ لم يتم ضبط روم التغريدات بالسيرفر.", ephemeral=True)
            
        tweet_chan = interaction.guild.get_channel(setting[0])
        
        # نظام الهاشتاقات
        tags = re.findall(r'#\w+', text)
        for tag in tags:
            query_db("INSERT INTO hashtags (tag, count) VALUES (?, 1) ON CONFLICT(tag) DO UPDATE SET count = count + 1", (tag,), commit=True)
            
        # تحديد الشارة
        badge = ""
        if user_data[1] == 1:
            if user_data[2] == "حساب حكومي": badge = " 🏛️"
            elif user_data[2] == "حساب تجاري": badge = " 💼"
            else: badge = " ☑️"
            
        embed = discord.Embed(description=text, color=discord.Color.blue(), timestamp=datetime.utcnow())
        embed.set_author(name=f"{interaction.user.display_name} (@{user_data[0]}){badge}", icon_url=interaction.user.display_avatar.url)
        if media_url: embed.set_image(url=media_url)
        embed.set_footer(text="U-Phone | Twitter")
        embed.add_field(name="📊 إحصائيات التفاعل:", value="❤️ الإعجابات: **0** | 🔁 إعادة النشر: **0**", inline=False)
        
        # إنشاء أزرار ديناميكية تحمل الـ ID لضمان عملها دائماً
        view = ui.View(timeout=None)
        
        msg = await tweet_chan.send(embed=embed)
        
        # تحديث الأزرار بالـ Message ID الفعلي
        view.add_item(ui.Button(label="أعجبني ❤️", style=discord.ButtonStyle.secondary, custom_id=f"tw_like_{msg.id}"))
        view.add_item(ui.Button(label="إعادة نشر 🔁", style=discord.ButtonStyle.secondary, custom_id=f"tw_rt_{msg.id}"))
        view.add_item(ui.Button(label="رد 💬", style=discord.ButtonStyle.secondary, custom_id=f"tw_reply_{msg.id}"))
        
        await msg.edit(view=view)
        
        is_open = 1 if comments_allowed == "نعم" else 0
        query_db("INSERT INTO tweets (message_id, author_id, comments_open) VALUES (?, ?, ?)", (msg.id, interaction.user.id, is_open), commit=True)
        
        # نظام المنشن الفعلي
        mentions = re.findall(r'@([a-zA-Z0-9_]+)', text)
        for mentioned_user in list(set(mentions)):
            if mentioned_user.lower() != user_data[0].lower():
                target_res = query_db("SELECT discord_id FROM users WHERE username = ?", (mentioned_user.lower(),), one=True)
                if target_res:
                    await send_notification(target_res[0], f"👤 قام `@{user_data[0]}` بالإشارة إليك في تغريدته!\n🔗 [إضغط هنا للانتقال]({msg.jump_url})")

        await interaction.response.send_message("✅ تم نشر تغريدتك بنجاح!", ephemeral=True)

class ReplyModal(ui.Modal, title="💬 الرد على التغريدة"):
    reply_text = ui.TextInput(label="اكتب ردك هنا", style=discord.TextStyle.paragraph, max_length=250)
    
    def __init__(self, message: discord.Message):
        super().__init__()
        self.message = message
        
    async def on_submit(self, interaction: discord.Interaction):
        user_data = query_db("SELECT username FROM users WHERE discord_id = ?", (interaction.user.id,), one=True)
        if not user_data: return await interaction.response.send_message("❌ يجب إنشاء حساب أولاً!", ephemeral=True)
        
        text = self.reply_text.value
        if not secure_text(text): return await interaction.response.send_message("❌ محظور وضع روابط خارجية!", ephemeral=True)
        
        thread = self.message.thread
        if thread is None:
            thread = await self.message.create_thread(name=f"ردود المغردين", auto_archive_duration=60)
            
        rembed = discord.Embed(description=text, color=discord.Color.light_grey(), timestamp=datetime.utcnow())
        rembed.set_author(name=f"رد من @{user_data[0]}", icon_url=interaction.user.display_avatar.url)
        await thread.send(embed=rembed)
        await interaction.response.send_message("✅ تم إضافة ردك!", ephemeral=True)

class SearchProfileModal(ui.Modal, title="🔍 البحث عن حساب"):
    username = ui.TextInput(label="يوزر الحساب المراد البحث عنه (بدون @)")
    
    async def on_submit(self, interaction: discord.Interaction):
        target = self.username.value.strip().lower()
        res = query_db("SELECT discord_id, verified, account_type FROM users WHERE username = ?", (target,), one=True)
        if not res: return await interaction.response.send_message("❌ لم يتم العثور على حساب بهذا اليوزر.", ephemeral=True)
        
        followers = len(query_db("SELECT follower_id FROM follows WHERE followed_id = ?", (res[0],)))
        following = len(query_db("SELECT followed_id FROM follows WHERE follower_id = ?", (res[0],)))
        
        acc_str = f"موثق ({res[2]})" if res[1] == 1 else "غير موثق / شخصي"
        embed = discord.Embed(title=f"👤 ملف الحساب: @{target}", color=discord.Color.blue())
        embed.add_field(name="فئة الحساب:", value=acc_str, inline=False)
        embed.add_field(name="المتابعون:", value=f"**{followers}**", inline=True)
        embed.add_field(name="يتابع:", value=f"**{following}**", inline=True)
        
        view = ui.View(timeout=None)
        view.add_item(ui.Button(label="متابعة / إلغاء ➕", style=discord.ButtonStyle.primary, custom_id=f"tw_follow_{res[0]}"))
        
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

# ==============================================================================
# 5. النماذج (Modals) للتطبيقات الجديدة (Shadow, Chat, Market, Gram)
# ==============================================================================
class ShadowMailModal(ui.Modal, title="🥷 إرسال رسالة مجهولة"):
    target = ui.TextInput(label="يوزر المستهدف (بدون @)")
    content = ui.TextInput(label="الرسالة السرية", style=discord.TextStyle.paragraph)
    
    async def on_submit(self, interaction: discord.Interaction):
        tid = query_db("SELECT discord_id FROM users WHERE username = ?", (self.target.value.strip().lower(),), one=True)
        if not tid: return await interaction.response.send_message("❌ اليوزر غير موجود في المدينة!", ephemeral=True)
        
        embed = discord.Embed(title="⚠️ رسالة مشفرة من جهة مجهولة", description=self.content.value, color=discord.Color.from_rgb(10, 10, 10))
        await send_notification(tid[0], text="", embed_title="⚠️ رسالة مشفرة", color=discord.Color.darker_grey())
        
        try:
            target_user = bot.get_user(tid[0]) or await bot.fetch_user(tid[0])
            await target_user.send(embed=embed)
            await interaction.response.send_message("🥷 تم تشفير الرسالة وإرسالها بنجاح.", ephemeral=True)
        except:
            await interaction.response.send_message("❌ المستهدف يغلق الرسائل الخاصة.", ephemeral=True)

class ChatAppModal(ui.Modal, title="💬 شات أب - بدء محادثة"):
    target = ui.TextInput(label="يوزر المستهدف (بدون @)")
    content = ui.TextInput(label="الرسالة", style=discord.TextStyle.paragraph)
    
    async def on_submit(self, interaction: discord.Interaction):
        sender = query_db("SELECT username FROM users WHERE discord_id = ?", (interaction.user.id,), one=True)
        if not sender: return await interaction.response.send_message("❌ سجل حسابك أولاً!", ephemeral=True)
        
        tid = query_db("SELECT discord_id FROM users WHERE username = ?", (self.target.value.strip().lower(),), one=True)
        if not tid: return await interaction.response.send_message("❌ اليوزر غير موجود!", ephemeral=True)
        
        embed = discord.Embed(title="💬 رسالة شات أب جديدة", description=f"**من:** `@{sender[0]}`\n\n**الرسالة:**\n{self.content.value}", color=discord.Color.green())
        
        view = ui.View(timeout=None)
        view.add_item(ui.Button(label="الرد السريع ↩️", style=discord.ButtonStyle.success, custom_id=f"ch_reply_{interaction.user.id}_{sender[0]}"))
        
        try:
            target_user = bot.get_user(tid[0]) or await bot.fetch_user(tid[0])
            await target_user.send(embed=embed, view=view)
            await interaction.response.send_message("✅ تم الإرسال للمستهدف في الخاص!", ephemeral=True)
        except:
            await interaction.response.send_message("❌ المستهدف يغلق الرسائل الخاصة.", ephemeral=True)

class ChatQuickReplyModal(ui.Modal, title="↩️ الرد السريع"):
    content = ui.TextInput(label="رسالتك", style=discord.TextStyle.paragraph)
    
    def __init__(self, target_id, target_name):
        super().__init__()
        self.target_id = int(target_id)
        self.target_name = target_name
        
    async def on_submit(self, interaction: discord.Interaction):
        sender = query_db("SELECT username FROM users WHERE discord_id = ?", (interaction.user.id,), one=True)
        embed = discord.Embed(title="💬 رد جديد - شات أب", description=f"**من:** `@{sender[0]}`\n\n**الرسالة:**\n{self.content.value}", color=discord.Color.green())
        
        view = ui.View(timeout=None)
        view.add_item(ui.Button(label="الرد السريع ↩️", style=discord.ButtonStyle.success, custom_id=f"ch_reply_{interaction.user.id}_{sender[0]}"))
        
        try:
            target_user = bot.get_user(self.target_id) or await bot.fetch_user(self.target_id)
            await target_user.send(embed=embed, view=view)
            await interaction.response.send_message("✅ تم إرسال الرد السريع بنجاح!", ephemeral=True)
        except:
            await interaction.response.send_message("❌ فشل الإرسال، المستهدف أغلق الخاص.", ephemeral=True)

class MarketModal(ui.Modal):
    title_inp = ui.TextInput(label="عنوان الإعلان والسلعة")
    desc = ui.TextInput(label="التفاصيل والسعر", style=discord.TextStyle.paragraph)
    img = ui.TextInput(label="رابط صورة (اختياري)", required=False)
    
    def __init__(self, is_dark: bool):
        super().__init__(title="سوق الإنترنت المظلم ☠️" if is_dark else "سوق المدينة القانوني 🚗")
        self.is_dark = is_dark

    async def on_submit(self, interaction: discord.Interaction):
        user = query_db("SELECT username FROM users WHERE discord_id = ?", (interaction.user.id,), one=True)
        if not user: return await interaction.response.send_message("❌ سجل حسابك أولاً!", ephemeral=True)
        
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
            embed.set_author(name=f"إعلان من: @{user[0]}")
            view.add_item(ui.Button(label="تواصل مع البائع 📞", style=discord.ButtonStyle.primary, custom_id=f"mk_contact_{interaction.user.id}_{user[0]}"))
            
        await m_chan.send(embed=embed, view=view)
        await interaction.response.send_message("✅ تم نشر إعلانك بالسوق!", ephemeral=True)

class GramModal(ui.Modal, title="📸 يو جرام - نشر يوميات"):
    content = ui.TextInput(label="التعليق على الصورة", max_length=150)
    img = ui.TextInput(label="رابط الصورة (إلزامي)")
    
    async def on_submit(self, interaction: discord.Interaction):
        user = query_db("SELECT username FROM users WHERE discord_id = ?", (interaction.user.id,), one=True)
        if not user: return await interaction.response.send_message("❌ أنشئ حسابك أولاً!", ephemeral=True)
        
        settings = query_db("SELECT gram_channel FROM settings WHERE guild_id = ?", (interaction.guild.id,), one=True)
        if not settings or not settings[0]: return await interaction.response.send_message("❌ روم اليوميات غير مفعل.", ephemeral=True)
        g_chan = interaction.guild.get_channel(settings[0])
        
        embed = discord.Embed(description=self.content.value, color=discord.Color.purple())
        embed.set_author(name=f"📸 ستوري: @{user[0]}")
        embed.set_image(url=self.img.value)
        
        view = ui.View(timeout=None)
        view.add_item(ui.Button(label="دعم وتفاعل 👍", style=discord.ButtonStyle.secondary, custom_id="gr_like"))
        
        await g_chan.send(embed=embed, view=view)
        await interaction.response.send_message("✅ تم نشر الستوري بنجاح! (يختفي بعد 24 ساعة ضمنياً في الرول بلاي)", ephemeral=True)

class ApplyMembershipModal(ui.Modal, title="📝 التقديم على عضوية رسمية"):
    char_name = ui.TextInput(label="الاسم وتفاصيل الشخصية (IC)", placeholder="مثال: عمر الراشدي", max_length=100)
    char_exp = ui.TextInput(label="الخبرات والأهداف", style=discord.TextStyle.paragraph, max_length=500)
    
    async def on_submit(self, interaction: discord.Interaction):
        settings = query_db("SELECT verify_channel FROM settings WHERE guild_id = ?", (interaction.guild.id,), one=True)
        if not settings or not settings[0]: return await interaction.response.send_message("❌ روم التقديمات غير مفعل.", ephemeral=True)
        v_chan = interaction.guild.get_channel(settings[0])
        
        embed = discord.Embed(title="📥 طلب عضوية قيد المراجعة", color=discord.Color.teal())
        embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)
        embed.add_field(name="👤 الشخصية:", value=self.char_name.value, inline=False)
        embed.add_field(name="📜 التفاصيل:", value=self.char_exp.value, inline=False)
        
        view = ui.View(timeout=None)
        view.add_item(ui.Button(label="قبول ✅", style=discord.ButtonStyle.success, custom_id=f"vf_accept_{interaction.user.id}"))
        view.add_item(ui.Button(label="رفض ❌", style=discord.ButtonStyle.danger, custom_id=f"vf_reject_{interaction.user.id}"))
        
        await v_chan.send(embed=embed, view=view)
        await interaction.response.send_message("✅ تم إرسال طلبك للإدارة!", ephemeral=True)

# ==============================================================================
# 6. قسم الألعاب الفردية (U-Play)
# ==============================================================================
class RPSView(ui.View):
    def __init__(self): super().__init__(timeout=None)
    async def play(self, interaction, user_choice):
        bot_choice = random.choice(['حجر', 'ورقة', 'مقص'])
        res = "تعادل 🤝"
        if (user_choice=='حجر' and bot_choice=='مقص') or (user_choice=='ورقة' and bot_choice=='حجر') or (user_choice=='مقص' and bot_choice=='ورقة'): res = "أنت الفائز! 🎉"
        elif user_choice != bot_choice: res = "البوت فاز! 🤖"
        embed = discord.Embed(title="✊ حجر ورقة مقص", description=f"اختيارك: **{user_choice}**\nاختيار البوت: **{bot_choice}**\n\nالنتيجة: {res}", color=discord.Color.green())
        await interaction.response.edit_message(embed=embed, view=None)

    @ui.button(emoji="🪨", style=discord.ButtonStyle.primary, custom_id="rps_r")
    async def r(self, interaction: discord.Interaction, button: ui.Button): await self.play(interaction, 'حجر')
    @ui.button(emoji="📄", style=discord.ButtonStyle.primary, custom_id="rps_p")
    async def p(self, interaction: discord.Interaction, button: ui.Button): await self.play(interaction, 'ورقة')
    @ui.button(emoji="✂️", style=discord.ButtonStyle.primary, custom_id="rps_s")
    async def s(self, interaction: discord.Interaction, button: ui.Button): await self.play(interaction, 'مقص')

class TicTacToeView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.board = [0]*9
        for i in range(9):
            self.add_item(ui.Button(label=" ", style=discord.ButtonStyle.secondary, custom_id=f"xo_{i}", row=i//3))

    async def check_winner(self):
        win_cond = [(0,1,2),(3,4,5),(6,7,8),(0,3,6),(1,4,7),(2,5,8),(0,4,8),(2,4,6)]
        for a,b,c in win_cond:
            if self.board[a] == self.board[b] == self.board[c] != 0: return self.board[a]
        if 0 not in self.board: return 3 # تعادل
        return 0

    async def process_move(self, interaction: discord.Interaction, idx: int):
        if self.board[idx] != 0: return await interaction.response.defer()
        
        # حركة اللاعب
        self.board[idx] = 1
        self.children[idx].label = "X"
        self.children[idx].style = discord.ButtonStyle.success
        self.children[idx].disabled = True
        
        winner = await self.check_winner()
        if winner == 0:
            # حركة البوت
            empty = [i for i, x in enumerate(self.board) if x == 0]
            if empty:
                bot_mv = random.choice(empty)
                self.board[bot_mv] = 2
                self.children[bot_mv].label = "O"
                self.children[bot_mv].style = discord.ButtonStyle.danger
                self.children[bot_mv].disabled = True
                winner = await self.check_winner()

        if winner != 0:
            for child in self.children: child.disabled = True
            msg = "فزت يا وحش! 🎉" if winner == 1 else "البوت فاز 🤖" if winner == 2 else "تعادل 🤝"
            await interaction.response.edit_message(content=msg, view=self)
        else:
            await interaction.response.edit_message(view=self)

class GuessNumModal(ui.Modal, title="🔢 تخمين الرقم السري"):
    guess = ui.TextInput(label="خمن رقماً من 1 إلى 50")
    async def on_submit(self, interaction: discord.Interaction):
        secret = random.randint(1, 50)
        try: v = int(self.guess.value)
        except: return await interaction.response.send_message("❌ يرجى إدخال أرقام فقط!", ephemeral=True)
        res = "مبروووك جبتها! 🎉" if v == secret else f"خطأ للأسف، الرقم السري كان {secret} 🤖"
        await interaction.response.send_message(res, ephemeral=True)

# ==============================================================================
# 7. هندسة واجهة الجوال الرئيسية (القوائم المنسدلة)
# ==============================================================================
class SubAppSelect(ui.Select):
    def __init__(self, app_code):
        options = []
        if app_code == "tw":
            options = [
                discord.SelectOption(label="كتابة تغريدة", value="tw_write", emoji="📝"),
                discord.SelectOption(label="حسابي والترند", value="tw_prof", emoji="👤"),
                discord.SelectOption(label="البحث عن حساب", value="tw_srch", emoji="🔍"),
                discord.SelectOption(label="الإشعارات", value="tw_notif", emoji="⚙️")
            ]
        elif app_code == "sh": options = [discord.SelectOption(label="إرسال رسالة مجهولة", value="sh_send", emoji="✉️")]
        elif app_code == "ch": options = [discord.SelectOption(label="بدء محادثة جديدة", value="ch_new", emoji="💬")]
        elif app_code == "mk": 
            options = [
                discord.SelectOption(label="نشر إعلان قانوني", value="mk_legal", emoji="🚗"),
                discord.SelectOption(label="نشر إعلان مظلم", value="mk_dark", emoji="☠️")
            ]
        elif app_code == "gr": options = [discord.SelectOption(label="نشر ستوري", value="gr_post", emoji="📸")]
        elif app_code == "pl": 
            options = [
                discord.SelectOption(label="حجر ورقة مقص", value="pl_rps", emoji="✊"),
                discord.SelectOption(label="لعبة إكس أو", value="pl_xo", emoji="❌"),
                discord.SelectOption(label="تخمين الرقم", value="pl_gn", emoji="🔢")
            ]
        elif app_code == "id":
            options = [
                discord.SelectOption(label="إنشاء حساب بالجوال", value="id_reg", emoji="📝"),
                discord.SelectOption(label="تقديم طلب عضوية", value="id_ver", emoji="🏅")
            ]
            
        options.extend([
            discord.SelectOption(label="العودة للشاشة الرئيسية", value="back_home", emoji="🔙"),
            discord.SelectOption(label="إغلاق الهاتف", value="close_phone", emoji="❌")
        ])
        super().__init__(placeholder="اختر الإجراء المطلوب...", options=options, custom_id="sub_app_dropdown")

class MainAppSelect(ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="تويتر المدينة", value="app_tw", emoji="🐦"),
            discord.SelectOption(label="شات أب", value="app_ch", emoji="💬"),
            discord.SelectOption(label="رسائل مجهولة", value="app_sh", emoji="🥷"),
            discord.SelectOption(label="سوق المدينة", value="app_mk", emoji="🛒"),
            discord.SelectOption(label="يو غرام (يوميات)", value="app_gr", emoji="📸"),
            discord.SelectOption(label="U-Play ألعاب", value="app_pl", emoji="🎮"),
            discord.SelectOption(label="الهوية والتقديمات", value="app_id", emoji="🛂"),
            discord.SelectOption(label="إغلاق وقفل الهاتف", value="close_phone", emoji="❌")
        ]
        super().__init__(placeholder="📱 اضغط هنا لفتح التطبيقات...", options=options, custom_id="main_app_dropdown")

class MainPhoneReceiver(commands.Cog):
    def __init__(self, bot): self.bot = bot
    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        if not interaction.is_select_menu(): return
        custom_id = interaction.data.get('custom_id')
        if custom_id not in ["main_app_dropdown", "sub_app_dropdown"]: return
        
        val = interaction.data['values'][0]
        
        if val == "close_phone": return await interaction.message.delete()
        
        if custom_id == "main_app_dropdown":
            app_code = val.split('_')[1]
            view = ui.View(timeout=None).add_item(SubAppSelect(app_code))
            embed = discord.Embed(title=f"📱 تطبيق {app_code.upper()}", description="الرجاء اختيار الإجراء من القائمة بالأسفل:", color=discord.Color.dark_grey())
            await interaction.response.edit_message(embed=embed, view=view)
            
        elif custom_id == "sub_app_dropdown":
            if val == "back_home":
                img = query_db("SELECT apps_img FROM settings WHERE guild_id = ?", (interaction.guild.id,), one=True)
                embed = discord.Embed(title="📱 شاشة التطبيقات الذكية", color=discord.Color.from_rgb(30,30,30))
                if img and img[0]: embed.set_image(url=img[0])
                view = ui.View(timeout=None).add_item(MainAppSelect())
                return await interaction.response.edit_message(embed=embed, view=view)
                
            # توجيه الخيارات
            if val == "tw_write": await interaction.response.send_modal(TweetModal())
            elif val == "tw_srch": await interaction.response.send_modal(SearchProfileModal())
            elif val == "tw_prof":
                data = query_db("SELECT username, verified, account_type FROM users WHERE discord_id = ?", (interaction.user.id,), one=True)
                if not data: return await interaction.response.send_message("❌ لا يوجد حساب!", ephemeral=True)
                flws = len(query_db("SELECT follower_id FROM follows WHERE followed_id = ?", (interaction.user.id,)))
                tags = query_db("SELECT tag, count FROM hashtags ORDER BY count DESC LIMIT 5")
                tags_str = "\n".join([f"🔥 {t[0]} ({t[1]} تغريدة)" for t in tags]) if tags else "لا يوجد ترند حالياً."
                em = discord.Embed(title=f"👤 حسابي: @{data[0]}", color=discord.Color.blue())
                em.add_field(name="المتابعون:", value=str(flws), inline=True)
                em.add_field(name="فئة החשבון:", value=data[2], inline=True)
                em.add_field(name="الترند:", value=tags_str, inline=False)
                await interaction.response.send_message(embed=em, ephemeral=True)
            elif val == "tw_notif":
                sts = query_db("SELECT notifications FROM users WHERE discord_id = ?", (interaction.user.id,), one=True)
                new_sts = 0 if sts and sts[0] == 1 else 1
                query_db("UPDATE users SET notifications = ? WHERE discord_id = ?", (new_sts, interaction.user.id), commit=True)
                await interaction.response.send_message(f"⚙️ تم التحديث، الإشعارات: {'مفعلة 🔔' if new_sts else 'معطلة 🔕'}", ephemeral=True)
            
            elif val == "sh_send": await interaction.response.send_modal(ShadowMailModal())
            elif val == "ch_new": await interaction.response.send_modal(ChatAppModal())
            elif val == "mk_legal": await interaction.response.send_modal(MarketModal(False))
            elif val == "mk_dark": await interaction.response.send_modal(MarketModal(True))
            elif val == "gr_post": await interaction.response.send_modal(GramModal())
            elif val == "id_reg": await interaction.response.send_modal(RegisterModal())
            elif val == "id_ver": await interaction.response.send_modal(ApplyMembershipModal())
            
            elif val == "pl_rps": await interaction.response.send_message(view=RPSView(), ephemeral=True)
            elif val == "pl_xo": await interaction.response.send_message("❌ إكس أو:", view=TicTacToeView(), ephemeral=True)
            elif val == "pl_gn": await interaction.response.send_modal(GuessNumModal())

class StartPhoneView(ui.View):
    def __init__(self): super().__init__(timeout=None)
    @ui.button(label="تشغيل الجوال 📱", style=discord.ButtonStyle.primary, custom_id="start_os_btn")
    async def boot(self, interaction: discord.Interaction, button: ui.Button):
        img = query_db("SELECT apps_img FROM settings WHERE guild_id = ?", (interaction.guild.id,), one=True)
        embed = discord.Embed(title="📱 شاشة التطبيقات الذكية", description="اختر تطبيقاً من القائمة المنسدلة بالأسفل للبدء:", color=discord.Color.from_rgb(30,30,30))
        if img and img[0]: embed.set_image(url=img[0])
        view = ui.View(timeout=None).add_item(MainAppSelect())
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

# ==============================================================================
# 8. معالج الأزرار الديناميكية (السر في عدم ظهور خطأ أحمر)
# ==============================================================================
@bot.event
async def on_interaction(interaction: discord.Interaction):
    if interaction.type != discord.InteractionType.component: return
    custom_id = interaction.data.get('custom_id', '')
    
    # 🐦 أزرار تويتر (لايك، ريتويت، رد، فولو)
    if custom_id.startswith('tw_like_'):
        msg_id = int(custom_id.split('_')[2])
        liked = query_db("SELECT 1 FROM tweet_likes WHERE message_id = ? AND user_id = ?", (msg_id, interaction.user.id), one=True)
        author = query_db("SELECT author_id FROM tweets WHERE message_id = ?", (msg_id,), one=True)
        if liked: query_db("DELETE FROM tweet_likes WHERE message_id = ? AND user_id = ?", (msg_id, interaction.user.id), commit=True)
        else:
            query_db("INSERT INTO tweet_likes (message_id, user_id) VALUES (?, ?)", (msg_id, interaction.user.id), commit=True)
            if author and author[0] != interaction.user.id:
                uname = query_db("SELECT username FROM users WHERE discord_id = ?", (interaction.user.id,), one=True)
                await send_notification(author[0], f"❤️ قام `@{uname[0] if uname else 'شخص'}` بالإعجاب بتغريدتك!")
        
        likes = query_db("SELECT COUNT(*) FROM tweet_likes WHERE message_id = ?", (msg_id,), one=True)[0]
        rts = query_db("SELECT COUNT(*) FROM tweet_rts WHERE message_id = ?", (msg_id,), one=True)[0]
        embed = interaction.message.embeds[0]
        embed.set_field_at(0, name="📊 إحصائيات التفاعل:", value=f"❤️ الإعجابات: **{likes}** | 🔁 إعادة النشر: **{rts}**", inline=False)
        await interaction.response.edit_message(embed=embed)
        
    elif custom_id.startswith('tw_rt_'):
        msg_id = int(custom_id.split('_')[2])
        rted = query_db("SELECT 1 FROM tweet_rts WHERE message_id = ? AND user_id = ?", (msg_id, interaction.user.id), one=True)
        author = query_db("SELECT author_id FROM tweets WHERE message_id = ?", (msg_id,), one=True)
        if rted: query_db("DELETE FROM tweet_rts WHERE message_id = ? AND user_id = ?", (msg_id, interaction.user.id), commit=True)
        else:
            query_db("INSERT INTO tweet_rts (message_id, user_id) VALUES (?, ?)", (msg_id, interaction.user.id), commit=True)
            if author and author[0] != interaction.user.id:
                uname = query_db("SELECT username FROM users WHERE discord_id = ?", (interaction.user.id,), one=True)
                await send_notification(author[0], f"🔁 قام `@{uname[0] if uname else 'شخص'}` بإعادة نشر تغريدتك!")
        
        likes = query_db("SELECT COUNT(*) FROM tweet_likes WHERE message_id = ?", (msg_id,), one=True)[0]
        rts = query_db("SELECT COUNT(*) FROM tweet_rts WHERE message_id = ?", (msg_id,), one=True)[0]
        embed = interaction.message.embeds[0]
        embed.set_field_at(0, name="📊 إحصائيات التفاعل:", value=f"❤️ الإعجابات: **{likes}** | 🔁 إعادة النشر: **{rts}**", inline=False)
        await interaction.response.edit_message(embed=embed)
        
    elif custom_id.startswith('tw_reply_'):
        msg_id = int(custom_id.split('_')[2])
        status = query_db("SELECT comments_open FROM tweets WHERE message_id = ?", (msg_id,), one=True)
        if status and status[0] == 0: return await interaction.response.send_message("❌ التعليقات مغلقة لهذه التغريدة!", ephemeral=True)
        await interaction.response.send_modal(ReplyModal(interaction.message))
        
    elif custom_id.startswith('tw_follow_'):
        target_id = int(custom_id.split('_')[2])
        if interaction.user.id == target_id: return await interaction.response.send_message("❌ لا يمكنك متابعة نفسك!", ephemeral=True)
        is_f = query_db("SELECT 1 FROM follows WHERE follower_id = ? AND followed_id = ?", (interaction.user.id, target_id), one=True)
        if is_f:
            query_db("DELETE FROM follows WHERE follower_id = ? AND followed_id = ?", (interaction.user.id, target_id), commit=True)
            await interaction.response.send_message("❌ تم إلغاء المتابعة.", ephemeral=True)
        else:
            query_db("INSERT INTO follows (follower_id, followed_id) VALUES (?, ?)", (interaction.user.id, target_id), commit=True)
            uname = query_db("SELECT username FROM users WHERE discord_id = ?", (interaction.user.id,), one=True)
            await send_notification(target_id, f"➕ بدأ `@{uname[0] if uname else 'شخص'}` بمتابعتك!")
            await interaction.response.send_message("✅ تمت المتابعة بنجاح!", ephemeral=True)

    # 💬 أزرار الشات والسوق
    elif custom_id.startswith('ch_reply_'):
        parts = custom_id.split('_')
        target_id = parts[2]
        target_name = parts[3]
        await interaction.response.send_modal(ChatQuickReplyModal(target_id, target_name))
        
    elif custom_id.startswith('mk_buy_'):
        owner_id = int(custom_id.split('_')[2])
        buyer = query_db("SELECT username FROM users WHERE discord_id = ?", (interaction.user.id,), one=True)
        view = ui.View(timeout=None)
        view.add_item(ui.Button(label="تواصل ↩️", style=discord.ButtonStyle.success, custom_id=f"ch_reply_{interaction.user.id}_{buyer[0] if buyer else 'مجهول'}"))
        await send_notification(owner_id, f"💼 العضو `@{buyer[0] if buyer else 'مجهول'}` مهتم بشراء سلعتك بالإنترنت المظلم!", color=discord.Color.dark_red(), view=view)
        await interaction.response.send_message("✅ تم إرسال رغبتك للبائع سرياً.", ephemeral=True)
        
    elif custom_id.startswith('mk_contact_'):
        parts = custom_id.split('_')
        await interaction.response.send_modal(ChatQuickReplyModal(parts[2], parts[3]))
        
    elif custom_id == "gr_like":
        await interaction.response.send_message("❤️ تم إرسال الدعم والتفاعل للمشهور!", ephemeral=True)

    # 🏅 أزرار تقديم العضوية
    elif custom_id.startswith('vf_accept_') or custom_id.startswith('vf_reject_'):
        data = query_db("SELECT admin_role FROM settings WHERE guild_id = ?", (interaction.guild.id,), one=True)
        if not data or not data[0]: return await interaction.response.send_message("❌ لم يتم تحديد رتبة الإدارة.", ephemeral=True)
        role = interaction.guild.get_role(data[0])
        if not role or role not in interaction.user.roles: return await interaction.response.send_message("❌ ليس لديك صلاحية الإدارة!", ephemeral=True)
        
        target_id = int(custom_id.split('_')[2])
        action = "قبول ✅" if "accept" in custom_id else "رفض ❌"
        
        embed = interaction.message.embeds[0]
        embed.title = f"تم {action} الطلب"
        embed.color = discord.Color.green() if "accept" in custom_id else discord.Color.red()
        embed.add_field(name="المسؤول:", value=f"{interaction.user.mention}", inline=False)
        
        try:
            target_user = bot.get_user(target_id) or await bot.fetch_user(target_id)
            await target_user.send(embed=discord.Embed(title="📣 نتيجة التقديم", description=f"تم **{action}** طلب انضمامك للمدينة.", color=embed.color))
        except: pass
        
        await interaction.response.edit_message(embed=embed, view=None)
        
    # 🎮 أزرار إكس أو
    elif custom_id.startswith('xo_'):
        idx = int(custom_id.split('_')[1])
        # لا يمكن تحديث XO بدون تمرير الـ view من الرسالة، سيتم معالجتها داخل الكلاس نفسه.

# ==============================================================================
# 9. الأوامر العامة والتسطيب
# ==============================================================================
@bot.tree.command(name="تسطيب_الجوال", description="إعداد وتهيئة منظومة الجوال بالكامل وروماتها")
@app_commands.checks.has_permissions(administrator=True)
async def setup_cmd(interaction: discord.Interaction, 
                    روم_الجوال: discord.TextChannel,
                    روم_التغريدات: discord.TextChannel,
                    روم_السوق: discord.TextChannel,
                    روم_اليوميات: discord.TextChannel,
                    روم_التقديمات: discord.TextChannel,
                    رتبة_المسؤولين: discord.Role,
                    توقيع_الخط: str,
                    صورة_الغلاف: str,
                    صورة_الشاشة: str):
    await interaction.response.defer(ephemeral=True)
    query_db('''INSERT OR REPLACE INTO settings (guild_id, app_channel, tweet_channel, market_channel, gram_channel, verify_channel, admin_role, signature, panel_img, apps_img) VALUES (?,?,?,?,?,?,?,?,?,?)''',
             (interaction.guild.id, روم_الجوال.id, روم_التغريدات.id, روم_السوق.id, روم_اليوميات.id, روم_التقديمات.id, رتبة_المسؤولين.id, توقيع_الخط, صورة_الغلاف, صورة_الشاشة), commit=True)
    
    embed = discord.Embed(title="URG | OS Phone System", description="اضغط الزر بالأسفل لتشغيل الجوال وفتح التطبيقات").set_image(url=صورة_الغلاف)
    await روم_الجوال.send(embed=embed, view=StartPhoneView())
    if توقيع_الخط: await روم_الجوال.send(توقيع_الخط)
    await interaction.followup.send("✅ تم تسطيب الجوال بالكامل وربط كل التطبيقات!", ephemeral=True)

@bot.tree.command(name="المطورين", description="عرض بيانات المطور")
async def dev_cmd(interaction: discord.Interaction):
    embed = discord.Embed(title="💻 عن المطور", description="تمت برمجة هذا النظام المتقدم خصيصاً للمدينة.\n\nالمبرمج:\n**f_arooq004**", color=discord.Color.dark_grey())
    embed.set_footer(text="URG OS | Copyright ©")
    await interaction.response.send_message(embed=embed)

@bot.event
async def on_message(message):
    if message.author.bot or not message.guild: return
    data = query_db("SELECT app_channel, tweet_channel, market_channel, gram_channel, verify_channel, signature FROM settings WHERE guild_id = ?", (message.guild.id,), one=True)
    if data and data[5] and message.channel.id in data[:5] and message.content.strip() != data[5].strip():
        await message.channel.send(data[5])
    await bot.process_commands(message)

@bot.event
async def on_ready():
    bot.add_view(StartPhoneView())
    await bot.add_cog(MainPhoneReceiver(bot))
    await bot.tree.sync()
    print("=========================================")
    print(f"✅ URG OS IS ONLINE! Logged in as {bot.user}")
    print("=========================================")

# ==============================================================================
# 10. التشغيل الآمن عبر بيئة الاستضافة
# ==============================================================================
token = os.getenv("DISCORD_TOKEN")
if token: bot.run(token)
else: print("❌ لم يتم العثور على التوكن في البيئة المستضيفة!")
