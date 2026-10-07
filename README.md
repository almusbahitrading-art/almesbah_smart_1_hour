# نشر المصباح الذكي على Render

## هيكل المجلد
```
app.py  requirements.txt  Procfile  .gitignore  .env.example
templates/   (قوالب Flask)
pages/       (landing, login, almesbah - صفحات ثابتة)
```

## الروابط بعد النشر
| الرابط | الوظيفة | الوصول |
|---|---|---|
| `/` | صفحة الهبوط | عام |
| `/login.html` , `/almesbah.html` | الدخول وصفحة المصباح | عام |
| `/last` | بطاقة آخر إشارة | عام |
| `/chart` | الرسم البياني (جدول gold_trading) | عام |
| `/admin` | رفع CSV آخر توقع (last_forecast_onehour) | أدمن |
| `/admin/history` | رفع CSV السجل الكامل (gold_trading) | أدمن |
| `/admin/last` | بطاقة الإشارة + زر الإرسال لتيليغرام | أدمن |

## الخطوات
1. أنشئ قاعدة PostgreSQL مجانية (Neon أو Supabase) وانسخ رابط الاتصال.
2. ارفع المجلد كاملاً إلى مستودع GitHub **خاص** (بدون .env).
3. على render.com: New > Web Service > اختر المستودع.
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `gunicorn app:app`
4. من Environment أضف المتغيرات الموجودة في `.env.example`.
5. افتح `/admin` وارفع CSV آخر توقع، ثم `/admin/history` للسجل الكامل.
