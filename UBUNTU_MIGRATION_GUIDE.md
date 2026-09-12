# 🐧 دليل تثبيت وتشغيل منظومة أمان الرافعات الشوكية على Ubuntu 24.04 LTS
# Industrial Deployment & Migration Guide — Limitless Future AI Forklift Safety

هذا الدليل مخصص لتهيئة وتثبيت وتشغيل المنظومة كجهاز صناعي مستقل (**Industrial Appliance / Kiosk**) على أي جهاز كمبيوتر مدمج (Micro-PC / Rugged Industrial PC) يعمل بنظام **Ubuntu 24.04 LTS**.

---

## 🛠️ المتطلبات التقنية الأساسية (Prerequisites)

1. **نظام التشغيل:** Ubuntu 24.04 LTS (يفضل بيئة X11 Kiosk).
2. **العتاد المطلوب:**
   - معالج رباعي النواة (Intel i5/i7 أو AMD Ryzen أو معالجات ARM الصناعية المتوافقة).
   - ذاكرة عشوائية (RAM): 8GB كحد أدنى.
   - كارت ريلاي رباعي القنوات: **RM04U 4-Channel USB Relay** (شريحة CH340).
   - ما يصل إلى 4 كاميرات صناعية تدعم معيار V4L2 (USB 2.0 / USB 3.0).
   - شاشة لمس صناعية بدقة 800x480 حتى 4K UHD.

---

## 📦 الخطوة 1: تثبيت حزم نظام لينكس (System Dependencies)

افتح الطرفية (`Ctrl+Alt+T`) ونفّذ الأوامر التالية لتثبيت حزم بايثون ومكتبات الجرافيك ومعالجة الفيديو لـ OpenCV و PyQt5:

```bash
# تحديث المستودعات وحزم النظام
sudo apt update && sudo apt upgrade -y

# تثبيت بايثون وأداة venv ومدير الحزم Git
sudo apt install -y python3 python3-pip python3-venv git

# تثبيت مكتبات النظام الرسومية الخاصة بـ PyQt5 و OpenCV
sudo apt install -y libgl1-mesa-glx libglib2.0-0 libxcb-xinerama0 libegl1-mesa libxkbcommon-x11-0 libdbus-1-3
```

---

## 📁 الخطوة 2: استنساخ المشروع وإعداد البيئة الافتراضية

```bash
# الانتقال إلى سطح المكتب أو مسار العمل
cd ~/Desktop

# استنساخ المشروع من GitHub (أو نسخ المجلد)
git clone https://github.com/<YOUR_ORGANIZATION>/AI_Forklift_Safety.git
cd AI_Forklift_Safety

# إنشاء بيئة افتراضية مخصصة للينكس
python3 -m venv venv

# تفعيل البيئة الافتراضية
source venv/bin/activate

# ترقية أداة pip وتثبيت متطلبات بايثون بالكامل
pip install --upgrade pip
pip install -r requirements.txt
```

---

## 🔌 الخطوة 3: ضبط أذونات USB وقواعد udev لكارت الريلاي

يحتاج نظام لينكس إلى منح المستخدم صلاحيات الوصول للمنفذ التسلسلي، وتثبيت رابط دائم للمنفذ `/dev/forklift_relay`:

```bash
# إضافة المستخدم الحالي إلى مجموعة dialout للوصول للمنافذ التسلسلية
sudo usermod -aG dialout $USER

# تفعيل قاعدة udev الخاصة بالريلاي (شريحة CH340: Vendor 1a86, Product 7523)
chmod +x setup_usb.sh
./setup_usb.sh
```

> **ملاحظة:** يلزم تسجيل الخروج وإعادة الدخول (أو إعادة تشغيل الجهاز) لتفعيل صلاحية مجموعة `dialout`.

---

## ⚙️ الخطوة 4: تفعيل خدمة النظام المستقلة (Systemd User Service)

يعمل النظام في بيئة الإنتاج كخدمة مستخدم مراقبة (`systemd user service`) مع استرداد ذاتي خلال 3 ثوانٍ وحماية من التشغيل المزدوج:

```bash
# إنشاء مجلد خدمات المستخدم إذا لم يكن موجوداً
mkdir -p ~/.config/systemd/user

# نسخ ملف الخدمة إلى مسار خدمات المستخدم
cp forklift-ai.service ~/.config/systemd/user/

# إعادة تحميل إعدادات Systemd للمستخدم
systemctl --user daemon-reload

# تمكين الخدمة لتعمل تلقائياً عند الإقلاع
systemctl --user enable forklift-ai.service

# تشغيل الخدمة فوراً
systemctl --user start forklift-ai.service
```

### إدارة ومراقبة الخدمة:
```bash
# التحقق من حالة الخدمة الحية
systemctl --user status forklift-ai.service

# متابعة السجلات الموحدة (Live Logs)
journalctl --user -u forklift-ai.service -f

# إعادة تشغيل الخدمة يدوياً
systemctl --user restart forklift-ai.service
```

---

## 🖥️ الخطوة 5: إضافة اختصار سطح المكتب والتشغيل المباشر

تم تجهيز اختصار سطح المكتب `AI_Forklift_System.desktop` لتشغيل النظام بسهولة بنقرة واحدة:

```bash
# منح صلاحيات التنفيذ لملف الإقلاع والاختصار
chmod +x start_system.sh
chmod +x AI_Forklift_System.desktop

# نسخ الاختصار إلى سطح المكتب
cp AI_Forklift_System.desktop ~/Desktop/
gio set ~/Desktop/AI_Forklift_System.desktop metadata::trusted true
```

### التشغيل اليدوي المباشر من الطرفية:
```bash
# التشغيل القياسي مع مهلة 15 ثانية لاستقرار منافذ USB
./start_system.sh

# التشغيل السريع لتجارب التطوير (تخطي مهلة الـ 15 ثانية)
./start_system.sh --no-delay
```

---

## 🧪 الخطوة 6: تشغيل حزم الاختبارات والتحقق البرمجي

للتأكد من سلامة كافة أجزاء النظام بعد التثبيت، نفّذ حزم الاختبارات المستقلة:

```bash
source venv/bin/activate

# 1. اختبار منطق بوابة OR للريلاي والأزمنة الميكروثانية
python3 test_or_gate_logic.py -v

# 2. اختبار ربط مسارات منافذ USB الفيزيائية لمنع تبديل الكاميرات
python3 scratch/test_physical_usb_binding.py -v
```

---

## 🎯 بنية الحماية الصناعية المطبقة في النظام

1. **معمارية العمليتين المنفصلتين (Two-Process Architecture):**
   - خادم العتاد `hardware_worker.py` يعمل في الخلفية ويتحكم بالريلاي عبر مقبس `/dev/shm/forklift_relay.sock`.
   - الواجهة الرسومية `ai_gui_system.py` معزولة تماماً، وتوقف الواجهة لا يسبب تعليق السارينة أو إيقاف الأمان.
2. **الربط الفيزيائي لمنافذ USB (Physical USB Hub Topology Binding):**
   - ترتبط كل كاميرا بالمسار الفيزيائي للمنفذ في المذربورد لمنع تبديل الكاميرات عند الاهتزاز أو إعادة الإقلاع.
3. **نظام الإحداثيات النسبية (Normalized ROI):**
   - حفظ مناطق الخطر بنسب معيارية (`0.0 - 1.0`) لضمان عدم انزياح الصندوق عند تغيير مقاس الشاشة أو النافذة.
4. **لوحة المفاتيح الافتراضية (OSK):**
   - دعم كامل للشاشات اللمسية دون الحاجة لفأرة أو لوحة مفاتيح فيزيائية.