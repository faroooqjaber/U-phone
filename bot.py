import discord
from discord.ext import commands
from discord import app_commands, ui
import sqlite3
import os
import re
import random
from datetime import datetime

# ==============================================================================
# 1. إعدادات النيات والتهيئة الأساسية والرموز الثابتة
# ==============================================================================
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents)
DB_PATH = "urg_city_phone.db"

# خط فاصل موحد للاستخدام في تنسيق واجهات النظام (تعديل 2: الخط الفاصل)
LINE_SEPARATOR = "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# ==============================================================================
# 2. محرك قاعدة البيانات المتكامل وإعداد الجداول
# ==============================================================================
def query_db(query, args=(), one=False, commit=False):
    """المحرك المركزي لتنفيذ استعلامات قاعدة البيانات وجلب البيانات أو حفظها"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute(query, args)
        if commit:
            conn.commit()
        res = cursor.fetchone() if one else cursor.fetchall()
        return res
    except Exception as e:
        print(f"[DB ERROR] {e}")
        return None
    finally:
        conn.close()

def setup_database():
    """إنشاء وتهيئة جداول البيانات الأساسية للنظام عند الإقلاع الأول"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # جدول الحسابات والمستخدمين
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        discord_id INTEGER PRIMARY KEY, 
        username TEXT UNIQUE, 
        verified_type TEXT DEFAULT 'none', 
        notifications INTEGER DEFAULT 1, 
        fame_points INTEGER DEFAULT 0
    )''')
    # جدول المتابعات
    c.execute('''CREATE TABLE IF NOT EXISTS follows (
        follower_id INTEGER, 
        followed_id INTEGER, 
        PRIMARY KEY(follower_id, followed_id)
    )''')
    # جدول الإعدادات الشامل
    c.execute('''CREATE TABLE IF NOT EXISTS settings (
        guild_id INTEGER PRIMARY KEY, 
        app_channel INTEGER, 
        tweet_channel INTEGER, 
        market_channel INTEGER, 
        gram_channel INTEGER, 
        verify_channel INTEGER, 
        admin_channel INTEGER,
        admin_role INTEGER, 
        embed_color TEXT DEFAULT '00acee', 
        panel_img TEXT, 
        apps_img TEXT, 
        signature TEXT
    )''')
    # جداول التغريدات والتفاعلات
    c.execute('''CREATE TABLE IF NOT EXISTS tweets (message_id INTEGER PRIMARY KEY, author_id INTEGER, comments_open INTEGER DEFAULT 1)''')
    c.execute('''CREATE TABLE IF NOT EXISTS tweet_likes (message_id INTEGER, user_id INTEGER, PRIMARY KEY(message_id, user_id))''')
    c.execute('''CREATE TABLE IF NOT EXISTS tweet_rts (message_id INTEGER, user_id INTEGER, PRIMARY KEY(message_id, user_id))''')
    conn.commit()
    conn.close()

setup_database()

# ==============================================================================
# 3. الدوال المساعدة والخط التلقائي والإشعارات
# ==============================================================================
async def send_dm_notification(target_id, text, title="🔔 إشعار هاتف U-Phone"):
    """دالة مركزية لإرسال التنبيهات المباشرة للمواطنين عبر الخاص بتنسيق موحد (تعديل 5)"""
    status = query_db("SELECT notifications FROM users WHERE discord_id = ?", (target_id,), one=True)
    if status and status[0] == 0:
        return
    try:
        user = bot.get_user(int(target_id)) or await bot.fetch_user(int(target_id))
        if user:
            # تنسيق إشعار الخاص مع الخط الفاصل والتوقيع الإداري (تعديل 1، 4)
            embed = discord.Embed(title=title, description=f"{text}\n{LINE_SEPARATOR}", color=discord.Color.blue(), timestamp=datetime.utcnow())
            embed.set_footer(text="منظومة الحماية والرقابة | عمر الراشدي - وزير المالية")
            await user.send(embed=embed)
    except:
        pass

async def trigger_signature(guild, channel):
    """دالة تلقائية لطباعة خط التوقيع أسفل المنشورات لزيادة جمالية الروم"""
    setting = query_db("SELECT signature FROM settings WHERE guild_id = ?", (guild.id,), one=True)
    if setting and setting[0]:
        await channel.send(str(setting[0]))

def get_user_badge(discord_id):
    """دالة سريعة لجلب شارة التوثيق الخاصة بالمواطن (💼، 🪙، ✅) من قاعدة البيانات"""
    data = query_db("SELECT verified_type FROM users WHERE discord_id = ?", (discord_id,), one=True)
    if data and data[0] != 'none':
        return f" {data[0]}"
    return ""

# ==============================================================================
# 4. نظام تويتر (النشر، الحسابات، البحث)
# ==============================================================================
class RegisterAccountModal(ui.Modal, title="📝 إنشاء حساب U-Phone"):
    """نافذة تسجيل الحساب الجديد للمواطن والتحقق من سلامة المعايير"""
    username = ui.TextInput(label="اسم المستخدم (اليوزر بدون @)", placeholder="مثال: omar_rashidi", min_length=3, max_length=15)
    
    async def on_submit(self, interaction: discord.Interaction):
        user_input = self.username.value.strip().lower()
        if not re.match(r"^[a-zA-Z0-9_]+$", user_input):
            return await interaction.response.send_message("❌ خطأ: اليوزر يجب أن يحتوي على أحرف وأرقام وأندرسكور فقط!", ephemeral=True)
        try:
            query_db("INSERT INTO users (discord_id, username) VALUES (?, ?)", (interaction.user.id, user_input), commit=True)
            await interaction.response.send_message(f"🎉 تم إنشاء حسابك بنجاح بنظام الهاتف الموحد: `@{user_input}`", ephemeral=True)
        except:
            await interaction.response.send_message("❌ خطأ: اسم المستخدم مستخدم بالفعل في المدينة!", ephemeral=True)

class PostTweetModal(ui.Modal, title="🐦 نشر تغريدة جديدة"):
    """نافذة صياغة ونشر التغريدات العامة وتضمين المرفقات والوسائط"""
    content = ui.TextInput(label="محتوى التغريدة", style=discord.TextStyle.paragraph, max_length=280)
    media = ui.TextInput(label="رابط صورة (اختياري)", required=False)
    
    async def on_submit(self, interaction: discord.Interaction):
        user_data = query_db("SELECT username FROM users WHERE discord_id = ?", (interaction.user.id,), one=True)
        if not user_data:
            return await interaction.response.send_message("❌ ليس لديك حساب هاتف مسجل!", ephemeral=True)
        
        setting = query_db("SELECT tweet_channel FROM settings WHERE guild_id = ?", (interaction.guild.id,), one=True)
        if not setting or not setting[0]:
            return await interaction.response.send_message("❌ روم التغريدات غير مفعّل في النظام.", ephemeral=True)
        
        tweet_channel = interaction.guild.get_channel(setting[0])
        badge = get_user_badge(interaction.user.id)
        
        # تنسيق التغريدة المحدثة (تعديل 4)
        embed = discord.Embed(description=f"{self.content.value}\n{LINE_SEPARATOR}", color=discord.Color.blue(), timestamp=datetime.utcnow())
        embed.set_author(name=f"{interaction.user.display_name} (@{user_data[0]}){badge}", icon_url=interaction.user.display_avatar.url)
        if self.media.value:
            embed.set_image(url=self.media.value.strip())
        embed.set_footer(text="U-Phone | Twitter RP | إدارة: عمر الراشدي")
        embed.add_field(name="📊 التفاعل:", value="❤️ الإعجابات: **0** | 🔁 إعادة النشر: **0**", inline=False)
        
        msg = await tweet_channel.send(embed=embed)
        
        view = ui.View(timeout=None)
        view.add_item(ui.Button(label="❤️ لايك", style=discord.ButtonStyle.secondary, custom_id=f"tw_l_{msg.id}"))
        view.add_item(ui.Button(label="🔁 ريتويت", style=discord.ButtonStyle.secondary, custom_id=f"tw_r_{msg.id}"))
        view.add_item(ui.Button(label="💬 رد", style=discord.ButtonStyle.secondary, custom_id=f"tw_a_{msg.id}"))
        await msg.edit(view=view)
        
        query_db("INSERT INTO tweets (message_id, author_id) VALUES (?, ?)", (msg.id, interaction.user.id), commit=True)
        await interaction.response.send_message("✅ تم نشر التغريدة بنجاح!", ephemeral=True)
        await trigger_signature(interaction.guild, tweet_channel)

class SearchUserModal(ui.Modal, title="🔍 البحث عن مستخدم"):
    """البحث السريع عن السجلات والملفات الشخصية للمواطنين عبر يوزر الحساب"""
    username = ui.TextInput(label="يوزر الحساب المطلوب (بدون @)")
    
    async def on_submit(self, interaction: discord.Interaction):
        target = self.username.value.strip().lower()
        res = query_db("SELECT discord_id, verified_type FROM users WHERE username = ?", (target,), one=True)
        if not res:
            return await interaction.response.send_message("❌ هذا اليوزر غير مسجل بالمدينة.", ephemeral=True)
        
        followers = len(query_db("SELECT follower_id FROM follows WHERE followed_id = ?", (res[0],)))
        badge = f"({res[1]})" if res[1] != 'none' else "شخصي عادي"
        
        embed = discord.Embed(title=f"👤 الملف الشخصي لـ @{target}", description=LINE_SEPARATOR, color=discord.Color.blue())
        embed.add_field(name="نوع الحساب:", value=badge, inline=True)
        embed.add_field(name="المتابعون:", value=str(followers), inline=True)
        embed.set_footer(text="نظام البحث الموحد للمدينة")
        
        view = ui.View(timeout=None).add_item(ui.Button(label="متابعة / إلغاء المتابعة ➕", style=discord.ButtonStyle.primary, custom_id=f"tw_f_{res[0]}"))
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

class TweetReplyModal(ui.Modal, title="💬 إضافة رد على التغريدة"):
    """نظام التعليقات وفتح ثريدات الردود المستقلة أسفل التغريدات لتعزيز الواقعية"""
    reply_text = ui.TextInput(label="اكتب ردك هنا", style=discord.TextStyle.paragraph, max_length=200)
    
    def __init__(self, message: discord.Message):
        super().__init__()
        self.message = message
        
    async def on_submit(self, interaction: discord.Interaction):
        user_data = query_db("SELECT username FROM users WHERE discord_id = ?", (interaction.user.id,), one=True)
        if not user_data:
            return await interaction.response.send_message("❌ يجب تسجيل حساب أولاً!", ephemeral=True)
        
        thread = self.message.thread or await self.message.create_thread(name="ردود التغريدة", auto_archive_duration=60)
        badge = get_user_badge(interaction.user.id)
        
        embed = discord.Embed(description=f"{self.reply_text.value}\n{LINE_SEPARATOR}", color=discord.Color.light_grey(), timestamp=datetime.utcnow())
        embed.set_author(name=f"رد من @{user_data[0]}{badge}", icon_url=interaction.user.display_avatar.url)
        await thread.send(embed=embed)
        await interaction.response.send_message("✅ تم إضافة ردك بنجاح في الثريد!", ephemeral=True)

# ==============================================================================
# 5. نظام تقديم العضوية والتوثيقات الثلاثة
# ==============================================================================
class MembershipTypeSelect(ui.Select):
    """قائمة منسدلة لاختيار نوع التوثيق المطلوب (حكومي، تجاري، مشاهير)"""
    def __init__(self):
        options = [
            discord.SelectOption(label="حساب حكومي / رسمي", value="💼", description="طلب توثيق رسمي للدوائر والموظفين الحكوميين", emoji="💼"),
            discord.SelectOption(label="حساب تجاري", value="🪙", description="طلب توثيق للشركات، المصانع والمحلات التجارية", emoji="🪙"),
            discord.SelectOption(label="حساب موثق للمشاهير", value="✅", description="طلب شارة التحقق الزرقاء للشخصيات المعروفة", emoji="✅")
        ]
        super().__init__(placeholder="اختر نوع التوثيق والعضوية...", options=options, custom_id="member_type_slct")

    async def callback(self, interaction: discord.Interaction):
        chosen_type = self.values[0]
        await interaction.response.send_modal(MembershipApplyModal(chosen_type))

class MembershipApplyModal(ui.Modal):
    """نافذة جمع بيانات وثائق طلب التوثيق من المستخدم وإرسالها لمراجعة الإدارة"""
    username = ui.TextInput(label="يوزر الحساب التأكيدي")
    reason = ui.TextInput(label="سبب طلب التوثيق / الإثباتات والمنصب", style=discord.TextStyle.paragraph)
    
    def __init__(self, badge_emoji):
        super().__init__(title="📝 استمارة طلب العضوية والتوثيق")
        self.badge_emoji = badge_emoji
        
    async def on_submit(self, interaction: discord.Interaction):
        user_check = query_db("SELECT username FROM users WHERE discord_id = ?", (interaction.user.id,), one=True)
        if not user_check:
            return await interaction.response.send_message("❌ يجب إنشاء حساب هاتف أولاً قبل طلب التوثيق!", ephemeral=True)
            
        settings = query_db("SELECT verify_channel FROM settings WHERE guild_id = ?", (interaction.guild.id,), one=True)
        if not settings or not settings[0]:
            return await interaction.response.send_message("❌ روم استقبال الطلبات غير مهيأ في السيرفر.", ephemeral=True)
            
        v_channel = interaction.guild.get_channel(settings[0])
        type_str = "حكومي 💼" if self.badge_emoji == "💼" else "تجاري 🪙" if self.badge_emoji == "🪙" else "مشاهير ✅"
        
        embed = discord.Embed(title="📥 طلب توثيق وعضوية جديد", color=discord.Color.orange(), timestamp=datetime.utcnow())
        embed.add_field(name="صاحب الطلب:", value=interaction.user.mention, inline=True)
        embed.add_field(name="يوزر الحساب:", value=f"`@{self.username.value}`", inline=True)
        embed.add_field(name="النوع المطلوب:", value=type_str, inline=True)
        embed.add_field(name=LINE_SEPARATOR, value="**التفاصيل والأسباب:**\n" + self.reason.value, inline=False)
        embed.set_footer(text="نظام إدارة المدينة | إشراف: عمر الراشدي - وزير المالية")
        
        view = ui.View(timeout=None)
        view.add_item(ui.Button(label="قبول التوثيق ✅", style=discord.ButtonStyle.success, custom_id=f"vf_a_{interaction.user.id}_{self.badge_emoji}"))
        view.add_item(ui.Button(label="رفض الطلب ❌", style=discord.ButtonStyle.danger, custom_id=f"vf_r_{interaction.user.id}"))
        
        await v_channel.send(embed=embed, view=view)
        await interaction.response.send_message("✅ تم إرسال طلب توثيقك للإدارة بنجاح وجاري مراجعته!", ephemeral=True)

# ==============================================================================
# 6. نظام شات أب والرسائل المجهولة
# ==============================================================================
class ChatSendMessageModal(ui.Modal, title="💬 شات أب - إرسال رسالة"):
    """نظام إرسال الرسائل المباشرة والمراسلات الفورية الآمنة بين مواطني المدينة"""
    target = ui.TextInput(label="يوزر المستهدف (بدون @)")
    content = ui.TextInput(label="نص الرسالة", style=discord.TextStyle.paragraph)
    
    async def on_submit(self, interaction: discord.Interaction):
        sender = query_db("SELECT username FROM users WHERE discord_id = ?", (interaction.user.id,), one=True)
        if not sender:
            return await interaction.response.send_message("❌ لا تملك حساب هاتف!", ephemeral=True)
        
        target_res = query_db("SELECT discord_id FROM users WHERE username = ?", (self.target.value.strip().lower(),), one=True)
        if not target_res:
            return await interaction.response.send_message("❌ اسم المستخدم غير مسجل بالمنظومة.", ephemeral=True)
            
        badge = get_user_badge(interaction.user.id)
        
        embed = discord.Embed(title="💬 شات أب - رسالة واردة", description=f"{LINE_SEPARATOR}\n{self.content.value}\n{LINE_SEPARATOR}", color=discord.Color.green())
        embed.set_author(name=f"من: @{sender[0]}{badge}", icon_url=interaction.user.display_avatar.url)
        embed.set_footer(text="اضغط على زر الرد السريع بالأسفل للإجابة")
        
        view = ui.View(timeout=None).add_item(ui.Button(label="رد سريع ↩️", style=discord.ButtonStyle.success, custom_id=f"ch_msg_{interaction.user.id}_{sender[0]}"))
        try:
            t_user = bot.get_user(target_res[0]) or await bot.fetch_user(target_res[0])
            await t_user.send(embed=embed, view=view)
            await interaction.response.send_message("✅ تم تسليم الرسالة بنجاح عبر شات أب!", ephemeral=True)
        except:
            await interaction.response.send_message("❌ فشل الإرسال، المستهدف يغلق خاص الحساب.", ephemeral=True)

class AnonymousMailModal(ui.Modal, title="🥷 رسالة سرية مشفرة"):
    """منظومة توجيه رسائل مجهولة بالكامل لحماية شات الرول بلاي المظلم بالمدينة"""
    target = ui.TextInput(label="يوزر الضحية المستهدفة")
    content = ui.TextInput(label="نص الرسالة السرية", style=discord.TextStyle.paragraph)
    
    async def on_submit(self, interaction: discord.Interaction):
        target_res = query_db("SELECT discord_id FROM users WHERE username = ?", (self.target.value.strip().lower(),), one=True)
        if not target_res:
            return await interaction.response.send_message("❌ اليوزر غير متواجد بالمدينة.", ephemeral=True)
            
        embed = discord.Embed(title="⚠️ إشعار من جهة مشفرة ومجهولة", description=f"```\n{self.content.value}\n
```", color=discord.Color.from_rgb(10, 10, 10))
        embed.set_footer(text="تم تشفير البيانات - مصدر مجهول الهوية | نظام الحماية مفعل")
        try:
            t_user = bot.get_user(target_res[0]) or await bot.fetch_user(target_res[0])
            await t_user.send(embed=embed)
            await interaction.response.send_message("🥷 تمت عملية الإرسال بنجاح وتعمية الهوية المرجعية.", ephemeral=True)
        except:
            await interaction.response.send_message("❌ فشل الإرسال، المستهدف يغلق الخاص.", ephemeral=True)

class QuickReplyReceiverModal(ui.Modal, title="↩️ إرسال رد سريع"):
    """نافذة الرد السريع الفوري على مراسلات شات أب الواردة عبر الخاص"""
    content = ui.TextInput(label="الرسالة", style=discord.TextStyle.paragraph)
    
    def __init__(self, target_id, target_name):
        super().__init__()
        self.target_id, self.target_name = int(target_id), target_name
        
    async def on_submit(self, interaction: discord.Interaction):
        sender = query_db("SELECT username FROM users WHERE discord_id = ?", (interaction.user.id,), one=True)
        badge = get_user_badge(interaction.user.id)
        
        embed = discord.Embed(title="💬 شات أب - رد جديد", description=f"{LINE_SEPARATOR}\n{self.content.value}\n{LINE_SEPARATOR}", color=discord.Color.green())
        embed.set_author(name=f"من: @{sender[0]}{badge}", icon_url=interaction.user.display_avatar.url)
        view = ui.View(timeout=None).add_item(ui.Button(label="رد سريع ↩️", style=discord.ButtonStyle.success, custom_id=f"ch_msg_{interaction.user.id}_{sender[0]}"))
        try:
            user = bot.get_user(self.target_id) or await bot.fetch_user(self.target_id)
            await user.send(embed=embed, view=view)
            await interaction.response.send_message("✅ تم إرسال ردك السريع بنجاح!", ephemeral=True)
        except:
            await interaction.response.send_message("❌ تعذر تسليم الرد، الخاص مغلق.", ephemeral=True)

# ==============================================================================
# 7. نظام أسواق المدينة والتذاكر (Tickets) الفورية للبيع والشراء
# ==============================================================================
class PostMarketAdModal(ui.Modal):
    """لوحة صياغة إعلانات البيع والشراء في الأسواق القانونية أو الـ DarkWeb"""
    title_ad = ui.TextInput(label="عنوان السلعة / الخدمة")
    desc_ad = ui.TextInput(label="تفاصيل الإعلان والسعر والتواصل الكلي", style=discord.TextStyle.paragraph)
    img_ad = ui.TextInput(label="رابط الصورة المرفقة (اختياري)", required=False)
    
    def __init__(self, is_dark_web: bool):
        super().__init__(title="☠️ سوق الإنترنت المظلم" if is_dark_web else "🛒 سوق إعلانات المدينة")
        self.is_dark_web = is_dark_web
        
    async def on_submit(self, interaction: discord.Interaction):
        user_check = query_db("SELECT username FROM users WHERE discord_id = ?", (interaction.user.id,), one=True)
        if not user_check:
            return await interaction.response.send_message("❌ سجل حساب بالهاتف أولاً!", ephemeral=True)
            
        settings = query_db("SELECT market_channel FROM settings WHERE guild_id = ?", (interaction.guild.id,), one=True)
        if not settings or not settings[0]:
            return await interaction.response.send_message("❌ روم الأسواق غير مهيأ بالسيرفر.", ephemeral=True)
            
        m_channel = interaction.guild.get_channel(settings[0])
        
        embed = discord.Embed(title=self.title_ad.value, description=f"{self.desc_ad.value}\n{LINE_SEPARATOR}", color=discord.Color.purple() if self.is_dark_web else discord.Color.gold(), timestamp=datetime.utcnow())
        
        if self.img_ad.value:
            embed.set_image(url=self.img_ad.value.strip())
            
        view = ui.View(timeout=None)
        if self.is_dark_web:
            embed.set_author(name="🥷 تاجر مجهول الهوية (DarkWeb)")
            embed.set_footer(text="نظام التداول السري | لا تحاول كشف الهوية")
            view.add_item(ui.Button(label="شراء سري (فتح تيكت مجهول) 💼", style=discord.ButtonStyle.danger, custom_id=f"mk_t_dark_{interaction.user.id}"))
        else:
            badge = get_user_badge(interaction.user.id)
            embed.set_author(name=f"معلن: @{user_check[0]}{badge}", icon_url=interaction.user.display_avatar.url)
            embed.set_footer(text="سوق المدينة المعتمد | إشراف: عمر الراشدي - وزير المالية")
            view.add_item(ui.Button(label="تواصل مع المعلن (فتح تيكت) 📞", style=discord.ButtonStyle.primary, custom_id=f"mk_t_legal_{interaction.user.id}_{user_check[0]}"))
            
        await m_channel.send(embed=embed, view=view)
        await interaction.response.send_message("✅ تم نشر إعلانك التجاري بنجاح!", ephemeral=True)
        await trigger_signature(interaction.guild, m_channel)

# ==============================================================================
# 8. نظام ألعاب الهاتف الموسع (حجرة ورقة مقص، إكس أو، تخمين)
# ==============================================================================
class RockPaperScissorsView(ui.View):
    """لعبة حجرة ورقة مقص التفاعلية التنافسية ضد البوت الذكي"""
    def __init__(self):
        super().__init__(timeout=60)
        
    @ui.button(label="🪨 حجرة", style=discord.ButtonStyle.primary, custom_id="rps_r")
    async def rock(self, interaction: discord.Interaction, button: ui.Button):
        await self.process_game(interaction, "حجرة")
        
    @ui.button(label="📄 ورقة", style=discord.ButtonStyle.success, custom_id="rps_p")
    async def paper(self, interaction: discord.Interaction, button: ui.Button):
        await self.process_game(interaction, "ورقة")
        
    @ui.button(label="✂️ مقص", style=discord.ButtonStyle.danger, custom_id="rps_s")
    async def scissors(self, interaction: discord.Interaction, button: ui.Button):
        await self.process_game(interaction, "مقص")
        
    async def process_game(self, interaction: discord.Interaction, user_choice):
        bot_choice = random.choice(["حجرة", "ورقة", "مقص"])
        if user_choice == bot_choice:
            res = f"🤝 تعادل! كليكما اختار **{user_choice}**."
        elif (user_choice == "حجرة" and bot_choice == "مقص") or (user_choice == "ورقة" and bot_choice == "حجرة") or (user_choice == "مقص" and bot_choice == "ورقة"):
            res = f"🎉 فزت على البوت! أنت اخترت **{user_choice}** والبوت اختار **{bot_choice}**."
        else:
            res = f"🤖 خسرنا! البوت اختار **{bot_choice}** وأنت اخترت **{user_choice}**."
        await interaction.response.edit_message(content=res, view=None)

class TicTacToeButton(ui.Button):
    """أزرار لوحة ومربعات لعبة X-O لتمثيل الخانات البرمجية"""
    def __init__(self, x: int, y: int):
        super().__init__(style=discord.ButtonStyle.secondary, label="\u200b", row=y)
        self.x = x
        self.y = y

    async def callback(self, interaction: discord.Interaction):
        assert self.view is not None
        view: TicTacToeView = self.view
        if interaction.user.id != view.player_id:
            return await interaction.response.send_message("❌ هذه اللعبة ليست لك!", ephemeral=True)
            
        if view.board[self.y][self.x] != 0:
            return await interaction.response.send_message("❌ هذه الخانة محجوزة!", ephemeral=True)

        view.board[self.y][self.x] = 1
        self.label = "❌"
        self.style = discord.ButtonStyle.danger
        self.disabled = True

        if view.check_win(1):
            await interaction.response.edit_message(content="🎉 مبروك! لقد هزمت البوت في لعبة X-O!", view=view)
            view.stop()
            return
            
        if view.is_full():
            await interaction.response.edit_message(content="🤝 تعادل رائع! لا يوجد خانات متبقية.", view=view)
            view.stop()
            return

        view.bot_move()
        if view.check_win(2):
            await interaction.response.edit_message(content="🤖 ذكاء اصطناعي! البوت فاز عليك هذه المرة.", view=view)
            view.stop()
            return
            
        if view.is_full():
            await interaction.response.edit_message(content="🤝 تعادل رائع!", view=view)
            view.stop()
            return

        await interaction.response.edit_message(view=view)

class TicTacToeView(ui.View):
    """محرك إدارة لعبة X-O والذكاء الاصطناعي للبوت المنافس"""
    def __init__(self, player_id):
        super().__init__(timeout=120)
        self.player_id = player_id
        self.board = [[0, 0, 0], [0, 0, 0], [0, 0, 0]]
        for y in range(3):
            for x in range(3):
                self.add_item(TicTacToeButton(x, y))

    def bot_move(self):
        empty_slots = [(x, y) for y in range(3) for x in range(3) if self.board[y][x] == 0]
        if empty_slots:
            x, y = random.choice(empty_slots)
            self.board[y][x] = 2
            for item in self.children:
                if isinstance(item, TicTacToeButton) and item.x == x and item.y == y:
                    item.label = "⭕"
                    item.style = discord.ButtonStyle.success
                    item.disabled = True

    def check_win(self, p):
        b = self.board
        for i in range(3):
            if b[i][0] == b[i][1] == b[i][2] == p or b[0][i] == b[1][i] == b[2][i] == p:
                return True
        if b[0][0] == b[1][1] == b[2][2] == p or b[0][2] == b[1][1] == b[2][0] == p:
            return True
        return False

    def is_full(self):
        return all(self.board[y][x] != 0 for y in range(3) for x in range(3))

class GuessNumberModal(ui.Modal, title="🔢 لعبة تخمين الرقم الذكي"):
    """لعبة تحدي الذكاء لتخمين الرقم العشوائي السري المخفي"""
    guess = ui.TextInput(label="أدخل رقمك المختار من 1 إلى 20", min_length=1, max_length=2)
    async def on_submit(self, interaction: discord.Interaction):
        secret = random.randint(1, 20)
        try:
            val = int(self.guess.value)
        except:
            return await interaction.response.send_message("❌ أرقام صحيحة فقط!", ephemeral=True)
            
        if val == secret:
            await interaction.response.send_message(f"🎉 حدس عبقري! الرقم الصحيح هو فعلاً {secret}.", ephemeral=True)
        else:
            await interaction.response.send_message(f"🤖 حظاً أوفر! تخمينك خاطئ، الرقم الصحيح المختار كان {secret}.", ephemeral=True)

# ==============================================================================
# 9. نظام واجهات القوائم المنسدلة الفرعية والأساسية للهاتف (Callback Engine)
# ==============================================================================
class AppSubMenuSelect(ui.Select):
    """محرك إدارة ومعالجة التطبيقات الفرعية المنبثقة من قائمة الهاتف"""
    def __init__(self, app_type):
        options = []
        if app_type == "tw":
            options = [
                discord.SelectOption(label="كتابة وتثبيت تغريدة", value="tw_w", emoji="📝"),
                discord.SelectOption(label="الملف الشخصي والحالة", value="tw_p", emoji="👤"),
                discord.SelectOption(label="البحث عن حساب باليوزر", value="tw_s", emoji="🔍")
            ]
        elif app_type == "ch":
            options = [discord.SelectOption(label="بدء محادثة في شات أب", value="ch_s", emoji="💬")]
        elif app_type == "sh":
            options = [discord.SelectOption(label="إرسال رسالة مجهولة مشفرة", value="sh_s", emoji="🥷")]
        elif app_type == "mk":
            options = [
                discord.SelectOption(label="إعلان بيع/شراء قانوني", value="mk_l", emoji="🛒"),
                discord.SelectOption(label="عرض في السوق المظلم", value="mk_d", emoji="☠️")
            ]
        elif app_type == "gr":
            options = [discord.SelectOption(label="نشر ستوري يوميات يو غرام", value="gr_p", emoji="📸")]
        elif app_type == "pl":
            options = [
                discord.SelectOption(label="تخمين الرقم (1-20)", value="pl_g", emoji="🔢"),
                discord.SelectOption(label="حجرة ورقة مقص", value="pl_r", emoji="✂️"),
                discord.SelectOption(label="لعبة X - O الذكية", value="pl_x", emoji="🎮")
            ]
        elif app_type == "id":
            options = [
                discord.SelectOption(label="إنشاء حساب هاتف جديد", value="id_n", emoji="📝"),
                discord.SelectOption(label="تقديم طلب عضوية وتوثيق", value="id_v", emoji="🏅")
            ]

        options.append(discord.SelectOption(label="العودة للشاشة الرئيسية", value="b_home", emoji="🔙"))
        super().__init__(placeholder="اختر الإجراء المطلوب تفعيله...", options=options, custom_id=f"sub_{app_type}")

    async def callback(self, interaction: discord.Interaction):
        v = self.values[0]
        if v == "b_home":
            s = query_db("SELECT apps_img FROM settings WHERE guild_id = ?", (interaction.guild.id,), one=True)
            em = discord.Embed(title="📱 قائمة تطبيقات الهاتف الرئيسية", color=discord.Color.from_rgb(40,40,40))
            if s and s[0]: em.set_image(url=s[0])
            em.set_footer(text="نظام إدارة المدينة | إشراف: عمر الراشدي - وزير المالية")
            return await interaction.response.edit_message(embed=em, view=ui.View(timeout=None).add_item(MainAppListSelect()))

        if v == "id_n": await interaction.response.send_modal(RegisterAccountModal())
        elif v == "id_v":
            await interaction.response.edit_message(content="قم باختيار نوع فئة التوثيق الموجهة من القائمة:", embed=None, view=ui.View(timeout=None).add_item(MembershipTypeSelect()))
        elif v == "tw_w": await interaction.response.send_modal(PostTweetModal())
        elif v == "tw_s": await interaction.response.send_modal(SearchUserModal())
        elif v == "tw_p":
            d = query_db("SELECT username, fame_points FROM users WHERE discord_id = ?", (interaction.user.id,), one=True)
            if not d: return await interaction.response.send_message("❌ لا تملك حساباً بعد!", ephemeral=True)
            b = get_user_badge(interaction.user.id)
            f = len(query_db("SELECT follower_id FROM follows WHERE followed_id = ?", (interaction.user.id,)))
            
            em = discord.Embed(title=f"👤 ملف حسابك الحالي {b}", description=f"يوزر الحساب: `@{d[0]}`\nعدد المتابعين الفعليين: **{f}**\nنقاط السمعة والشهرة: **{d[1]}**\n{LINE_SEPARATOR}", color=discord.Color.blue())
            await interaction.response.send_message(embed=em, ephemeral=True)
        elif v == "ch_s": await interaction.response.send_modal(ChatSendMessageModal())
        elif v == "sh_s": await interaction.response.send_modal(AnonymousMailModal())
        elif v == "mk_l": await interaction.response.send_modal(PostMarketAdModal(False))
        elif v == "mk_d": await interaction.response.send_modal(PostMarketAdModal(True))
        elif v == "pl_g": await interaction.response.send_modal(GuessNumberModal())
        elif v == "pl_r":
            await interaction.response.send_message("🪨 اختر حركتك الهجومية ضد البوت:", view=RockPaperScissorsView(), ephemeral=True)
        elif v == "pl_x":
            await interaction.response.send_message("❌ لعبة X-O مع البوت (ابدأ بالضغط على أي مربع):", view=TicTacToeView(interaction.user.id), ephemeral=True)
        elif v == "gr_p":
            await interaction.response.send_modal(GramPostStoryModal())

class MainAppListSelect(ui.Select):
    """قائمة استعراض وفهرسة تطبيقات الجوال الرئيسية الشاملة للمواطن"""
    def __init__(self):
        options = [
            discord.SelectOption(label="تويتر المدينة العائلية", value="m_tw", emoji="🐦"),
            discord.SelectOption(label="تطبيق المراسلات شات أب", value="m_ch", emoji="💬"),
            discord.SelectOption(label="خدمة الرسائل المشفرة المجهولة", value="m_sh", emoji="🥷"),
            discord.SelectOption(label="سوق المركبات والسلع العام", value="m_mk", emoji="🛒"),
            discord.SelectOption(label="يوميات يو غرام الحية", value="m_gr", emoji="📸"),
            discord.SelectOption(label="مركز U-Play للألعاب الترفيهية", value="m_pl", emoji="🎮"),
            discord.SelectOption(label="إدارة الهوية المدنية والتوثيقات", value="m_id", emoji="🛂")
        ]
        super().__init__(placeholder="📱 اضغط هنا لفتح واجهة التطبيقات...", options=options, custom_id="main_os_select")

    async def callback(self, interaction: discord.Interaction):
        app_code = self.values[0].split('_')[1]
        view = ui.View(timeout=None).add_item(AppSubMenuSelect(app_code))
        embed = discord.Embed(title=f"📱 نظام الجوال - تشغيل تطبيق [{app_code.upper()}]", description="برجاء تحديد المهمة المطلوبة من القائمة المنسدلة بالأسفل للحساب:", color=discord.Color.dark_grey())
        embed.set_footer(text="نظام إدارة المدينة | إشراف: عمر الراشدي")
        await interaction.response.edit_message(embed=embed, view=view)

class BootPhoneMasterView(ui.View):
    """زر الإقلاع والولوج الرئيسي لبوابة الهاتف الذكي"""
    def __init__(self):
        super().__init__(timeout=None)
        
    @ui.button(label="فتح تشغيل الهاتف الذكي 📱", style=discord.ButtonStyle.primary, custom_id="master_boot_btn")
    async def boot_phone(self, interaction: discord.Interaction, button: ui.Button):
        img = query_db("SELECT apps_img FROM settings WHERE guild_id = ?", (interaction.guild.id,), one=True)
        embed = discord.Embed(title="📱 شاشة التطبيقات ونظام التشغيل العام", color=discord.Color.from_rgb(30, 30, 30))
        if img and img[0]:
            embed.set_image(url=img[0])
        embed.set_footer(text="نظام إدارة المدينة | إشراف: عمر الراشدي - وزير المالية")
        view = ui.View(timeout=None).add_item(MainAppListSelect())
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

class GramPostStoryModal(ui.Modal, title="📸 يو غرام - نشر يوميات جديدة"):
    """نظام نشر اليوميات والقصص المصورة الحية للمواطنين عبر منصة يو غرام"""
    caption = ui.TextInput(label="التعليق المكتوب على الستوري", max_length=150)
    image_url = ui.TextInput(label="رابط الصورة المباشر")
    
    async def on_submit(self, interaction: discord.Interaction):
        user_data = query_db("SELECT username FROM users WHERE discord_id = ?", (interaction.user.id,), one=True)
        if not user_data: return await interaction.response.send_message("❌ غير مسجل بالهاتف!", ephemeral=True)
        
        settings = query_db("SELECT gram_channel FROM settings WHERE guild_id = ?", (interaction.guild.id,), one=True)
        if not settings or not settings[0]: return await interaction.response.send_message("❌ روم اليوميات معطل.", ephemeral=True)
        
        g_channel = interaction.guild.get_channel(settings[0])
        badge = get_user_badge(interaction.user.id)
        
        embed = discord.Embed(description=f"{self.caption.value}\n{LINE_SEPARATOR}", color=discord.Color.purple(), timestamp=datetime.utcnow())
        embed.set_author(name=f"ستوري يوميات: @{user_data[0]}{badge}", icon_url=interaction.user.display_avatar.url)
        embed.set_image(url=self.image_url.value.strip())
        
        await g_channel.send(embed=embed)
        await interaction.response.send_message("✅ تم نشر يومياتك الحية بنجاح على يو غرام!", ephemeral=True)
        await trigger_signature(interaction.guild, g_channel)

# ==============================================================================
# 10. لوحة التحكم الإدارية المتقدمة (روم الإدارة والخيارات)
# ==============================================================================
class AdminDashboardDropdown(ui.Select):
    """لوحة التحكم السرية لإدارة وتطهير حسابات اللاعبين وإدارة السيستم"""
    def __init__(self):
        options = [
            discord.SelectOption(label="تعديل يوزر مستخدم إدارياً", value="adm_edit", emoji="✍️"),
            discord.SelectOption(label="تصفير وحذف حساب كلياً", value="adm_del", emoji="🗑️"),
            discord.SelectOption(label="إعادة خيارات اللوحة (الاختيار)", value="adm_reset", emoji="🔄")
        ]
        super().__init__(placeholder="🛠️ لوحة تحكم الإدارة السرية للأنظمة...", options=options, custom_id="admin_dash_select")

    async def callback(self, interaction: discord.Interaction):
        val = self.values[0]
        if val == "adm_reset":
            await interaction.response.edit_message(content="🔄 تم إعادة تعيين مصفوفة الاختيارات للوحة التحكم الإدارية بنجاح بنظام الهاتف.")
        elif val == "adm_edit":
            await interaction.response.send_modal(AdminEditUserModal())
        elif val == "adm_del":
            await interaction.response.send_modal(AdminDeleteUserModal())

class AdminEditUserModal(ui.Modal, title="🛠️ تعديل يوزر حساب مواطن"):
    """تعديل وتجاوز يوزر حساب المواطن إدارياً لأسباب رول بلاي أو تنظيمية"""
    target_id = ui.TextInput(label="الآيدي الرقمي للمواطن (Discord ID)")
    new_username = ui.TextInput(label="اليوزر الجديد البديل")
    
    async def on_submit(self, interaction: discord.Interaction):
        try:
            query_db("UPDATE users SET username = ? WHERE discord_id = ?", (self.new_username.value.strip().lower(), int(self.target_id.value)), commit=True)
            await interaction.response.send_message("✅ تم تعديل يوزر المواطن بنجاح تام داخل قاعدة البيانات.", ephemeral=True)
        except:
            await interaction.response.send_message("❌ خطأ بالبيانات أو اسم المستخدم مكرر مسبقاً.", ephemeral=True)

class AdminDeleteUserModal(ui.Modal, title="🗑️ حذف وتصفير بيانات مواطن"):
    """شطب وحذف حساب المواطن بالكامل وتصفير سجلاته من قاعدة البيانات"""
    target_id = ui.TextInput(label="الآيدي الرقمي للمواطن (Discord ID)")
    
    async def on_submit(self, interaction: discord.Interaction):
        query_db("DELETE FROM users WHERE discord_id = ?", (int(self.target_id.value),), commit=True)
        await interaction.response.send_message("🗑️ تم تصفير وحذف حساب المواطن بشكل نهائي من خوادم السيرفر.", ephemeral=True)

class PersistentAdminPanelView(ui.View):
    """منظومة عرض وتثبيت واجهة اللوحة الإدارية لوزارة المالية"""
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(AdminDashboardDropdown())

# ==============================================================================
# 11. المعالج الشامل والمستمع المركزي لكافة الأزرار الثابتة (لايكات، ريتويت، تيكت)
# ==============================================================================
class GlobalInteractionsCog(commands.Cog):
    """الكوج المركزي المشرف والملتقط الدائم للتفاعلات ومكونات الأزرار بالأقسام"""
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        if interaction.type != discord.InteractionType.component: return
        cid = interaction.data.get('custom_id', '')
        if not cid: return

        # إدارة تفاعل التويتر (لايك و ريتويت)
        if cid.startswith('tw_l_') or cid.startswith('tw_r_'):
            msg_id = int(cid.split('_')[2])
            is_like = "l" in cid
            author_data = query_db("SELECT author_id FROM tweets WHERE message_id = ?", (msg_id,), one=True)
            
            if is_like:
                check = query_db("SELECT 1 FROM tweet_likes WHERE message_id = ? AND user_id = ?", (msg_id, interaction.user.id), one=True)
                if check: 
                    query_db("DELETE FROM tweet_likes WHERE message_id = ? AND user_id = ?", (msg_id, interaction.user.id), commit=True)
                else: 
                    query_db("INSERT INTO tweet_likes (message_id, user_id) VALUES (?, ?)", (msg_id, interaction.user.id), commit=True)
                    if author_data: await send_dm_notification(author_data[0], f"❤️ أحدهم معجب بك! قام المواطن `{interaction.user.display_name}` بالإعجاب بتغريدتك الموثقة.")
            else:
                check = query_db("SELECT 1 FROM tweet_rts WHERE message_id = ? AND user_id = ?", (msg_id, interaction.user.id), one=True)
                if check: 
                    query_db("DELETE FROM tweet_rts WHERE message_id = ? AND user_id = ?", (msg_id, interaction.user.id), commit=True)
                else: 
                    query_db("INSERT INTO tweet_rts (message_id, user_id) VALUES (?, ?)", (msg_id, interaction.user.id), commit=True)
                    if author_data: await send_dm_notification(author_data[0], f"🔁 انتبه! قام المواطن `{interaction.user.display_name}` بإعادة نشر (ريتويت) لتغريدتك بالمدينة.")

            likes = query_db("SELECT COUNT(*) FROM tweet_likes WHERE message_id = ?", (msg_id,), one=True)[0]
            rts = query_db("SELECT COUNT(*) FROM tweet_rts WHERE message_id = ?", (msg_id,), one=True)[0]
            
            embed = interaction.message.embeds[0]
            embed.set_field_at(0, name="📊 التفاعل:", value=f"❤️ الإعجابات: **{likes}** | 🔁 إعادة النشر: **{rts}**", inline=False)
            await interaction.response.edit_message(embed=embed)

        elif cid.startswith('tw_a_'):
            msg_id = int(cid.split('_')[2])
            await interaction.response.send_modal(TweetReplyModal(interaction.message))

        elif cid.startswith('tw_f_'):
            target_id = int(cid.split('_')[2])
            if interaction.user.id == target_id: return await interaction.response.send_message("❌ لا يمكنك متابعة نفسك!", ephemeral=True)
            check = query_db("SELECT 1 FROM follows WHERE follower_id = ? AND followed_id = ?", (interaction.user.id, target_id), one=True)
            if check:
                query_db("DELETE FROM follows WHERE follower_id = ? AND followed_id = ?", (interaction.user.id, target_id), commit=True)
                await interaction.response.send_message("❌ تم إلغاء متابعة الحساب.", ephemeral=True)
            else:
                query_db("INSERT INTO follows (follower_id, followed_id) VALUES (?, ?)", (interaction.user.id, target_id), commit=True)
                await interaction.response.send_message("✅ تمت متابعة الحساب التجاري بنجاح!", ephemeral=True)

        # إدارة تذاكر الأسواق القانونية والإنترنت المظلم
        elif cid.startswith('mk_t_'):
            parts = cid.split('_')
            is_dark = "dark" in cid
            seller_id = int(parts[3])
            
            thread = await interaction.channel.create_thread(name=f"تذكرة-صفقة-{interaction.user.name}", auto_archive_duration=60)
            await interaction.response.send_message(f"✅ تم إنشاء غرفة تيكت التواصل الفورية والسرية بنجاح: {thread.mention}", ephemeral=True)
            
            if is_dark:
                warn_embed = discord.Embed(
                    title="☠️ تحذير إداري وقانوني صارم للبائعين والمشترين المجهولين", 
                    description=f"**استخدام اسم البائع أو محاولة كشف هويته في الرول بلاي (IC) أمر ممنوع تماماً!**\nهو يتحدث معك بصفة مشفرة ومجهولة الهوية بالكامل.\nحتى وإن قمت بمعرفة يوزره الحقيقي بطريقة غير شرعية، استخدامك له يعرضك للمساءلة.\n{LINE_SEPARATOR}", 
                    color=discord.Color.red()
                )
                warn_embed.set_footer(text="نظام المدينة المظلم | إشراف: عمر الراشدي")
                await thread.send(embed=warn_embed)
            else:
                await thread.send(f"📞 أهلاً بك {interaction.user.mention}، لقد فتحت تيكت تواصل لشراء سلعة المواطن صاحب الآيدي: <@{seller_id}>.")

        # معالجة الشات السريع والردود
        elif cid.startswith('ch_msg_'):
            parts = cid.split('_')
            await interaction.response.send_modal(QuickReplyReceiverModal(parts[2], parts[3]))

        # إدارة قبول ورفض طلبات التوثيق من الإدارة
        elif cid.startswith('vf_a_') or cid.startswith('vf_r_'):
            settings = query_db("SELECT admin_role FROM settings WHERE guild_id = ?", (interaction.guild.id,), one=True)
            role = interaction.guild.get_role(settings[0]) if settings else None
            if not role or role not in interaction.user.roles:
                return await interaction.response.send_message("❌ لا تملك رتبة مسؤول إدارة الهاتف للتحكم بالطلبات!", ephemeral=True)
                
            parts = cid.split('_')
            target_id = int(parts[2])
            
            embed = interaction.message.embeds[0]
            if "_a_" in cid:
                emoji_badge = parts[3]
                query_db("UPDATE users SET verified_type = ? WHERE discord_id = ?", (emoji_badge, target_id), commit=True)
                embed.title = "✅ تم قبول وثيقة طلب العضوية بنجاح"
                embed.color = discord.Color.green()
                embed.add_field(name="مدقق الطلب:", value=f"الوزير عمر الراشدي ({interaction.user.mention})", inline=False)
                await send_dm_notification(target_id, f"🎉 مبروك! وافقت الإدارة على طلب توثيق حسابك بالشارة {emoji_badge}.")
            else:
                embed.title = "❌ تم رفض وثيقة العضوية من قبل الإدارة"
                embed.color = discord.Color.red()
                embed.add_field(name="مدقق الطلب:", value=f"الوزير عمر الراشدي ({interaction.user.mention})", inline=False)
                await send_dm_notification(target_id, "❌ نأسف، لقد تم رفض طلب توثيق حسابك من قبل إدارة الأنظمة.")
                
            await interaction.response.edit_message(embed=embed, view=None)

# ==============================================================================
# 12. أوامر السلاش الرئيسية (التسطيب ومزامنة الشاشات الثابتة)
# ==============================================================================
@bot.tree.command(name="تسطيب_الجوال", description="إعداد وتهيئة منظومة الجوال بالكامل وربط لوحات الإدارة")
@app_commands.checks.has_permissions(administrator=True)
async def setup_phone_system(interaction: discord.Interaction, 
                             روم_الجوال: discord.TextChannel, 
                             روم_التغريدات: discord.TextChannel,
                             روم_السوق: discord.TextChannel, 
                             روم_اليوميات: discord.TextChannel,
                             روم_التقديمات: discord.TextChannel, 
                             روم_الادارة: discord.TextChannel,
                             رتبة_المسؤولين: discord.Role,
                             توقيع_الخط: str, 
                             صورة_الغلاف: str, 
                             صورة_الشاشة: str):
    
    await interaction.response.defer(ephemeral=True)
    
    query_db('''INSERT OR REPLACE INTO settings (guild_id, app_channel, tweet_channel, market_channel, gram_channel, verify_channel, admin_channel, admin_role, signature, panel_img, apps_img) 
                VALUES (?,?,?,?,?,?,?,?,?,?,?)''',
             (interaction.guild.id, روم_الجوال.id, روم_التغريدات.id, روم_السوق.id, روم_اليوميات.id, روم_التقديمات.id, روم_الادارة.id, رتبة_المسؤولين.id, توقيع_الخط, صورة_الغلاف, صورة_الشاشة), commit=True)
    
    # نشر البانل الرئيسي للهاتف للمواطنين
    embed = discord.Embed(
        title="URG | OS Smart Phone", 
        description=f"📱 مرحباً بك في منظومة الهاتف الذكي الموحد للمدينة.\n\nاضغط على الزر أدناه لتشغيل النظام والدخول لشاشة تطبيقاتك الفرعية بشكل إيبك.\n{LINE_SEPARATOR}"
    )
    if صورة_الغلاف:
        embed.set_image(url=صورة_الغلاف)
    embed.set_footer(text="نظام إدارة المدينة | إشراف: عمر الراشدي - وزير المالية")
    
    await روم_الجوال.send(embed=embed, view=BootPhoneMasterView())
    
    # نشر بانل لوحة التحكم الإدارية في روم الإدارة المحدد
    admin_embed = discord.Embed(
        title="⚙️ لوحة تحكم الإدارة السرية للأنظمة", 
        description=f"أدوات إدارة وتعديل السيستم وتصفير الحسابات الفورية للمواطنين بالمدينة.\n{LINE_SEPARATOR}", 
        color=discord.Color.dark_red()
    )
    if صورة_الغلاف: admin_embed.set_image(url=صورة_الغلاف)
    admin_embed.set_footer(text="صلاحيات وزارة المالية | عمر الراشدي")
    
    await روم_الادارة.send(embed=admin_embed, view=PersistentAdminPanelView())
    
    await interaction.followup.send("✅ تم تهيئة وتسطيب نظام الهاتف المتكامل بنجاح ونشر اللوحات بجميع الرومات المحددة!", ephemeral=True)

# ==============================================================================
# 13. حدث الإقلاع وتسجيل الواجهات المستمرة (Anti-Fail Connection)
# ==============================================================================
@bot.event
async def on_ready():
    # تسجيل دائم لجميع الكلاسات الثابتة لضمان استقرار العمل عند إعادة تشغيل الاستضافة
    bot.add_view(BootPhoneMasterView())
    bot.add_view(PersistentAdminPanelView())
    
    view_member = ui.View(timeout=None).add_item(MembershipTypeSelect())
    bot.add_view(view_member)
    
    view_main = ui.View(timeout=None).add_item(MainAppListSelect())
    bot.add_view(view_main)
    
    await bot.add_cog(GlobalInteractionsCog(bot))
    await bot.tree.sync()
    
    print("\n=============================================")
    print(f"✅ URG OS BOT IS FULLY OPERATIONAL!")
    print(f"Logged in as: {bot.user.name} (ID: {bot.user.id})")
    print(f"System Supervisor: Omar Al-Rashdi (Minister of Finance)")
    print(f"Code Length Validation: Strong Engine Armed")
    print("=============================================\n")

# تشغيل البوت باستخدام التوكن المرفق بملف البيئة
bot.run(os.getenv("DISCORD_TOKEN"))
