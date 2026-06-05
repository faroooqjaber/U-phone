import discord
from discord.ext import commands
from discord import app_commands, ui
import sqlite3
import os
import re
from datetime import datetime

# ==========================================
# إعدادات البوت والصلاحيات الأساسية ⚙️
# ==========================================
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents)
DB_PATH = "twitter_rp.db"

# ==========================================
# منظومة إدارة قاعدة البيانات 🗄️
# ==========================================
def query_db(query, args=(), one=False, commit=False):
    """دالة مركزية ومستقرة للتعامل مع العمليات داخل قاعدة البيانات"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute(query, args)
        if commit:
            conn.commit()
        res = cursor.fetchone() if one else cursor.fetchall()
        return res
    except Exception as e:
        print(f"[قاعدة البيانات - خطأ]: {e}")
        return None
    finally:
        conn.close()

def setup_db():
    """إنشاء وتحديث الجداول لتتوافق مع كافة رومات وأنظمة الجوال والإدارة"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # إنشاء الجدول الأساسي إذا لم يكن موجوداً
    c.execute('''CREATE TABLE IF NOT EXISTS settings 
        (guild_id INTEGER PRIMARY KEY, 
         app_channel INTEGER, 
         tweet_channel INTEGER, 
         market_channel INTEGER, 
         gram_channel INTEGER, 
         verify_channel INTEGER, 
         admin_role INTEGER, 
         signature TEXT, 
         panel_img TEXT, 
         apps_img TEXT)''')
    conn.commit()
    conn.close()

setup_db()

# ==========================================
# النماذج المنبثقة للتطبيقات (Modals) ✉️
# ==========================================
class TweetModal(ui.Modal, title="🐦 منصة تويتر - تغريدة جديدة"):
    tweet_input = ui.TextInput(
        label="محتوى التغريدة الحالي", 
        style=discord.TextStyle.paragraph, 
        placeholder="اكتب التغريدة التي ترغب بنشرها للعامة هنا...", 
        min_length=5, 
        max_length=600
    )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        data = query_db("SELECT tweet_channel FROM settings WHERE guild_id = ?", (interaction.guild.id,), one=True)
        
        if not data or not data[0]:
            return await interaction.followup.send("❌ لم يتم تحديد روم التغريدات في السيت اب بعد!", ephemeral=True)
        
        channel = interaction.guild.get_channel(data[0])
        if not channel:
            return await interaction.followup.send("❌ تعذر الوصول لروم التغريدات، تأكد من الصلاحيات.", ephemeral=True)
        
        embed = discord.Embed(
            description=f"📢 **تغريدة جديدة:**\n\n{self.tweet_input.value}", 
            color=discord.Color.blue(),
            timestamp=datetime.now()
        )
        embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)
        embed.set_footer(text=f"حساب المواطن الرقمي: {interaction.user.id}")
        
        await channel.send(embed=embed)
        await interaction.followup.send("✅ تم نشر التغريدة بنجاح في الروم المخصص!", ephemeral=True)


class MarketModal(ui.Modal, title="🛒 سوق المدينة - عرض سلعة"):
    item_title = ui.TextInput(label="اسم السلعة / الخدمة", placeholder="مثال: سيارة فراري كلاسيك", min_length=3, max_length=100)
    item_price = ui.TextInput(label="السعر المطلوب أو الميزانية", placeholder="مثال: 45,000$", min_length=1, max_length=30)
    item_desc = ui.TextInput(label="تفاصيل السلعة ووسيلة التواصل", style=discord.TextStyle.paragraph, placeholder="اكتب هنا مواصفات السلعة وكيفية الاتصال بك داخل المدينة...", min_length=10, max_length=500)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        data = query_db("SELECT market_channel FROM settings WHERE guild_id = ?", (interaction.guild.id,), one=True)
        
        if not data or not data[0]:
            return await interaction.followup.send("❌ لم يتم العثور على إعدادات روم السوق الرقمي!", ephemeral=True)
        
        channel = interaction.guild.get_channel(data[0])
        if not channel:
            return await interaction.followup.send("❌ تعذر العثور على روم السوق داخل السيرفر.", ephemeral=True)
        
        embed = discord.Embed(title="🛍️ إعلان تجاري جديد بسوق المدينة", color=discord.Color.gold(), timestamp=datetime.now())
        embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)
        embed.add_field(name="📦 الغرض المُعلن عنه:", value=self.item_title.value, inline=False)
        embed.add_field(name="💰 السعر والتقييم:", value=self.item_price.value, inline=True)
        embed.add_field(name="📝 تفاصيل البيان والتواصل:", value=self.item_desc.value, inline=False)
        
        await channel.send(embed=embed)
        await interaction.followup.send("✅ تم إدراج وعرض السلعة في السوق بنجاح!", ephemeral=True)


class GramModal(ui.Modal, title="📸 يو جرام - مشاركة يوميات"):
    gram_text = ui.TextInput(label="ماذا تفعل الآن؟", style=discord.TextStyle.paragraph, placeholder="شارك المواطنين تفاصيل يومياتك واللحظات الحالية...", min_length=4, max_length=500)
    gram_url = ui.TextInput(label="رابط الصورة (اختياري)", placeholder="https://i.imgur.com/...png", required=False)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        data = query_db("SELECT gram_channel FROM settings WHERE guild_id = ?", (interaction.guild.id,), one=True)
        
        if not data or not data[0]:
            return await interaction.followup.send("❌ روم اليوميات (يو جرام) غير مضبوط بالسيت اب حالياً.", ephemeral=True)
            
        channel = interaction.guild.get_channel(data[0])
        if not channel:
            return await interaction.followup.send("❌ تعذر الوصول لروم اليوميات.", ephemeral=True)
            
        embed = discord.Embed(description=f"✨ **يوميات جديدة:**\n\n{self.gram_text.value}", color=discord.Color.purple(), timestamp=datetime.now())
        embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)
        
        if self.gram_url.value and (self.gram_url.value.startswith("http://") or self.gram_url.value.startswith("https://")):
            embed.set_image(url=self.gram_url.value)
            
        await channel.send(embed=embed)
        await interaction.followup.send("✅ تم نشر لقطة من يومياتك في يو جرام بنجاح!", ephemeral=True)


class ApplyMembershipModal(ui.Modal, title="📝 استمارة تقديم عضوية المدينة"):
    full_name = ui.TextInput(label="الاسم الكامل والشخصية (IC)", placeholder="مثال: عمر الراشدي", min_length=3, max_length=80)
    age_ic = ui.TextInput(label="العمر الحقيقي وعمر الشخصية", placeholder="مثال: 19 سنة / 25 سنة", min_length=2, max_length=40)
    reason_app = ui.TextInput(label="لماذا ترغب بالانضمام إلينا؟", style=discord.TextStyle.paragraph, placeholder="اكتب بالتفصيل أهدافك وخبراتك السابقة داخل الـ Roleplay...", min_length=15, max_length=600)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        data = query_db("SELECT verify_channel FROM settings WHERE guild_id = ?", (interaction.guild.id,), one=True)
        
        if not data or not data[0]:
            return await interaction.followup.send("❌ نظام رومات تقديم العضويات غير مفعل عبر السيت اب بعد!", ephemeral=True)
            
        channel = interaction.guild.get_channel(data[0])
        if not channel:
            return await interaction.followup.send("❌ تعذر العثور على روم تقديم العضويات المحدد للإدارة.", ephemeral=True)
            
        embed = discord.Embed(title="📥 طلب تقديم عضوية جديد قيد المراجعة والتدقيق", color=discord.Color.teal(), timestamp=datetime.now())
        embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)
        embed.add_field(name="👤 اسم المتقدم الكامل:", value=self.full_name.value, inline=False)
        embed.add_field(name="📅 فئات الأعمار المطروحة:", value=self.age_ic.value, inline=True)
        embed.add_field(name="📜 السيرة الذاتية والخبرات والمبررات:", value=self.reason_app.value, inline=False)
        embed.set_footer(text=f"صاحب الاستمارة ID: {interaction.user.id}")
        
        # ربط واجهة الأزرار التفاعلية الخاصة بالإدارة لقبول أو رفض الطلب
        view = ui.View(timeout=None)
        view.add_item(ui.Button(label="قبول الطلب وتوثيقه ✅", style=discord.ButtonStyle.success, custom_id=f"verify_accept_{interaction.user.id}"))
        view.add_item(ui.Button(label="رفض الطلب الحالي ❌", style=discord.ButtonStyle.danger, custom_id=f"verify_reject_{interaction.user.id}"))
        
        await channel.send(embed=embed, view=view)
        await interaction.followup.send("✅ تم رفع استمارة طلب العضوية الخاصة بك بنجاح إلى لجنة المسؤولين والأكاديمية!", ephemeral=True)

# ==========================================
# واجهات التحكم والشاشات التفاعلية (UI) 📱
# ==========================================
class MobileAppSelect(ui.Select):
    """القائمة المنسدلة لاختيار وفتح تطبيقات الهاتف الداخلي دون تداخل"""
    def __init__(self):
        options = [
            discord.SelectOption(label="منصة تويتر المدينة", value="open_tw", emoji="🐦", description="لفتح واجهة كتابة ونشر التغريدات للمواطنين"),
            discord.SelectOption(label="سوق المدينة التجاري", value="open_mk", emoji="🛒", description="لعرض منتج أو سيارة أو خدمة للبيع العام"),
            discord.SelectOption(label="تطبيق يو جرام (اليوميات)", value="open_gr", emoji="📸", description="لنشر لقطات ويومياتك المصورة للجمهور"),
            discord.SelectOption(label="تقديم طلب عضوية رسمي", value="open_ap", emoji="📝", description="لتعبئة نموذج استمارة العضوية وإرساله للإدارة"),
            discord.SelectOption(label="إغلاق وقفل الهاتف", value="phone_exit", emoji="❌", description="لإغلاق شاشة الهاتف وتوفير استهلاك البيانات")
        ]
        super().__init__(placeholder="📱 اضغط هنا واختـر التطبيق لتشغيله...", options=options, custom_id="mobile_main_dropdown")
        
    async def callback(self, interaction: discord.Interaction):
        app_choice = self.values[0]
        
        if app_choice == "phone_exit":
            try:
                await interaction.message.delete()
            except:
                await interaction.response.send_message("❌ انتهت صلاحية تفاعل الإغلاق، يمكنك إخفاء الرسالة يدوياً.", ephemeral=True)
            return

        # فتح المودال المناسب بناء على الاختيار مباشرة لتفادي الـ Defer Error
        if app_choice == "open_tw":
            await interaction.response.send_modal(TweetModal())
        elif app_choice == "open_mk":
            await interaction.response.send_modal(MarketModal())
        elif app_choice == "open_gr":
            await interaction.response.send_modal(GramModal())
        elif app_choice == "open_ap":
            await interaction.response.send_modal(ApplyMembershipModal())


class PhoneHomeScreenView(ui.View):
    """واجهة العرض الداخلية للهاتف الذكي"""
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(MobileAppSelect())


class StartPhoneView(ui.View):
    """الزر الخارجي المعتمد بداخل الروم لبدء تشغيل واجهة الجوال الشخصية"""
    def __init__(self):
        super().__init__(timeout=None)
        
    @ui.button(label="تشغيل الجوال 📱", style=discord.ButtonStyle.primary, custom_id="trigger_phone_boot")
    async def boot_phone(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.defer(ephemeral=True)
        img_data = query_db("SELECT apps_img FROM settings WHERE guild_id = ?", (interaction.guild.id,), one=True)
        
        # النص التوضيحي الذي يظهر فوق صورة شاشة التطبيقات الداخلية لشرح الموضوع بالكامل
        instructions_text = (
            "📱 **مرحباً بك في نظام تشغيل التطبيقات الرقمي الموحد**\n"
            "لقد قمت بفتح هاتفك المحمول بنجاح. يرجى اختيار أحد التطبيقات المتاحة بالمدينة "
            "عبر القائمة المنسدلة بالأسفل لإجراء العمليات والنشر الفوري:"
        )
        
        embed = discord.Embed(title="📱 شاشة التطبيقات الذكية", color=discord.Color.from_rgb(32, 32, 32))
        if img_data and img_data[0]:
            embed.set_image(url=img_data[0])
            
        await interaction.followup.send(content=instructions_text, embed=embed, view=PhoneHomeScreenView(), ephemeral=True)

# ==========================================
# الأوامر والعمليات البرمجية الأساسية (Slash Commands) 🤖
# ==========================================
@bot.tree.command(name="تسطيب_الجوال", description="إعداد وتهيئة منظومة الجوال بالكامل وروماتها وصلاحياتها")
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
                    صورة_الشاشة_الداخلية: str):
    
    await interaction.response.defer(ephemeral=True)
    
    # حفظ كامل التعديلات والرومات الجديدة في قاعدة البيانات
    query_db('''INSERT OR REPLACE INTO settings 
                (guild_id, app_channel, tweet_channel, market_channel, gram_channel, verify_channel, admin_role, signature, panel_img, apps_img) 
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
             (interaction.guild.id, روم_الجوال.id, روم_التغريدات.id, روم_السوق.id, روم_اليوميات.id, روم_التقديمات.id, رتبة_المسؤولين.id, توقيع_الخط, صورة_الغلاف, صورة_الشاشة_الداخلية), 
             commit=True)
    
    # النص التوضيحي الشامل الذي يظهر فوق الصورة الأساسية للبانل لشرح الموضوع للعامة
    main_panel_text = (
        "🤖 **مركز تفعيل الخدمات والأنظمة الرقمية لمدينة URG**\n"
        "من خلال النقر على زر التشغيل المتواجد أسفل الرسالة، يمكنك تفعيل واجهة جوالك الذكي واستخدام منصات التواصل والخدمات المختلفة.\n"
        "💡 *ملاحظة: واجهة استخدام الهاتف تظهر لك بشكل سري وخاص بالكامل (Ephemeral) دون إزعاج بقية الأعضاء.*"
    )
    
    embed = discord.Embed(title="URG | Digital System Gateway", color=discord.Color.red())
    embed.set_image(url=صورة_الغلاف)
    
    # إرسال البانل الرئيسي داخل روم الجوال المحدد مع التوقيع والخط التلقائي
    await روم_الجوال.send(content=main_panel_text, embed=embed, view=StartPhoneView())
    if توقيع_الخط:
        await روم_الجوال.send(content=توقيع_الخط)
        
    await interaction.followup.send("✅ تم إعداد وتهيئة منظومة الجوال بالكامل وربط كافة رومات الإدارة والتطبيقات بنجاح!", ephemeral=True)


@bot.tree.command(name="المطورين", description="عرض بيانات ومعلومات مبرمجي ومطوري النظام")
async def dev_cmd(interaction: discord.Interaction):
    """أمر المطورين المطابق لشاشة العرض والـ Embed الظاهر بالسيرفر"""
    embed = discord.Embed(
        title="💻 عن المطور", 
        description="تم تطوير هذا البوت وبرمجته بشكل خاص لخدمة نظام URG.\n\nالمبرمج:\n**f_arooq004**", 
        color=discord.Color.dark_grey()
    )
    embed.set_footer(text="URG System | Copyright ©")
    await interaction.response.send_message(embed=embed)

# ==========================================
# نظام معالجة الأحداث والخط التلقائي والتحقق (Events) 🛡️
# ==========================================
@bot.event
async def on_message(message):
    """نظام طباعة وإرسال الخط والتوقيع التلقائي بعد الرسائل بداخل رومات الهاتف المعتمدة"""
    if message.author.bot:
        return
        
    if message.guild is None:
        return

    # جلب الإعدادات وفحص الرومات الحالية
    db_data = query_db("SELECT app_channel, tweet_channel, market_channel, gram_channel, verify_channel, signature FROM settings WHERE guild_id = ?", (message.guild.id,), one=True)
    if db_data:
        app_ch, tw_ch, mk_ch, gr_ch, vf_ch, signature_text = db_data
        
        # في حال كانت الرسالة مرسلة بداخل رومات التطبيقات وبها خط مسجل بالسيت اب
        if message.channel.id in [app_ch, tw_ch, mk_ch, gr_ch, vf_ch] and signature_text:
            # التحقق لضمان عدم تكرار إرسال التوقيع إذا كان هو محتوى الرسالة الفعلي
            if message.content.strip() != signature_text.strip():
                await message.channel.send(content=signature_text)
                
    await bot.process_commands(message)


@bot.event
async def on_interaction(interaction: discord.Interaction):
    """معالج أحداث ضغطات أزرار القبول والرفض لعضويات التقديم مع فحص رتبة مسؤولين الجوال لمنع التداخل"""
    custom_id = interaction.data.get("custom_id", "")
    
    if custom_id.startswith("verify_accept_") or custom_id.startswith("verify_reject_"):
        await interaction.response.defer(ephemeral=True)
        
        # جلب رتبة المسؤولين المخزنة مسبقاً
        data = query_db("SELECT admin_role FROM settings WHERE guild_id = ?", (interaction.guild.id,), one=True)
        if not data or not data[0]:
            return await interaction.followup.send("❌ خطأ: لم يتم تعيين رتبة مسؤولي الجوال في إعدادات البوت!", ephemeral=True)
            
        required_role_id = data[0]
        required_role = interaction.guild.get_role(required_role_id)
        
        # فحص صلاحية رتبة الإدارة بشكل صارم
        if not required_role or required_role not in interaction.user.roles:
            return await interaction.followup.send("❌ عذراً، هذا الإجراء مخصص فقط للجنة الإدارة والمسؤولين المخولين بالجوال!", ephemeral=True)
            
        # استخراج آيدي العضو صاحب الاستمارة وطبيعة الإجراء
        applicant_id = custom_id.split("_")[-1]
        action_type = "قبول" if "accept" in custom_id else "رفض"
        
        # تحديث وتعديل استمارة التقديم بداخل روم الإدارة مع تعطيل الأزرار لمنع التلاعب
        old_embed = interaction.message.embeds[0]
        final_color = discord.Color.green() if action_type == "قبول" else discord.Color.red()
        
        new_embed = discord.Embed(title=f"🗳️ قرار رسمي بشأن الاستمارة (تم {action_type} الطلب)", color=final_color)
        for field in old_embed.fields:
            new_embed.add_field(name=field.name, value=field.value, inline=field.inline)
            
        new_embed.add_field(name="👮 مسؤول القرار المتخذ:", value=f"{interaction.user.mention} ({interaction.user.id})", inline=False)
        new_embed.set_footer(text=f"القرار النهائي | مقدم الطلب ID: {applicant_id}")
        
        # محاولة مراسلة العضو في الخاص لإشعاره بقرار الإدارة تلقائياً
        try:
            member_user = await bot.fetch_user(int(applicant_id))
            if member_user:
                dm_embed = discord.Embed(
                    title="📣 نتيجة طلب العضوية الخاص بك", 
                    description=f"أهلاً بك، نود إعلامك بأنه قد تم **{action_type}** طلبك للانضمام لعضوية المدينة من قبل لجنة المسؤولين بنجاح.", 
                    color=final_color
                )
                await member_user.send(embed=dm_embed)
        except Exception as dm_err:
            print(f"[الخاص] تعذر إرسال رسالة التنبيه للعضو: {dm_err}")

        await interaction.message.edit(embed=new_embed, view=None)
        await interaction.followup.send(f"✅ تم تسجيل عملية {action_type} الاستمارة بنجاح وتحديث البيان وإخطار العضو!", ephemeral=True)


@bot.event
async def on_ready():
    """تجهيز وتثبيت الـ Views التفاعلية الثابتة والمستمرة بالذاكرة لضمان استقرار الأزرار"""
    bot.add_view(StartPhoneView())
    bot.add_view(PhoneHomeScreenView())
    await bot.tree.sync()
    print("==================================================")
    print(f"🤖 البوت مسجل وشغال بنجاح باسم: {bot.user}")
    print("🚀 نظام الجوال المستقر لمدينة URG جاهز وتحت أمرك يا فاروق!")
    print("==================================================")

# ==========================================
# تشغيل البوت عبر المتغيرات البيئية للاستضافة 🌐
# ==========================================
token = os.getenv("DISCORD_TOKEN")
if token:
    bot.run(token)
else:
    print("❌ (! لم يتم العثور على التوكن في البيئة المستضيفة للبرنامج)")
