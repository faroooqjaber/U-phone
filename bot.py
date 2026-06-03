import discord
from discord.ext import commands
from discord import app_commands, ui
import sqlite3
import os
import re
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

# إنشاء الجداول لقاعدة البيانات (تم التحديث لدعم الميزات الجديدة)
def setup_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (discord_id INTEGER PRIMARY KEY, username TEXT UNIQUE, verified INTEGER DEFAULT 0)''')
    c.execute('''CREATE TABLE IF NOT EXISTS follows (follower_id INTEGER, followed_id INTEGER, PRIMARY KEY(follower_id, followed_id))''')
    c.execute('''CREATE TABLE IF NOT EXISTS settings (guild_id INTEGER PRIMARY KEY, app_channel INTEGER, tweet_channel INTEGER, verify_channel INTEGER, admin_channel INTEGER, embed_color TEXT, admin_role INTEGER, panel_img TEXT, signature TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS tweets (message_id INTEGER PRIMARY KEY, author_id INTEGER, likes_count INTEGER DEFAULT 0, rts_count INTEGER DEFAULT 0)''')
    c.execute('''CREATE TABLE IF NOT EXISTS tweet_likes (message_id INTEGER, user_id INTEGER, PRIMARY KEY(message_id, user_id))''')
    c.execute('''CREATE TABLE IF NOT EXISTS tweet_rts (message_id INTEGER, user_id INTEGER, PRIMARY KEY(message_id, user_id))''')
    c.execute('''CREATE TABLE IF NOT EXISTS hashtags (tag TEXT PRIMARY KEY, count INTEGER DEFAULT 0)''')
    conn.commit()
    conn.close()

setup_db()

# دالة فحص وحظر الروابط الخارجية (تسمح فقط بروابط الصور المباشرة ودعم ديسكورد)
def secure_text(text):
    urls = re.findall(r'https?://\S+', text)
    for url in urls:
        if "discord" in url and ("attachments" in url or "asset" in url):
            continue
        if any(ext in url.lower() for ext in ['.png', '.jpg', '.jpeg', '.gif', '.webp']):
            continue
        return False
    return True

# ==========================================
# 🎛️ النوافذ المنبثقة (Modals)
# ==========================================

class RegisterModal(ui.Modal, title="إنشاء حساب تويتر جديد"):
    username = ui.TextInput(label="اسم المستخدم (اليوزر بدون @)", placeholder="مثال: omar_rashidi", min_length=3, max_length=15)
    async def on_submit(self, interaction: discord.Interaction):
        user_input = self.username.value.strip().lower()
        if not re.match(r"^[a-zA-Z0-9_]+$", user_input):
            return await interaction.response.send_message("❌ خطأ: اليوزر يجب أن يحتوي على أحرف، أرقام، أو شرطة سفلية فقط!", ephemeral=True)
        try:
            query_db("INSERT INTO users (discord_id, username) VALUES (?, ?)", (interaction.user.id, user_input), commit=True)
            await interaction.response.send_message(f"🎉 تم إنشاء حسابك بنجاح بـ يوزر: `@{user_input}`", ephemeral=True)
        except sqlite3.IntegrityError:
            await interaction.response.send_message("❌ خطأ: اسم المستخدم هذا مستخدم بالفعل في حساب آخر بالمدينة!", ephemeral=True)

class TweetModal(ui.Modal, title="إرسال تغريدة جديدة"):
    content = ui.TextInput(label="محتوى التغريدة", style=discord.TextStyle.paragraph, placeholder="اكتب ما يدور في ذهنك هنا...", max_length=280)
    media = ui.TextInput(label="رابط صورة المرفق (اختياري)", placeholder="ضع رابط الصورة المباشر هنا فقط...", required=False)
    
    async def on_submit(self, interaction: discord.Interaction):
        user_data = query_db("SELECT username, verified FROM users WHERE discord_id = ?", (interaction.user.id,), one=True)
        if not user_data:
            return await interaction.response.send_message("❌ ليس لديك حساب! قم بإنشاء حساب أولاً من اللوحة الرئيسية.", ephemeral=True)
        
        text = self.content.value
        media_url = self.media.value.strip() if self.media.value else None
        
        if not secure_text(text) or (media_url and not secure_text(media_url)):
            return await interaction.response.send_message("❌ خطأ أمني: تم حظر التغريدة! لا يُسمح بنشر روابط خارجية أو دعوات ديسكورد، مسموح فقط بروابط الصور.", ephemeral=True)
        
        setting = query_db("SELECT tweet_channel, embed_color, signature FROM settings WHERE guild_id = ?", (interaction.guild.id,), one=True)
        if not setting: return await interaction.response.send_message("❌ لم يتم ضبط إعدادات البوت بالسيرفر بعد.", ephemeral=True)
        
        tweet_chan = interaction.guild.get_channel(setting[0])
        color = int(setting[1], 16)
        signature_text = setting[2] # جلب التوقيع (خط السيرفر)
        
        # استخراج الهاشتاقات وزيادة عدادها
        tags = re.findall(r'#\w+', text)
        for tag in tags:
            query_db("INSERT INTO hashtags (tag, count) VALUES (?, 1) ON CONFLICT(tag) DO UPDATE SET count = count + 1", (tag,), commit=True)
            
        username = f"{interaction.user.display_name} (@{user_data[0]})"
        if user_data[1] == 1:
            username += " ☑️"
            
        # دمج خط السيرفر (التوقيع) أسفل محتوى التغريدة إذا كان متوفراً
        embed_description = f"{text}\n\n{signature_text}" if signature_text else text
            
        embed = discord.Embed(description=embed_description, color=color, timestamp=datetime.utcnow())
        embed.set_author(name=username, icon_url=interaction.user.display_avatar.url)
        if media_url: embed.set_image(url=media_url)
        embed.set_footer(text="U app | مدينة يو ار جي")
        
        # إضافة حقول الإحصائيات التفاعلية داخل الإمبد
        embed.add_field(name="📊 إحصائيات التفاعل:", value="❤️ الإعجابات: **0** | 🔁 إعادة النشر: **0**", inline=False)
        
        tweet_msg = await tweet_chan.send(embed=embed)
        await tweet_msg.edit(view=TweetActionView(tweet_msg.id))
        query_db("INSERT INTO tweets (message_id, author_id) VALUES (?, ?)", (tweet_msg.id, interaction.user.id), commit=True)
        await interaction.response.send_message("✅ تم نشر تغريدتك بنجاح في روم التغريدات!", ephemeral=True)

class VerifyModal(ui.Modal, title="تقديم طلب توثيق الحساب"):
    username = ui.TextInput(label="يوزر الحساب", placeholder="اكتب يوزرك بدون @")
    reason = ui.TextInput(label="سبب طلب التوثيق بالمدينة", style=discord.TextStyle.paragraph, placeholder="اكتب منصبك أو سبب استحقاقك للتوثيق...")
    async def on_submit(self, interaction: discord.Interaction):
        user_data = query_db("SELECT verified FROM users WHERE discord_id = ?", (interaction.user.id,), one=True)
        if not user_data: return await interaction.response.send_message("❌ ليس لديك حساب أصلاً لتوثيقه!", ephemeral=True)
        if user_data[0] == 1: return await interaction.response.send_message("ℹ️ حسابك موثق بالفعل!", ephemeral=True)
        
        setting = query_db("SELECT verify_channel, admin_role FROM settings WHERE guild_id = ?", (interaction.guild.id,), one=True)
        v_chan = interaction.guild.get_channel(setting[0])
        admin_role_id = setting[1]
        
        # تجهيز منشن رتبة المسؤولين المسؤولة عن التوثيق
        role_mention = f"<@&{admin_role_id}>" if admin_role_id else ""
        
        embed = discord.Embed(title="🔔 طلب توثيق جديد", color=discord.Color.orange())
        embed.add_field(name="العضو:", value=interaction.user.mention)
        embed.add_field(name="اليوزر المقرون:", value=f"@{self.username.value}")
        embed.add_field(name="السبب المذكور:", value=self.reason.value, inline=False)
        
        await v_chan.send(content=role_mention, embed=embed, view=VerifyActionView(interaction.user.id))
        await interaction.response.send_message("✅ تم إرسال طلب توثيقك إلى الإدارة بنجاح وجاري المراجعة.", ephemeral=True)

class SearchModal(ui.Modal, title="البحث عن حساب شخص"):
    username = ui.TextInput(label="يوزر الحساب المراد البحث عنه", placeholder="اكتب اليوزر بدون @")
    async def on_submit(self, interaction: discord.Interaction):
        target = self.username.value.strip().lower()
        res = query_db("SELECT discord_id, verified FROM users WHERE username = ?", (target,), one=True)
        if not res: return await interaction.response.send_message("❌ لم يتم العثور على أي حساب بهذا اليوزر في المدينة.", ephemeral=True)
        
        followers = len(query_db("SELECT follower_id FROM follows WHERE followed_id = ?", (res[0],)))
        following = len(query_db("SELECT followed_id FROM follows WHERE follower_id = ?", (res[0],)))
        
        embed = discord.Embed(title=f"👤 ملف الحساب: @{target}", color=discord.Color.blue())
        embed.add_field(name="صاحب الحساب:", value=f"<@{res[0]}>")
        embed.add_field(name="حالة التوثيق:", value="موثق ☑️" if res[1] == 1 else "غير موثق")
        embed.add_field(name="المتابعون:", value=f"**{followers}** متابع")
        embed.add_field(name="يتابع:", value=f"**{following}** شخص")
        
        await interaction.response.send_message(embed=embed, view=FollowActionView(res[0]), ephemeral=True)

class ReplyModal(ui.Modal, title="الرد على التغريدة"):
    reply_text = ui.TextInput(label="اكتب ردك هنا", style=discord.TextStyle.paragraph, max_length=200)
    def __init__(self, message: discord.Message):
        super().__init__()
        self.message = message
    async def on_submit(self, interaction: discord.Interaction):
        user_data = query_db("SELECT username FROM users WHERE discord_id = ?", (interaction.user.id,), one=True)
        if not user_data: return await interaction.response.send_message("❌ يجب إنشاء حساب أولاً للرد!", ephemeral=True)
        
        text = self.reply_text.value
        if not secure_text(text): return await interaction.response.send_message("❌ محظور وضع روابط خارجية!", ephemeral=True)
        
        # فتح ثيرد تلقائي على التغريدة للردود
        thread = self.message.thread
        if thread is None:
            thread = await self.message.create_thread(name=f"الردود على تغريدة @{user_data[0]}", auto_archive_duration=60)
            
        rembed = discord.Embed(description=text, color=discord.Color.light_grey(), timestamp=datetime.utcnow())
        rembed.set_author(name=f"رد من @{user_data[0]}", icon_url=interaction.user.display_avatar.url)
        await thread.send(embed=rembed)
        await interaction.response.send_message("✅ تم إضافة ردك داخل ثيرد التغريدة!", ephemeral=True)

# ==========================================
# 🔘 واجهات القوائم المنسدلة والتفاعلات (Views)
# ==========================================

# كلاس القائمة المنسدلة الرئيسي الجديد
class MainSelect(ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="إنشاء حساب 📝", value="reg", emoji="📝"),
            discord.SelectOption(label="إرسال تغريدة 🐦", value="tweet", emoji="🐦"),
            discord.SelectOption(label="طلب توثيق 🏅", value="verify", emoji="🏅"),
            discord.SelectOption(label="حسابي والترند 👤", value="profile", emoji="👤"),
            discord.SelectOption(label="البحث عن حساب 🔍", value="search", emoji="🔍"),
            discord.SelectOption(label="إعادة الاختيار 🔄", value="reset", emoji="🔄")
        ]
        super().__init__(placeholder="القائمة الرئيسية لـ U app | إضغط هنا 👇", options=options, custom_id="main_menu_select")

    async def callback(self, interaction: discord.Interaction):
        val = self.values[0]
        if val == "reg":
            await interaction.response.send_modal(RegisterModal())
        elif val == "tweet":
            await interaction.response.send_modal(TweetModal())
        elif val == "verify":
            await interaction.response.send_modal(VerifyModal())
        elif val == "search":
            await interaction.response.send_modal(SearchModal())
        elif val == "reset":
            await interaction.response.send_message("🔄 تمت إعادة تعيين خيار القائمة المنسدلة بنجاح.", ephemeral=True)
        elif val == "profile":
            data = query_db("SELECT username, verified FROM users WHERE discord_id = ?", (interaction.user.id,), one=True)
            if not data: return await interaction.response.send_message("❌ ليس لديك حساب مسجل بعد!", ephemeral=True)
            
            followers = len(query_db("SELECT follower_id FROM follows WHERE followed_id = ?", (interaction.user.id,)))
            following = len(query_db("SELECT followed_id FROM follows WHERE follower_id = ?", (interaction.user.id,)))
            
            # جلب الترندات الأكثر تداولاً (تم ترقيتها لأعلى 5 هاشتاقات)
            top_tags = query_db("SELECT tag, count FROM hashtags ORDER BY count DESC LIMIT 5")
            trend_text = "\n".join([f"🔥 {t[0]} ({t[1]} تغريدة)" for t in top_tags]) if top_tags else "لا توجد هاشتاقات نشطة حالياً."
            
            embed = discord.Embed(title=f"📱 بيانات حسابك: @{data[0]}", color=discord.Color.blue())
            embed.add_field(name="حالة التوثيق:", value="موثق ☑️" if data[1] == 1 else "غير موثق")
            embed.add_field(name="المتابعون:", value=f"**{followers}** متابع", inline=True)
            embed.add_field(name="يتابع:", value=f"**{following}** شخص", inline=True)
            embed.add_field(name="📈 ترندات المدينة الأكثر تداولاً (Top 5):", value=trend_text, inline=False)
            
            await interaction.response.send_message(embed=embed, ephemeral=True)

# تعديل بانل اللوحة الرئيسية ليحتوي على القائمة المنسدلة بدلاً من الأزرار
class MainPanelView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(MainSelect())

class TweetActionView(ui.View):
    def __init__(self, message_id: int):
        super().__init__(timeout=None)
        self.message_id = message_id

    async def update_embed(self, interaction: discord.Interaction):
        likes = query_db("SELECT COUNT(*) FROM tweet_likes WHERE message_id = ?", (self.message_id,), one=True)[0]
        rts = query_db("SELECT COUNT(*) FROM tweet_rts WHERE message_id = ?", (self.message_id,), one=True)[0]
        
        embed = interaction.message.embeds[0]
        embed.set_field_at(0, name="📊 إحصائيات التفاعل:", value=f"❤️ الإعجابات: **{likes}** | 🔁 إعادة النشن: **{rts}**", inline=False)
        await interaction.message.edit(embed=embed)

    @ui.button(label="أعجبني ❤️", style=discord.ButtonStyle.secondary, custom_id="tweet_like")
    async def like_click(self, interaction: discord.Interaction, button: ui.Button):
        liked = query_db("SELECT 1 FROM tweet_likes WHERE message_id = ? AND user_id = ?", (self.message_id, interaction.user.id), one=True)
        if liked:
            query_db("DELETE FROM tweet_likes WHERE message_id = ? AND user_id = ?", (self.message_id, interaction.user.id), commit=True)
        else:
            query_db("INSERT INTO tweet_likes (message_id, user_id) VALUES (?, ?)", (self.message_id, interaction.user.id), commit=True)
        await interaction.response.defer()
        await self.update_embed(interaction)

    @ui.button(label="إعادة نشر 🔁", style=discord.ButtonStyle.secondary, custom_id="tweet_rt")
    async def rt_click(self, interaction: discord.Interaction, button: ui.Button):
        rted = query_db("SELECT 1 FROM tweet_rts WHERE message_id = ? AND user_id = ?", (self.message_id, interaction.user.id), one=True)
        if rted:
            query_db("DELETE FROM tweet_rts WHERE message_id = ? AND user_id = ?", (self.message_id, interaction.user.id), commit=True)
        else:
            query_db("INSERT INTO tweet_rts (message_id, user_id) VALUES (?, ?)", (self.message_id, interaction.user.id), commit=True)
        await interaction.response.defer()
        await self.update_embed(interaction)

    @ui.button(label="رد 💬", style=discord.ButtonStyle.secondary, custom_id="tweet_reply")
    async def reply_click(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(ReplyModal(interaction.message))

class FollowActionView(ui.View):
    def __init__(self, target_id: int):
        super().__init__(timeout=30)
        self.target_id = target_id
        
    @ui.button(label="متابعة / إلغاء المتابعة ➕", style=discord.ButtonStyle.primary)
    async def follow_toggle(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user.id == self.target_id:
            return await interaction.response.send_message("❌ لا يمكنك متابعة نفسك يا بطل!", ephemeral=True)
        
        is_following = query_db("SELECT 1 FROM follows WHERE follower_id = ? AND followed_id = ?", (interaction.user.id, self.target_id), one=True)
        if is_following:
            query_db("DELETE FROM follows WHERE follower_id = ? AND followed_id = ?", (interaction.user.id, self.target_id), commit=True)
            await interaction.response.send_message("❌ تم إلغاء متابعة الحساب.", ephemeral=True)
        else:
            query_db("INSERT INTO follows (follower_id, followed_id) VALUES (?, ?)", (interaction.user.id, self.target_id), commit=True)
            await interaction.response.send_message("✅ تم متابعة الحساب بنجاح!", ephemeral=True)

class VerifyActionView(ui.View):
    def __init__(self, target_user_id: int):
        super().__init__(timeout=None)
        self.target_user_id = target_user_id
        
    @ui.button(label="قبول التوثيق ✅", style=discord.ButtonStyle.success)
    async def approve(self, interaction: discord.Interaction, button: ui.Button):
        query_db("UPDATE users SET verified = 1 WHERE discord_id = ?", (self.target_user_id,), commit=True)
        await interaction.response.send_message("✅ تم قبول التوثيق وتحديث رتبة الحساب بنجاح!", ephemeral=True)
        await interaction.message.delete()
        
    @ui.button(label="رفض الطلب ❌", style=discord.ButtonStyle.danger)
    async def deny(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_message("❌ تم رفض طلب توثيق هذا الحساب.", ephemeral=True)
        await interaction.message.delete()

# ==========================================
# 🛑 أوامر السلاش (Slash Commands) والإدارة
# ==========================================

@bot.event
async def on_ready():
    print(f'✅ تم تشغيل البوت بنجاح باسم: {bot.user.name}')
    await bot.change_presence(activity=discord.Game(name="U app | مدينة يو ار جي"))
    
    # إعادة ربط الـ Views الثابتة المستمرة لضمان عمل الأزرار والقوائم بعد ريستارت البوت
    bot.add_view(MainPanelView())
    bot.add_view(AdminControlView())
    try:
        synced = await bot.tree.sync()
        print(f"🔄 تم مزامنة {len(synced)} أوامر سلاش بنجاح.")
    except Exception as e:
        print(f"❌ خطأ في المزامنة: {e}")

@bot.tree.command(name="شرح", description="شرح استخدام تطبيق تويتر الخاص بالمدينة")
async def help_cmd(interaction: discord.Interaction):
    embed = discord.Embed(
        title="📘 دليل استخدام تطبيق U app",
        description="نظام تويتر المتكامل لمدينة يو ار جي:\n\n"
                    "1️⃣ **روم التطبيق:** يحتوي على القائمة المنسدلة لفتح النوافذ المنبثقة والتحكم بملفك.\n"
                    "2️⃣ **إنشاء الحساب:** يتيح لك حجز يوزر نيم فريد لا يتكرر بالمدينة.\n"
                    "3️⃣ **التغريد:** يدعم الهاشتاقات والمرفقات والتوقيع التلقائي (روابط صور فقط، الروابط الأخرى محظورة).\n"
                    "4️⃣ **التفاعلات:** التغريدات تظهر بأزرار (أعجبني، ريتويت، وردود تفتح داخل ثيرد مستقل).\n"
                    "5️⃣ **المتابعة:** ابحث عن أي شخص من القائمة وتابعه لرفع إحصائيات حسابه!",
        color=discord.Color.blue()
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)

# تحديث أمر التسطيب بالبارامترات الجديدة وحفظها كاملة بقاعدة البيانات
@bot.tree.command(name="تسطيب_البوت", description="إعداد وتجهيز منظومة تويتر رول بلي المحدثة (للإدارة)")
@app_commands.checks.has_permissions(administrator=True)
async def setup_cmd(interaction: discord.Interaction, 
                    روم_التطبيق: discord.TextChannel, 
                    روم_التغريدات: discord.TextChannel, 
                    روم_طلبات_التوثيق: discord.TextChannel, 
                    روم_الادارة: discord.TextChannel, 
                    رتبة_المسؤولين: discord.Role, 
                    رابط_صورة_البانل: str, 
                    خط_السيرفر: str, 
                    لون_الامبد: str = "00acee"):
    
    query_db('''INSERT OR REPLACE INTO settings (guild_id, app_channel, tweet_channel, verify_channel, admin_channel, embed_color, admin_role, panel_img, signature) 
              VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''', 
              (interaction.guild.id, روم_التطبيق.id, روم_التغريدات.id, روم_طلبات_التوثيق.id, روم_الادارة.id, لون_الامبد, رتبة_المسؤولين.id, رابط_صورة_البانل, خط_السيرفر), commit=True)

    panel_embed = discord.Embed(
        title="📱 تطبيق U app | اللوحة الرئيسية",
        description="مرحباً بك في منصة تويتر الرسمية المخصصة لسكان مدينة يو ار جي.\n\n"
                    "يمكنك التحكم التام بحسابك والتواصل البرمي المميز من خلال القائمة المنسدلة بالأسفل 👇",
        color=int(لون_الامبد, 16)
    )
    panel_embed.set_image(url=رابط_صورة_البانل) # تعيين صورة البانل ديناميكياً
    panel_embed.set_footer(text="U app © جميع الحقوق محفوظة لـ مدينة يو ار جي")
    
    await روم_التطبيق.send(embed=panel_embed, view=MainPanelView())
    
    # إرسال لوحة الإدارة لروم الإدارة
    admin_embed = discord.Embed(title="⚙️ لوحة تحكم الإدارة السرية", description="أدوات إدارة وتعديل السيستم وتصفير الحسابات.", color=discord.Color.red())
    await روم_الادارة.send(embed=admin_embed, view=AdminControlView())
    
    await interaction.response.send_message("✅ تم إعداد القنوات وتحديث سيستم قاعدة البيانات بنجاح، وإرسال لوحة التحكم المنسدلة واللوحة الإدارية!", ephemeral=True)

# إضافة أمر المطورين المستقل
@bot.tree.command(name="مطورين", description="عرض معلومات المبرمج المطور للنظام")
async def dev_cmd(interaction: discord.Interaction):
    embed = discord.Embed(
        title="💻 عن المطور",
        description="نظام URG System v2.0\n\nالمبرمج:\n**f_arooq004**\n\nجميع الحقوق محفوظة ©",
        color=discord.Color.dark_grey()
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)

# ==========================================
# 🛠️ لوحة تحكم الإدارة (روم الإدارة)
# ==========================================

class AdminControlView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(label="حذف حساب 🗑️", style=discord.ButtonStyle.danger, custom_id="adm_del")
    async def del_acc(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(AdminDeleteModal())

    @ui.button(label="تعديل يوزر ✏️", style=discord.ButtonStyle.secondary, custom_id="adm_edit")
    async def edit_acc(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(AdminEditModal())

class AdminDeleteModal(ui.Modal, title="حذف حساب عضو"):
    username = ui.TextInput(label="يوزر الحساب المراد حذفه")
    async def on_submit(self, interaction: discord.Interaction):
        target = self.username.value.strip().lower()
        res = query_db("SELECT discord_id FROM users WHERE username = ?", (target,), one=True)
        if not res: return await interaction.response.send_message("❌ اليوزر غير موجود بالسيستم.", ephemeral=True)
        query_db("DELETE FROM users WHERE username = ?", (target,), commit=True)
        query_db("DELETE FROM follows WHERE follower_id = ? OR followed_id = ?", (res[0], res[0]), commit=True)
        await interaction.response.send_message(f"🗑️ تم حذف حساب `@{target}` وجميع بياناته ومتابعيه بنجاح!", ephemeral=True)

class AdminEditModal(ui.Modal, title="تعديل يوزر عضو يدوياً"):
    old_user = ui.TextInput(label="اليوزر الحالي")
    new_user = ui.TextInput(label="اليوزر الجديد")
    async def on_submit(self, interaction: discord.Interaction):
        old = self.old_user.value.strip().lower()
        new = self.new_user.value.strip().lower()
        try:
            query_db("UPDATE users SET username = ? WHERE username = ?", (new, old), commit=True)
            await interaction.response.send_message(f"✏️ تم تعديل اليوزر بنجاح من `@{old}` إلى `@{new}`.", ephemeral=True)
        except sqlite3.IntegrityError:
            await interaction.response.send_message("❌ اليوزر الجديد مكرر وموجود مسبقاً!", ephemeral=True)

# تشغيل البوت بالتوكن السري
token = os.getenv("DISCORD_TOKEN")
if token:
    bot.run(token)
else:
    print("❌ خطأ: لم يتم العثور على المتغير البيئي لتوكن البوت DISCORD_TOKEN!")
