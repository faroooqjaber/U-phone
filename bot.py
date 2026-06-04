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

# إنشاء وتحديث الجداول لدعم الأنظمة الجديدة (العضويات والإشعارات والتعليقات)
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
    
    # حقن الحقول الجديدة بأمان في حال كانت قاعدة البيانات قديمة
    try: c.execute("ALTER TABLE users ADD COLUMN notifications INTEGER DEFAULT 1")
    except sqlite3.OperationalError: pass
    try: c.execute("ALTER TABLE users ADD COLUMN account_type TEXT DEFAULT 'شخصي'")
    except sqlite3.OperationalError: pass
    try: c.execute("ALTER TABLE tweets ADD COLUMN comments_open INTEGER DEFAULT 1")
    except sqlite3.OperationalError: pass
    
    conn.commit()
    conn.close()

setup_db()

# دالة إرسال الإشعارات التلقائية للخاص
async def send_notification(target_id, text):
    status = query_db("SELECT notifications FROM users WHERE discord_id = ?", (target_id,), one=True)
    if status and status[0] == 0:
        return # الإشعارات مغلقة من قبل المستخدم
    try:
        user = bot.get_user(target_id) or await bot.fetch_user(target_id)
        if user:
            embed = discord.Embed(title="🔔 إشعار جديد - U app", description=text, color=discord.Color.blue())
            await user.send(embed=embed)
    except Exception:
        pass # في حال كانت خاصية الخاص مغلقة عند العضو

# دالة فحص وحظر الروابط الخارجية
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
# 🎛️ النوافذ المنبثقة والواجهات الفرعية (Modals & Sub-Views)
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
    content = ui.TextInput(label="محتوى التغريدة", style=discord.TextStyle.paragraph, placeholder="اكتب ما يدور في ذهنك هنا... يمكنك منشن أي شخص بـ @يوزر", max_length=280)
    media = ui.TextInput(label="رابط صورة المرفق (اختياري)", placeholder="ضع رابط الصورة المباشر هنا فقط...", required=False)
    comments = ui.TextInput(label="هل تريد فتح التعليقات؟ (نعم / لا)", min_length=2, max_length=3, placeholder="اكتب نعم أو لا فقط")
    
    async def on_submit(self, interaction: discord.Interaction):
        user_data = query_db("SELECT username, verified, account_type FROM users WHERE discord_id = ?", (interaction.user.id,), one=True)
        if not user_data:
            return await interaction.response.send_message("❌ ليس لديك حساب! قم بإنشاء حساب أولاً من اللوحة الرئيسية.", ephemeral=True)
        
        comments_allowed = self.comments.value.strip()
        if comments_allowed not in ["نعم", "لا"]:
            return await interaction.response.send_message("❌ خطأ: يجب كتابة 'نعم' أو 'لا' فقط في خانة فتح التعليقات!", ephemeral=True)
        
        text = self.content.value
        media_url = self.media.value.strip() if self.media.value else None
        
        if not secure_text(text) or (media_url and not secure_text(media_url)):
            return await interaction.response.send_message("❌ خطأ أمني: تم حظر التغريدة! لا يُسمح بنشر روابط خارجية، مسموح فقط بروابط الصور.", ephemeral=True)
        
        setting = query_db("SELECT tweet_channel, embed_color, signature FROM settings WHERE guild_id = ?", (interaction.guild.id,), one=True)
        if not setting: return await interaction.response.send_message("❌ لم يتم ضبط إعدادات البوت بالسيرفر بعد.", ephemeral=True)
        
        tweet_chan = interaction.guild.get_channel(setting[0])
        color = int(setting[1], 16)
        signature_text = setting[2]
        
        tags = re.findall(r'#\w+', text)
        for tag in tags:
            query_db("INSERT INTO hashtags (tag, count) VALUES (?, 1) ON CONFLICT(tag) DO UPDATE SET count = count + 1", (tag,), commit=True)
            
        # تحديد الإيموجي المناسب للشارة المعتمدة بناءً على نوع الحساب الموثق
        badge = ""
        if user_data[1] == 1:
            if user_data[2] == "حساب حكومي": badge = " 🏛️"
            elif user_data[2] == "حساب تجاري": badge = " 💼"
            elif user_data[2] == "حساب موثق": badge = " ☑️"
            else: badge = " ☑️"
            
        username = f"{interaction.user.display_name} (@{user_data[0]}){badge}"
            
        embed = discord.Embed(description=text, color=color, timestamp=datetime.utcnow())
        embed.set_author(name=username, icon_url=interaction.user.display_avatar.url)
        if media_url: embed.set_image(url=media_url)
        embed.set_footer(text="U app | مدينة يو ار جي")
        embed.add_field(name="📊 إحصائيات التفاعل:", value="❤️ الإعجابات: **0** | 🔁 إعادة النشر: **0**", inline=False)
        
        tweet_msg = await tweet_chan.send(embed=embed)
        
        # إرسال خط السيرفر (التوقيع) منفصلاً تلقائياً بعد التغريدة مباشرة وليس بداخلها
        if signature_text:
            await tweet_chan.send(content=signature_text)
            
        is_open = 1 if comments_allowed == "نعم" else 0
        
        await tweet_msg.edit(view=TweetActionView(tweet_msg.id))
        query_db("INSERT INTO tweets (message_id, author_id, comments_open) VALUES (?, ?, ?)", (tweet_msg.id, interaction.user.id, is_open), commit=True)
        
        # 🔔 [نظام المنشن الفعلي للتغريدات] 🔔
        mentions = re.findall(r'@([a-zA-Z0-9_]+)', text)
        for mentioned_user in list(set(mentions)): # تصفية الأسماء المكررة لتفادي إرسال تنبيهات مزعجة لنفس الشخص
            if mentioned_user.lower() != user_data[0].lower(): # منع البوت من إرسال تنبيه للشخص إذا منشن نفسه
                target_res = query_db("SELECT discord_id FROM users WHERE username = ?", (mentioned_user.lower(),), one=True)
                if target_res:
                    await send_notification(target_res[0], f"👤 قام `@{user_data[0]}` بالإشارة إليك في تغريدته الأخيرة!\n🔗 [إضغط هنا للانتقال ومساندة التغريدة]({tweet_msg.jump_url})")

        await interaction.response.send_message("✅ تم نشر تغريدتك بنجاح في روم التغريدات!", ephemeral=True)

# واجهة اختيار نوع العضوية المنسدلة الفرعية
class MembershipSelect(ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="حساب حكومي (القطاعات الرسمية)", value="حساب حكومي", emoji="🏛️"),
            discord.SelectOption(label="حساب تجاري (الشركات والمحلات)", value="حساب تجاري", emoji="💼"),
            discord.SelectOption(label="حساب موثق (للمشاهير والأعيان)", value="حساب موثق", emoji="☑️")
        ]
        super().__init__(placeholder="اختر نوع العضوية المطلوبة...", options=options, custom_id="membership_sub_select")

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(MembershipModal(self.values[0]))

class MembershipTypeView(ui.View):
    def __init__(self):
        super().__init__(timeout=60)
        self.add_item(MembershipSelect())

class MembershipModal(ui.Modal):
    username = ui.TextInput(label="يوزر الحساب المراد توثيقه (بدون @)", placeholder="مثال: omar_rashidi")
    reason = ui.TextInput(label="سبب واستحقاق طلب العضوية بالمدينة", style=discord.TextStyle.paragraph, placeholder="اكتب مبرراتك أو منصبك هنا...")
    
    def __init__(self, account_type: str):
        super().__init__(title=f"تقديم طلب: {account_type}")
        self.account_type = account_type

    async def on_submit(self, interaction: discord.Interaction):
        user_data = query_db("SELECT verified FROM users WHERE discord_id = ?", (interaction.user.id,), one=True)
        if not user_data: return await interaction.response.send_message("❌ ليس لديك حساب أصلاً لتقديم طلب له!", ephemeral=True)
        
        setting = query_db("SELECT verify_channel, admin_role FROM settings WHERE guild_id = ?", (interaction.guild.id,), one=True)
        v_chan = interaction.guild.get_channel(setting[0])
        admin_role_id = setting[1]
        role_mention = f"<@&{admin_role_id}>" if admin_role_id else ""
        
        embed = discord.Embed(title="🔔 طلب تقديم عضوية جديد", color=discord.Color.gold())
        embed.add_field(name="العضو المقدم:", value=interaction.user.mention)
        embed.add_field(name="اليوزر بالسيستم:", value=f"@{self.username.value}")
        embed.add_field(name="نوع العضوية المقترحة:", value=f"**{self.account_type}**", inline=False)
        embed.add_field(name="السبب المذكور:", value=self.reason.value, inline=False)
        
        await v_chan.send(content=role_mention, embed=embed, view=VerifyActionView(interaction.user.id, self.account_type))
        await interaction.response.send_message("✅ تم إرسال طلب عضويتك الفاخرة للإدارة بنجاح ويتم مراجعتها الآن.", ephemeral=True)

class NotificationToggleView(ui.View):
    def __init__(self):
        super().__init__(timeout=60)
    @ui.button(label="تبديل حالة الإشعارات (تفعيل/تعطيل) 🔄", style=discord.ButtonStyle.primary)
    async def toggle(self, interaction: discord.Interaction, button: ui.Button):
        status = query_db("SELECT notifications FROM users WHERE discord_id = ?", (interaction.user.id,), one=True)
        new_status = 0 if (status and status[0] == 1) else 1
        query_db("UPDATE users SET notifications = ? WHERE discord_id = ?", (new_status, interaction.user.id), commit=True)
        current = "مفعلة 🔔" if new_status == 1 else "معطلة 🔕"
        await interaction.response.edit_message(content=f"✅ تم تحديث إعداداتك بنجاح! الإشعارات الآن: **{current}**", view=None)

class SearchModal(ui.Modal, title="البحث عن حساب شخص"):
    username = ui.TextInput(label="يوزر الحساب المراد البحث عنه", placeholder="اكتب اليوزر بدون @")
    async def on_submit(self, interaction: discord.Interaction):
        target = self.username.value.strip().lower()
        res = query_db("SELECT discord_id, verified, account_type FROM users WHERE username = ?", (target,), one=True)
        if not res: return await interaction.response.send_message("❌ لم يتم العثور على أي حساب بهذا اليوزر في المدينة.", ephemeral=True)
        
        followers = len(query_db("SELECT follower_id FROM follows WHERE followed_id = ?", (res[0],)))
        following = len(query_db("SELECT followed_id FROM follows WHERE follower_id = ?", (res[0],)))
        
        acc_str = f"موثق ({res[2]})" if res[1] == 1 else "غير موثق / شخصي"
        embed = discord.Embed(title=f"👤 ملف الحساب: @{target}", color=discord.Color.blue())
        embed.add_field(name="صاحب الحساب:", value=f"<@{res[0]}>")
        embed.add_field(name="فئة الحساب:", value=acc_str)
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
        
        thread = self.message.thread
        if thread is None:
            thread = await self.message.create_thread(name=f"الردود على تغريدة @{user_data[0]}", auto_archive_duration=60)
            
        rembed = discord.Embed(description=text, color=discord.Color.light_grey(), timestamp=datetime.utcnow())
        rembed.set_author(name=f"رد من @{user_data[0]}", icon_url=interaction.user.display_avatar.url)
        reply_msg = await thread.send(embed=rembed)
        
        # 🔔 [نظام المنشن الفعلي للردود والتعليقات] 🔔
        mentions = re.findall(r'@([a-zA-Z0-9_]+)', text)
        for mentioned_user in list(set(mentions)):
            if mentioned_user.lower() != user_data[0].lower():
                target_res = query_db("SELECT discord_id FROM users WHERE username = ?", (mentioned_user.lower(),), one=True)
                if target_res:
                    await send_notification(target_res[0], f"💬 قام `@{user_data[0]}` بالإشارة إليك في رد جديد داخل ثيرد التغريدة!\n🔗 [إضغط هنا لعرض الرد والتعليق عليه]({reply_msg.jump_url})")

        await interaction.response.send_message("✅ تم إضافة ردك داخل ثيرد التغريدة!", ephemeral=True)

# ==========================================
# 🔘 واجهات القوائم المنسدلة والتفاعلات الرئيسية
# ==========================================

class MainSelect(ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="إنشاء حساب 📝", value="reg", emoji="📝"),
            discord.SelectOption(label="إرسال تغريدة 🐦", value="tweet", emoji="🐦"),
            discord.SelectOption(label="تقديم عضوية 🏅", value="membership", emoji="🏅"),
            discord.SelectOption(label="حسابي والترند 👤", value="profile", emoji="👤"),
            discord.SelectOption(label="البحث عن حساب 🔍", value="search", emoji="🔍"),
            discord.SelectOption(label="إعدادات الإشعارات ⚙️", value="settings_menu", emoji="⚙️"),
            discord.SelectOption(label="إعادة الاختيار 🔄", value="reset", emoji="🔄")
        ]
        super().__init__(placeholder="القائمة الرئيسية لـ U app | إضغط هنا 👇", options=options, custom_id="main_menu_select")

    async def callback(self, interaction: discord.Interaction):
        val = self.values[0]
        if val == "reg":
            await interaction.response.send_modal(RegisterModal())
        elif val == "tweet":
            await interaction.response.send_modal(TweetModal())
        elif val == "membership":
            await interaction.response.send_message("⚙️ الرجاء اختيار نوع العضوية التي ترغب بالتقديم عليها للحصول على الشارة الفخمة:", view=MembershipTypeView(), ephemeral=True)
        elif val == "search":
            await interaction.response.send_modal(SearchModal())
        elif val == "reset":
            await interaction.response.send_message("🔄 تمت إعادة تعيين خيار القائمة المنسدلة بنجاح.", ephemeral=True)
        elif val == "settings_menu":
            status = query_db("SELECT notifications FROM users WHERE discord_id = ?", (interaction.user.id,), one=True)
            current = "مفعلة 🔔" if (not status or status[0] == 1) else "معطلة 🔕"
            await interaction.response.send_message(f"⚙️ **إعدادات التنبيهات الحالية لملفك:** {current}\nتلقي الإشعارات في الخاص عند حصول تفاعل (لايك، ريتويت، متابعة، منشن) مفعل بشكل تلقائي ما لم تقم بإغلاقه.", view=NotificationToggleView(), ephemeral=True)
        elif val == "profile":
            data = query_db("SELECT username, verified, account_type FROM users WHERE discord_id = ?", (interaction.user.id,), one=True)
            if not data: return await interaction.response.send_message("❌ ليس لديك حساب مسجل بعد!", ephemeral=True)
            
            followers = len(query_db("SELECT follower_id FROM follows WHERE followed_id = ?", (interaction.user.id,)))
            following = len(query_db("SELECT followed_id FROM follows WHERE follower_id = ?", (interaction.user.id,)))
            
            top_tags = query_db("SELECT tag, count FROM hashtags ORDER BY count DESC LIMIT 5")
            trend_text = "\n".join([f"🔥 {t[0]} ({t[1]} تغريدة)" for t in top_tags]) if top_tags else "لا توجد هاشتاقات نشطة حالياً."
            
            acc_type_str = f"موثق ({data[2]})" if data[1] == 1 else "حساب شخصي عادي"
            embed = discord.Embed(title=f"📱 بيانات حسابك: @{data[0]}", color=discord.Color.blue())
            embed.add_field(name="فئة العضوية:", value=acc_type_str, inline=False)
            embed.add_field(name="المتابعون:", value=f"**{followers}** متابع", inline=True)
            embed.add_field(name="يتابع:", value=f"**{following}** شخص", inline=True)
            embed.add_field(name="📈 ترندات المدينة الأكثر تداولاً (Top 5):", value=trend_text, inline=False)
            
            await interaction.response.send_message(embed=embed, ephemeral=True)

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
        embed.set_field_at(0, name="📊 إحصائيات التفاعل:", value=f"❤️ الإعجابات: **{likes}** | 🔁 إعادة النشر: **{rts}**", inline=False)
        await interaction.message.edit(embed=embed)

    @ui.button(label="أعجبني ❤️", style=discord.ButtonStyle.secondary, custom_id="tweet_like")
    async def like_click(self, interaction: discord.Interaction, button: ui.Button):
        liked = query_db("SELECT 1 FROM tweet_likes WHERE message_id = ? AND user_id = ?", (self.message_id, interaction.user.id), one=True)
        author_data = query_db("SELECT author_id FROM tweets WHERE message_id = ?", (self.message_id,), one=True)
        
        if liked:
            query_db("DELETE FROM tweet_likes WHERE message_id = ? AND user_id = ?", (self.message_id, interaction.user.id), commit=True)
        else:
            query_db("INSERT INTO tweet_likes (message_id, user_id) VALUES (?, ?)", (self.message_id, interaction.user.id), commit=True)
            if author_data and author_data[0] != interaction.user.id:
                user_info = query_db("SELECT username FROM users WHERE discord_id = ?", (interaction.user.id,), one=True)
                uname = user_info[0] if user_info else interaction.user.display_name
                await send_notification(author_data[0], f"❤️ قام المستخدم `@{uname}` بالإعجاب بتغريدتك للتو!")
                
        await interaction.response.defer()
        await self.update_embed(interaction)

    @ui.button(label="إعادة نشر 🔁", style=discord.ButtonStyle.secondary, custom_id="tweet_rt")
    async def rt_click(self, interaction: discord.Interaction, button: ui.Button):
        rted = query_db("SELECT 1 FROM tweet_rts WHERE message_id = ? AND user_id = ?", (self.message_id, interaction.user.id), one=True)
        author_data = query_db("SELECT author_id FROM tweets WHERE message_id = ?", (self.message_id,), one=True)
        
        if rted:
            query_db("DELETE FROM tweet_rts WHERE message_id = ? AND user_id = ?", (self.message_id, interaction.user.id), commit=True)
        else:
            query_db("INSERT INTO tweet_rts (message_id, user_id) VALUES (?, ?)", (self.message_id, interaction.user.id), commit=True)
            if author_data and author_data[0] != interaction.user.id:
                user_info = query_db("SELECT username FROM users WHERE discord_id = ?", (interaction.user.id,), one=True)
                uname = user_info[0] if user_info else interaction.user.display_name
                await send_notification(author_data[0], f"🔁 قام المستخدم `@{uname}` بإعادة نشر تغريدتك في المدينة!")
                
        await interaction.response.defer()
        await self.update_embed(interaction)

    @ui.button(label="رد 💬", style=discord.ButtonStyle.secondary, custom_id="tweet_reply")
    async def reply_click(self, interaction: discord.Interaction, button: ui.Button):
        status = query_db("SELECT comments_open FROM tweets WHERE message_id = ?", (self.message_id,), one=True)
        if status and status[0] == 0:
            return await interaction.response.send_message("❌ خطأ: قام صاحب التغريدة بإغلاق التعليقات لهذه التغريدة مسبقاً!", ephemeral=True)
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
        user_info = query_db("SELECT username FROM users WHERE discord_id = ?", (interaction.user.id,), one=True)
        uname = user_info[0] if user_info else interaction.user.display_name
        
        if is_following:
            query_db("DELETE FROM follows WHERE follower_id = ? AND followed_id = ?", (interaction.user.id, self.target_id), commit=True)
            await interaction.response.send_message("❌ تم إلغاء متابعة الحساب.", ephemeral=True)
        else:
            query_db("INSERT INTO follows (follower_id, followed_id) VALUES (?, ?)", (interaction.user.id, self.target_id), commit=True)
            await send_notification(self.target_id, f"➕ بدأ المستخدم `@{uname}` في متابعة حسابك الآن!")
            await interaction.response.send_message("✅ تم متابعة الحساب بنجاح!", ephemeral=True)

class VerifyActionView(ui.View):
    def __init__(self, target_user_id: int, account_type: str):
        super().__init__(timeout=None)
        self.target_user_id = target_user_id
        self.account_type = account_type
        
    @ui.button(label="قبول العضوية ✅", style=discord.ButtonStyle.success)
    async def approve(self, interaction: discord.Interaction, button: ui.Button):
        query_db("UPDATE users SET verified = 1, account_type = ? WHERE discord_id = ?", (self.account_type, self.target_user_id), commit=True)
        await interaction.response.send_message(f"✅ تم قبول العضوية بنجاح بنوع: **{self.account_type}** وتحديث شارات الحساب!", ephemeral=True)
        await send_notification(self.target_user_id, f"🎉 تهانينا! وافقت الإدارة على طلبك وتم توثيق حسابك كـ **{self.account_type}**")
        await interaction.message.delete()
        
    @ui.button(label="رفض الطلب ❌", style=discord.ButtonStyle.danger)
    async def deny(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_message("❌ تم رفض طلب العضوية بنجاح.", ephemeral=True)
        await interaction.message.delete()

# ==========================================
# 🛑 أوامر السلاش (Slash Commands) والإدارة
# ==========================================

@bot.event
async def on_ready():
    print(f'✅ تم تشغيل البوت بنجاح باسم: {bot.user.name}')
    await bot.change_presence(activity=discord.Game(name="U app | مدينة يو ار جي"))
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
        title="📘 دليل استخدام تطبيق U app المطور",
        description="نظام تويتر المتكامل لمدينة يو ار جي:\n\n"
                    "1️⃣ **القائمة المنسدلة:** تحتوي على إعداد الإشعارات والتحكم الكامل بالملفات والعضويات.\n"
                    "2️⃣ **تقديم العضوية:** يمنحك شارات مخصصة (حكومي 🏛️، تجاري 💼، موثق ☑️).\n"
                    "3️⃣ **حماية التعليقات:** يمكنك التحكم بقفل أو فتح الردود على كل تغريدة تنشرها.\n"
                    "4️⃣ **الإشعارات المباشرة:** تصلك إشعارات تفاعلات حسابك (شاملاً التنبيه عند المنشن) بالخاص تلقائياً.",
        color=discord.Color.blue()
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="تسطيب_البوت", description="إعداد وتجهيز منظومة تويتر رول بلي المحدثة بالكامل (للإدارة)")
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
                    "يمكنك التحكم التام بحسابك والتواصل الرقمي المميز من خلال القائمة المنسدلة بالأسفل 👇",
        color=int(لون_الامبد, 16)
    )
    panel_embed.set_image(url=رابط_صورة_البانل)
    panel_embed.set_footer(text="U app © جميع الحقوق محفوظة لـ مدينة يو ار جي")
    
    await روم_التطبيق.send(embed=panel_embed, view=MainPanelView())
    if خط_السيرفر:
        await روم_التطبيق.send(content=خط_السيرفر) # إرسال خط السيرفر منفصلاً تلقائياً تحت اللوحة الرئيسية
    
    admin_embed = discord.Embed(title="⚙️ لوحة تحكم الإدارة السرية", description="أدوات إدارة وتعديل السيستم وتصفير الحسابات.", color=discord.Color.red())
    await روم_الادارة.send(embed=admin_embed, view=AdminControlView())
    if خط_السيرفر:
        await روم_الادارة.send(content=خط_السيرفر) # إرسال خط السيرفر منفصلاً تلقائياً تحت بانل الإدارة
        
    await interaction.response.send_message("✅ تم إعداد المنظومة بنظام الفصل الجديد للخط، وتصحيح الكلمات الإملائية بنجاح!", ephemeral=True)

@bot.tree.command(name="مطورين", description="عرض معلومات المبرمج المطور للنظام")
async def dev_cmd(interaction: discord.Interaction):
    embed = discord.Embed(
        title="💻 عن المطور",
        description="نظام URG System v2.5\n\nالمبرمج:\n**f_arooq004**\n\nجميع الحقوق محفوظة ©",
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

# تشغيل البوت
token = os.getenv("DISCORD_TOKEN")
if token:
    bot.run(token)
else:
    print("❌ خطأ: لم يتم العثور على المتغير البيئي لتوكن البوت DISCORD_TOKEN!")
