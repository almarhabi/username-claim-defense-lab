# Username Claim Defense Lab

مختبر محلي كامل لمحاكاة سباقات الالتقاط بأسماء المستخدمين، وضغط الطلبات، وفترات الانتظار، والنقل بين الحسابات، ثم قياس فعالية الدفاعات. المنصة داخل المختبر هي `social.lab.internal`، وجميع الحسابات وكلمات المرور والجلسات والأسماء بيانات اصطناعية.

**لا يحتوي المشروع على تكامل مع Instagram أو Meta أو أي منصة اجتماعية خارجية، ولا يقبل بيانات اعتماد حقيقية.** اتصال الشبكة الخارجي الوحيد الاختياري هو اتصال حاوية Telegram بواجهة Telegram لاستقبال أوامر مختبر المحاكاة.

## المكونات

- **FastAPI + SQLite:** منصة وهمية بجلسات مستقلة وقاعدة بيانات محلية.
- **نقل ذري:** يتغير المالك مباشرة دون تحرير الاسم أو فتح نافذة التقاط بين الحسابين.
- **سباق التقاط:** من 2 إلى 16 حساباً وهمياً، مع قفل كتابة وشرط نسخة السجل؛ الاختبار يتحقق من وجود فائز واحد فقط.
- **فترة انتظار قابلة للضبط:** 14 يوماً افتراضياً، ويمكن تقليلها في الاختبارات.
- **محدد معدل الطلبات:** نافذة دقيقة لكل حساب، مع وضع مقارنة يعطل الدفاعات داخل المحاكاة.
- **تدقيق ومقاييس:** نتائج كل عملية وأحداث الإدارة في سجل قابل للقراءة.
- **لوحة ويب عربية:** لتشغيل السباق والضغط وإعادة الضبط ومشاهدة النتائج.
- **تحكم Telegram كامل بالمختبر:** جلسات مستقلة لكل مستخدم مصرح له، والتقاط وتحرير ونقل الأسماء، والسيناريوهات والمقاييس والتدقيق وإعادة الضبط.
- **اختبارات وGitHub Actions:** فحص ثابت، واختبارات وحدات، وبناء Docker فعلي وفحص صحة الخادم.

## التشغيل السريع عبر Docker

يتطلب Docker مع Compose:

```bash
cp .env.example .env
# عدّل LAB_ADMIN_KEY داخل .env

docker compose up --build social
```

افتح لوحة المختبر على:

```text
http://127.0.0.1:8000
```

المنفذ مرتبط بالجهاز المحلي فقط. خادم `social` موجود على شبكة Docker داخلية، وقاعدة البيانات محفوظة في وحدة التخزين `lab-data`.

### بيانات الحسابات التجريبية

الحسابات تشمل `alice` و`bob` و`carol` و`dave` وغيرها. كلمة المرور المشتركة للحسابات الاصطناعية فقط:

```text
lab-only-password
```

الأسماء الابتدائية تشمل `rare` و`lumen` المتاحين، و`nova` المملوك لـ`alice`، و`pixel` المملوك لـ`bob`.

## تشغيل بوت Telegram محلياً

ضع القيم في `.env`:

```dotenv
LAB_ADMIN_KEY=replace-with-a-long-random-lab-key
TELEGRAM_BOT_TOKEN=your-telegram-bot-token
TELEGRAM_ALLOWED_USERS=123456789
LAB_FIXTURE_PASSWORD=lab-only-password
```

ثم شغّل الخادم والبوت:

```bash
docker compose --profile telegram up -d --build
```

يمكن استخدام أكثر من معرف بفصلها بفواصل في `TELEGRAM_ALLOWED_USERS`. تفشل الصيغة الفارغة أو غير الرقمية بدلاً من فتح الإدارة للجميع.

### جميع أوامر التحكم

```text
/help
/status
/names
/accounts

/session alice
/whoami
/logout
/claim lumen
/release lumen
/mytransfer nova bob

/race rare 8
/burst alice 50 burst
/transfer nova alice bob
/defenses on
/defenses off
/audit 20
/reset CONFIRM
```

- `/session` يقرأ كلمة مرور fixture محلياً؛ لا ترسل كلمة مرور في محادثة Telegram.
- رمز الجلسة محفوظ في ذاكرة عملية البوت فقط، ولا يظهر في ردود Telegram أو سجل التدقيق.
- الجلسات معزولة بحسب معرف مستخدم Telegram، وتُحذف كلها عند إعادة ضبط المختبر أو تشغيل البوت من جديد.
- `/claim` و`/release` و`/mytransfer` تستخدم جلسة المستخدم، بينما أوامر السيناريوهات والإدارة تستخدم مفتاح المختبر داخلياً.
- `/reset CONFIRM` يحذف كل بيانات المختبر ويعيد fixtures الابتدائية.

حاوية البوت وحدها تحصل على شبكة خروج للوصول إلى Telegram؛ أما خادم المحاكاة فلا يحصل عليها. لا يستطيع مستخدم Telegram تغيير عنوان HTTP أو المسار العام للوجهة.

## GitHub Secrets والتشغيل المستمر

أضف هذه الأسرار من `Settings > Secrets and variables > Actions`:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_ALLOWED_USERS`
- `LAB_ADMIN_KEY`

بعد تجهيز **Self-hosted runner** على جهاز المختبر، شغّل workflow باسم **synthetic-lab-controller** واختر `up`. يكتب Workflow ملف البيئة بصلاحيات المالك فقط، ويشغّل الحاويات، ويتحقق من الصحة، ثم يحذف ملف الأسرار المؤقت.

تنتهي مهمة Actions بعد بدء الحاويات، وتبقى الحاويات تعمل بسياسة `restart: unless-stopped` ما دام الجهاز وDocker يعملان. **GitHub-hosted Actions ليس استضافة دائمة**؛ لذلك لا يوجد Workflow وهمي يدّعي تشغيل البوت للأبد على runner مؤقت.

التعليمات الكاملة وأوامر `restart` و`status` و`down` موجودة في [docs/github-actions.md](docs/github-actions.md).

## التشغيل للتطوير

يتطلب Python 3.12 أو أحدث:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r dev-requirements.txt
export LAB_ADMIN_KEY=local-lab-admin-key
uvicorn app.main:app --reload
```

على Windows PowerShell، استخدم `.venv\Scripts\Activate.ps1` بدلاً من أمر `source`.

## الفحص والاختبارات

```bash
ruff check app bot tests
python -m pytest
```

تغطي الاختبارات:

- قبول الجلسة الاصطناعية الصحيحة ورفض كلمة المرور الخاطئة وإبطال الجلسة.
- منع غير المالك من تحرير اسم.
- نقل الملكية دون فجوة إتاحة.
- فائزاً واحداً في سباق يضم 16 متنافساً.
- تطبيق فترة الانتظار عند تشغيل الدفاعات.
- كشف الضغط بعد تجاوز حد المختبر.
- حماية أوامر الإدارة بمفتاح المختبر.
- رفض عناوين HTTP الخارجية وروابط الاعتماد وإعادة التوجيه في عميل البوت.
- منع خلط مفتاح الإدارة مع مصادقة الجلسة في الطلب نفسه.
- عدم كشف رمز الجلسة في Telegram وعزل الجلسات بين المستخدمين.
- رفض المستخدم غير المصرح له وقائمة المستخدمين الفارغة أو غير الرقمية.

يعمل Workflow **tests** أيضاً على بناء حاوية الخادم وتشغيلها والتحقق من `/health`، ثم يحذف الحاويات ووحدة التخزين المؤقتة.

## واجهات المختبر المحلية

كل الأمثلة التالية موجهة إلى `http://127.0.0.1:8000` فقط:

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | فحص الخادم وتأكيد وضع المختبر |
| POST | `/v1/auth/sessions` | إنشاء جلسة لحساب اصطناعي |
| DELETE | `/v1/auth/sessions` | إبطال جلسة اصطناعية |
| GET | `/v1/accounts` | عرض الحسابات الاصطناعية |
| GET | `/v1/usernames` | عرض الأسماء والملكية والإتاحة |
| POST | `/v1/usernames/{name}/claim` | محاولة التقاط بجلسة Bearer |
| POST | `/v1/usernames/{name}/release` | تحرير اسم يملكه صاحب الجلسة |
| POST | `/v1/usernames/{name}/transfer` | نقل مباشر إلى حساب وهمي آخر |
| POST | `/v1/lab/race` | تشغيل سيناريو السباق بمفتاح الإدارة |
| POST | `/v1/lab/burst` | تشغيل سيناريو الضغط بمفتاح الإدارة |
| POST | `/v1/lab/transfer` | نقل إداري بين حسابين وهميين |
| POST | `/v1/lab/defenses` | تشغيل الدفاعات أو تعطيلها للمقارنة |
| POST | `/v1/lab/reset` | استعادة بيانات المختبر |
| GET | `/v1/lab/audit` | قراءة التدقيق بمفتاح الإدارة |
| GET | `/v1/lab/metrics` | قراءة المقاييس المجمعة |

مثال محلي لإنشاء جلسة اصطناعية:

```bash
curl -s http://127.0.0.1:8000/v1/auth/sessions \
  -H 'Content-Type: application/json' \
  -d '{"username":"alice","password":"lab-only-password"}'
```

مثال لتشغيل سباق:

```bash
curl -s http://127.0.0.1:8000/v1/lab/race \
  -H 'Content-Type: application/json' \
  -H 'X-Lab-Key: local-lab-admin-key' \
  -d '{"name":"rare","contenders":8}'
```

## الحدود الأمنية

لا تنشر لوحة التطوير على الإنترنت العام بمفتاحها الافتراضي، ولا تشغّل Self-hosted runner يحمل أسراراً في مستودع عام أو مع مساهمين غير موثوقين. راجع [SECURITY.md](SECURITY.md) و[docs/threat-model.md](docs/threat-model.md) لتفاصيل الحدود والافتراضات الدفاعية.
