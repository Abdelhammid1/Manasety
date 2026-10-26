"""Initial content: the approved design copy, the claim-registry features, and the inventory of
what runs on manasety.ai today. Idempotent — existing rows are never overwritten.

Records whose facts are not confirmed yet (client names, 2000+ / 400+ numbers) are created
*hidden*: the publishing rules keep them off the site until consent / source is recorded."""
from __future__ import annotations

import re
import shutil
from datetime import date
from pathlib import Path
from typing import Any

from flask import current_app

from .extensions import db
from .models import (Author, CaseStudy, Category, Client, DisplayFile, Fact, FaqItem, Feature, Integration, LegalPage,
                     Page, Redirect, Section)
from .publishing import publish_page
from .security import clean_legal

STAGES = "ابتدائي\nمتوسط\nثانوي\nمجمع تعليمي كامل (ابتدائي، متوسط، ثانوي)\nمعهد تدريب / لغات\nأخرى"
BUSINESS_TYPES = ("مدرسة خاصة / أهلية / عالمية\nمعهد تدريب وتأهيل\nمدرسة / جمعية تحفيظ قرآن\n"
                  "نشاط تجاري أو شركة ترغب بسوفتوير مخصص")


def _sec(block_type: str, label: str, anchor: str, ar: dict[str, Any]) -> dict:
    return {"block_type": block_type, "admin_label": label, "anchor": anchor, "content": {"ar": ar, "en": {}}}


HOME_SECTIONS = [
    _sec("hero", "Hero", "top", {
        "badge": "الجيل السحابي المتكامل لإدارة المدارس والتعليم الذكي",
        "title": "نظام واحد لمدرستك كلها.",
        "title_highlight": "وكل موديول تحتاجه يُفعَّل بضغطة زر.",
        "subtitle": "من القبول والحضور إلى الدرجات والفواتير والرواتب، ومعها ذكاء اصطناعي يوفّر وقت المعلم، كلها بهوية مدرستك.",
        "cta_primary_label": "احجز عرضًا توضيحيًا", "cta_primary_href": "#contact",
        "cta_secondary_label": "شاهد المميزات", "cta_secondary_href": "#features",
        "proof_line": "مُجرَّب في مدارس ومعاهد حقيقية.", "image": None, "show_files": False,
    }),
    _sec("cards", "المشكلة", "problem", {
        "eyebrow": "التحدي القائم في المدارس",
        "title": "مدرستك تعمل بخمس أدوات، وأنت تدفع ثمن إعادة إدخال البيانات.",
        "subtitle": "تعدد البرامج المنفصلة يخلق جزر بيانات معزولة، ويهدر أوقات الكادر الإداري والتعليمي في تكرار العمليات والمطابقة اليدوية.",
        "variant": "problem",
        "items": [
            {"icon": "table", "title": "ملفات الطلاب مشتتة بين Excel والورق",
             "text": "بيانات القبول، المستندات الرسمية، وسجلات أولياء الأمور موزعة بين ملفات متناثرة يصعب تحديثها أو الوصول الموحد إليها."},
            {"icon": "wallet", "title": "حسابات ومصروفات في برنامج محاسبي منفصل",
             "text": "محاسب المدرسة يضطر لمراجعة كشوفات الغياب والرسوم والخصومات يدويًا لإنشاء فواتير الأقساط ومطابقة التحويلات البنكية."},
            {"icon": "help-square", "title": "تعليم إلكتروني واختبارات في منصة منعزلة",
             "text": "المعلم ينشئ الواجبات على نظام خارجي، ثم يعيد تفريغ الدرجات في سجلات التقويم الرسمية ورصد الشهادات."},
            {"icon": "clipboard-clock", "title": "جداول مدرسية وتقارير تُجمع يدويًا وتهدر الساعات",
             "text": "إعداد جداول الحصص، بدائل المعلمين، وتقارير أداء الفصول تستنزف أيام عمل متواصلة من مديري المدارس والوكلاء."},
        ],
    }),
    _sec("cards", "الحل: نظام واحد", "solution", {
        "eyebrow": "منظومة موحدة بقاعدة بيانات واحدة",
        "title": "الطلاب والتقييم والتعلم والمالية والموارد البشرية على نفس البيانات.",
        "subtitle": "نواة واحدة تلغي تكرار الإدخال، وتمنح الإدارة والمعلم وولي الأمر رؤية 360 درجة فورية ومتزامنة.",
        "variant": "solution",
        "items": [
            {"icon": "user-check", "title": "شؤون الطلاب والأكاديمي والحضور الذكي",
             "text": "إدارة متكاملة لملفات الطلاب من التقديم حتى التخرج، مع رصد ذكي للحضور اليومي وبالحصة، وتتبع فوري للسلوك والمواظبة."},
            {"icon": "star", "title": "التقييم بالروبريك وسلالم الدرجات الموزونة",
             "text": "معايير تقويم معتمدة ومكتوبة، وسلالم درجات قابلة للتخصيص تضمن تقييمًا عادلًا وشفافًا للمهارات والواجبات والمشاريع."},
            {"icon": "book-open", "title": "التعلم الإلكتروني وبنك الأسئلة المتقدم (بلوم)",
             "text": "بيئة تفاعلية للمناهج الرقمية مع بنك أسئلة مصنف حسب مستويات بلوم ونواتج التعلم، مع تحليل مؤشرات صعوبة السؤال."},
            {"icon": "shield", "title": "الاختبارات الإلكترونية ونزاهة الاختبار",
             "text": "نظام اختبارات مع خلط تلقائي للأسئلة والخيارات، ومراقبة مباشرة، وتسجيل محاولات تبديل التاب."},
            {"icon": "receipt", "title": "المالية والمحاسبة المدرسية",
             "text": "إدارة دورة الرسوم كاملة: فواتير، جداول أقساط مرنة، خصومات الإخوة والمنح، والربط المحاسبي المباشر بقيود اليومية."},
            {"icon": "id-card", "title": "الموارد البشرية وبوابة أولياء الأمور ونداء الاستلام",
             "text": "مسيرات رواتب الكادر المدرسي، بوابة تواصل مباشرة لأولياء الأمور، مع نظام رقمي لنداء واستلام الطلاب عند البوابة."},
        ],
    }),
    _sec("feature_tabs", "المميزات بالتفصيل", "features", {
        "eyebrow": "المميزات بالتفصيل", "title": "كل موديول مبني على يوم المدرسة الفعلي.",
        "tabs": [
            {"module": "academic", "label": "الحضور الذكي", "intro": "رصد يومي أو بالحصة، والنظام ينبّهك قبل أن يتحول الغياب إلى مشكلة."},
            {"module": "assessment", "label": "الروبريك", "intro": "تصحيح بمعايير مكتوبة وأوزان واضحة، بدل التصحيح بالانطباع."},
            {"module": "elearning", "label": "بنك الأسئلة", "intro": "أسئلة مصنفة ومراجَعة، وجودتها تُقاس من نتائج الطلاب."},
            {"module": "exams", "label": "الاختبارات", "intro": "اختبارات إلكترونية بإعدادات تحفظ نزاهة التقييم."},
            {"module": "finance", "label": "المالية", "intro": "محاسبة كاملة مربوطة بملف الطالب."},
            {"module": "pickup", "label": "نداء الاستلام", "intro": "خروج آمن ومنظم في نهاية اليوم."},
            {"module": "security", "label": "الأمان", "intro": "بيانات مدرستك محمية ومعزولة ويمكن استرجاعها."},
        ],
        "soon_module": "apps",
    }),
    _sec("customize", "على مقاس مدرستك", "customize", {
        "eyebrow": "على مقاس مدرستك", "title": "ابدأ بالأساسيات، وكل ما تحتاجه لاحقًا يُفعَّل بضغطة زر.",
        "core_label": "المنصة الأم",
        "ring": [{"label": l, "on": on} for l, on in (
            ("الطلاب", True), ("الحضور", True), ("التقييم", True), ("الاختبارات", False), ("المالية", True),
            ("الرواتب", False), ("نداء الاستلام", False), ("الذكاء الاصطناعي", False))],
        "points": [
            {"icon": "link", "title": "رابط خاص باسم مدرستك", "text": "منصة مدرستك على رابطها الخاص، وبياناتها معزولة عن أي مدرسة أخرى."},
            {"icon": "palette", "title": "لوجو ولون المدرسة في كل المنصة", "text": "من شاشة الدخول إلى الشهادات والفواتير، الطلاب وأولياء الأمور يرون مدرستهم."},
            {"icon": "code", "title": "فريق تطوير يبني ما ينقص", "text": "ميزة غير موجودة؟ ندرس إمكانية بنائها لمدرستك كخدمة مخصصة."},
        ],
    }),
    _sec("ai", "الذكاء الاصطناعي", "ai", {
        "eyebrow": "فلسفة الذكاء الاصطناعي المسؤول", "title": "الذكاء الاصطناعي: يقترح، والإنسان يقرّر.",
        "subtitle": "نحن لا نستبدل المعلم أو المدير أبدًا. مهمة الذكاء الاصطناعي في منصتي هي رفع الأعباء الروتينية الشاقة، مع إبقاء القرار النهائي والاعتماد بيد الكادر البشري بنسبة 100%.",
        "tools_title": "1. مساعد المعلم الذكي (6 أدوات معتمدة)", "tools_subtitle": "لا يُعتمد أي مقترح إلا بمراجعة وموافقة المعلم",
        "tools": [{"icon": i, "text": t} for i, t in (
            ("branch", "توليد أسئلة بديلة ومتكافئة"), ("list-pen", "إعادة صياغة الأسئلة بوضوح"),
            ("pie", "اقتراح توزيع أوزان الدرجات"), ("check-square", "مراجعة وتدقيق الأسئلة المعلّقة"),
            ("list-check", "تصحيح مقترح وفق معايير الروبريك"), ("bar-chart", "تحليل فوري للنتائج بالعربية"))],
        "rows_title": "2. تحليل أداء الطالب والخطة العلاجية", "rows_subtitle": "خبرة مبنية ومنفذة في منصاتنا التدريبية المتخصصة",
        "rows": [
            {"icon": "trending", "title": "مقارنة معيارية بمتوسط الدفعة", "text": "رسم بياني يوضح موقع الطالب قياسًا بأقرانه في كل مهارة محددة."},
            {"icon": "search", "title": "كشف نقاط القوة والفجوات التعليمية", "text": "تحديد مباشر للمفاهيم التي يعاني فيها الطالب قبل اختبارات نهاية العام."},
            {"icon": "list-ordered", "title": "خطة علاجية مخصصة من 5 خطوات", "text": "مسار مقترح من 5 محطات تعليمية وتمارين مركزة لسد الفجوة التحصيلية."},
        ],
        "cost_title": "لوحة تحكم وتحجيم التكلفة (Cost Control)",
        "cost_text": "الذكاء الاصطناعي مقفول افتراضيًا، ويُفعَّل بإرادتك. تحدد المدرسة سقف استهلاك شهري محدد، مع تنبيه إداري عند بلوغ 90%، وسجل شفاف لكامل الطلبات.",
        "cost_badge": "تحكم 100% في الميزانية",
        "transparency": "",  # pending Abdelhamid's decision on naming the AI provider (spec decision 13)
    }),
    _sec("split", "خبرة التحضير للاختبارات", "exams", {
        "eyebrow": "خبرة التحضير للاختبارات",
        "title": "فهمنا اختبارات القدرات والتحصيلي وSTEP من داخل معهد يدرّب عليها.",
        "body": "بنينا منصة معهد متخصص في التدريب على هذه الاختبارات، ونقلنا ما تعلمناه إلى بنك الأسئلة والتقييم في منصتي-سكول.",
        "points": [
            {"title": "بنك أسئلة بتصنيف بلوم", "text": "تحليل صعوبة وتمييز من نتائج الطلاب الفعلية، ودورة مراجعة قبل الاعتماد."},
            {"title": "Blueprint للاختبار", "text": "توزيع الأسئلة على النواتج والمستويات قبل بناء الاختبار."},
            {"title": "موديول نافس", "text": "شجرة نواتج التعلم وإدارة الدورات."},
        ],
    }),
    _sec("case_studies", "قصص النجاح", "success", {
        "eyebrow": "قصص النجاح", "title": "ماذا بنينا، ولمن، وما الذي يعمل الآن.",
        "label_challenge": "التحدي", "label_built": "ما بنيناه", "label_now": "ما يعمل الآن", "show_files": False,
    }),
    _sec("logos", "شركاء النجاح", "partners", {"title": "شركاء النجاح", "partner_label": "شريك"}),
    _sec("systems", "خبرتنا في الإدارة", "portfolio", {
        "eyebrow": "بنية برمجية مثبتة هندسيًا",
        "title": "قبل المدارس، بنينا أنظمة إدارة متكاملة في قطاعات أخرى، والخبرة نفسها هي ما تحصل عليه مدرستك.",
        "subtitle": "أنظمتنا ليست نماذج نظرية، بل حلول SaaS مؤسسية تعمل باشتراكات فعلية.",
        "items": [
            {"icon": "gavel", "name": "المحامي (LexOffice)", "tag": "SaaS نشط باشتراكات", "url": "https://elmouhamy.com",
             "text": "نظام متقدم لإدارة مكاتب وشركات المحاماة، الجلسات، القضايا، إدارة الموكلين، والفوترة القانونية."},
            {"icon": "archive", "name": "مرصود (Marsoud)", "tag": "إدارة عمليات وسلاسل إمداد", "url": "https://marsoud.com",
             "text": "منصة CRM & ERP شاملة لإدارة المبيعات، المستودعات، سلاسل الإمداد، وأوامر الشراء باحترافية."},
            {"icon": "dumbbell", "name": "ActiveFit", "tag": "إدارة عضويات واشتراكات", "url": "https://activefit.manasety.ai",
             "text": "نظام متكامل لإدارة الصالات الرياضية متعددة الفروع، تجديد الاشتراكات، وجدولة الحصص والمدربين."},
            {"icon": "ticket", "name": "لمّة (Lammah)", "tag": "إدارة فعاليات وتذاكر", "url": "",
             "text": "منصة متخصصة لإدارة الفعاليات والمؤتمرات، بيع التذاكر، رصد بوابات الدخول عبر QR Code، والتحليلات."},
        ],
    }),
    _sec("services", "عندك نشاط آخر؟", "services", {
        "eyebrow": "حلول برمجية مخصصة للشركات والمؤسسات",
        "title": "عندك نشاط آخر؟ أنت تأتي بالفكرة ونحن نتولى الباقي.",
        "subtitle": "سواء كنت تدير مركزًا طبيًا، شركة تجارية، منصة تدريب، أو شركة لوجستية؛ فريقنا الهندسي يصمم ويبني حلولًا رقمية مخصصة ومفصلة على متطلبات عملك تمامًا.",
        "items": [{"icon": i, "title": t} for i, t in (
            ("monitor-code", "تطوير أنظمة خاصة Custom Software"), ("bot", "حلول الذكاء الاصطناعي والأتمتة"),
            ("grid", "بناء وتكامل أنظمة ERP المخصصة"), ("phone", "تطبيقات ويب وموبايل أصلية"))],
        "side_title": "استشارة تقنية مباشرة",
        "side_text": "شاركنا فكرتك أو نظامك الحالي، وسنقدم لك دراسة جدوى وتصورًا معماريًا متكاملًا.",
        "cta_label": "ناقش مشروعك معنا", "cta_href": "#contact",
    }),
    _sec("faq", "الأسئلة الشائعة", "faq", {
        "eyebrow": "إجابات واضحة وشفافة", "title": "الأسئلة الشائعة حول منصتي - سكول",
        "subtitle": "كل ما تحتاج معرفته عن طبيعة النظام، الأمان، التخصيص، والتطبيق في مدرستك.",
        "category": "", "more_label": "",
    }),
    _sec("cta_form", "نموذج العرض التوضيحي", "contact", {
        "eyebrow": "خطوتك الأولى نحو تحول رقمي مستقر", "title": "احجز عرضًا توضيحيًا لمدرستك الآن",
        "subtitle": "املأ البيانات وسيقوم مستشارنا التعليمي بتجهيز جلسة استعراض حية مخصصة لاحتياجات مدرستك ونطاق عملك.",
        "stages": STAGES, "business_types": BUSINESS_TYPES,
        "name_placeholder": "مثال: أ. محمد العتيبي", "school_placeholder": "مثال: مدارس الرياض الأهلية",
        "phone_placeholder": "+966 5X XXX XXXX", "notes_placeholder": "اذكر عدد الطلاب التقريبي أو أي أنظمة ترغب بربطها...",
        "submit_label": "احجز العرض التوضيحي",
        "note": "سيتواصل معك مستشارنا التعليمي لتجهيز نسخة تجريبية حية مخصصة لبيانات واحتياجات مدرستك.",
    }),
]

# (module, icon, name, description, status) — from the claim registry ("تُكتب بثقة" / "قريبًا").
FEATURES = [
    ("academic", "clipboard", "رصد يومي أو بالحصة", "المعلم يرصد الحضور من شاشته في ثوانٍ.", "ready"),
    ("academic", "bell", "إنذار تلقائي", "للطلاب المعرّضين للخطر حسب الغياب والدرجات.", "ready"),
    ("academic", "user-check", "Student 360", "ملف الطالب كاملًا في شاشة واحدة.", "ready"),
    ("academic", "calendar", "الجدول الذكي", "كشف التعارض وتغطية غياب المعلم.", "ready"),
    ("assessment", "star", "روبريك بأوزان", "مربوط بالواجب مباشرة.", "ready"),
    ("assessment", "list-ordered", "سلالم درجات وقواعد نجاح", "لكل مادة ومرحلة.", "ready"),
    ("assessment", "spark", "تصحيح مقترح بالروبريك", "بالذكاء الاصطناعي، والمعلم يعتمد.", "ready"),
    ("elearning", "layers", "تصنيف بلوم", "لكل سؤال مستواه المعرفي.", "ready"),
    ("elearning", "bar-chart", "تحليل الصعوبة والتمييز", "من نتائج الطلاب الفعلية.", "ready"),
    ("elearning", "check-square", "دورة مراجعة", "قبل اعتماد أي سؤال.", "ready"),
    ("elearning", "grid", "Blueprint", "توزيع الاختبار على النواتج.", "ready"),
    ("exams", "branch", "خلط الأسئلة والخيارات", "لكل طالب ترتيب مختلف.", "ready"),
    ("exams", "pie", "درجة جزئية وسالبة", "ومحاولات محددة.", "ready"),
    ("exams", "shield", "مراقبة مباشرة", "وتسجيل تبديل التاب.", "ready"),
    ("finance", "receipt", "فواتير وأقساط", "وخصومات ومنح.", "ready"),
    ("finance", "wallet", "تسوية بنكية", "وتقارير مالية كاملة.", "ready"),
    ("finance", "briefcase", "رواتب مربوطة بالقيد", "مع الموارد البشرية.", "ready"),
    ("pickup", "megaphone", "ولي الأمر ينادي", "من رابط مخصص.", "ready"),
    ("pickup", "check", "شاشة مباشرة", "المدرسة تؤكد خروج الطالب.", "ready"),
    ("security", "lock", "بيانات معزولة", "لكل مدرسة.", "ready"),
    ("security", "database", "نسخ احتياطي واسترجاع انتقائي", "وسلة محذوفات.", "ready"),
    ("security", "file", "سجل نشاط", "بقيم قبل وبعد لكل تعديل.", "ready"),
    ("nafes", "target", "شجرة نواتج التعلم وإدارة الدورات", "موديول نافس.", "ready"),
    ("nafes", "chart", "الفجوات والخطط العلاجية في نافس", "تحليل الفجوات وخطط علاجية.", "soon"),
    ("apps", "phone", "تطبيقات ولي الأمر والطالب والمعلم", "تطبيقات جوال لمتابعة الحضور والدرجات والرسوم والإشعارات.", "soon"),
]

FAQ_HOME = [
    ("ما الفرق بين منصتي سكول والبرامج الجاهزة المنتشرة في السوق؟", "schools",
     "البرامج الجاهزة غالبًا ما تجبر مدرستك على تغيير طريقتها لتناسب البرنامج، أو تقدم حلولًا مجزأة تتطلب إدخال بيانات متكرر. منصتي صُممت كنواة واحدة متكاملة تجمع شؤون الطلاب والاختبارات والمالية والرواتب، ومعها فريق تطوير يدرس تخصيص أي ميزة حسب طبيعة مدرستك."),
    ("هل تظهر منصتي باسم وشعار مدرستنا أم باسم منصتي؟", "schools",
     "تظهر المنصة باسم مدرستك: رابط خاص بها، وكامل الواجهات بشعار مدرستك وألوانها الرسمية، من شاشة الدخول إلى الشهادات والفواتير."),
    ("كيف تضمنون أمان وعزل بيانات الطلاب والمالية الخاصة بمدرستنا؟", "tech",
     "بيانات كل مؤسسة تعليمية معزولة عن غيرها، مع نسخ احتياطي واسترجاع انتقائي، وسلة محذوفات، وسجل نشاط يرصد كل تعديل بقيمته قبل وبعد."),
    ("هل تتوفر تطبيقات للهواتف الذكية لأولياء الأمور والمعلمين؟", "schools",
     "تطبيقات الجوال لولي الأمر والمعلم والطالب قريبًا."),
    ("هل استخدام ميزات الذكاء الاصطناعي إلزامي، وكيف نتحكم في تكاليفه؟", "ai",
     "الذكاء الاصطناعي مقفول افتراضيًا وموديول اختياري بالكامل. إن رغبت في تفعيله، تحدد الإدارة سقفًا شهريًا للاستهلاك مع تنبيه عند الوصول إلى 90%، ولا يُعتمد أي مقترح إلا بموافقة المعلم."),
    ("لدينا ملفات طلاب ومعلمين على Excel، هل يمكن استيرادها بسهولة؟", "tech",
     "نعم، تُستورد قوائم الطلاب من ملفات Excel، وفريقنا معك أثناء تجهيز البيانات ونقلها."),
    ("كيف يتم احتساب التسعير لمدرستنا؟", "pricing",
     "نتبع تسعيرًا مرنًا حسب الباقة والموديولات التي تحتاجها مدرستك فعليًا، حتى لا تدفع لخدمات لا تستخدمها. يُقدَّم عرض سعر مخصص بعد العرض التوضيحي ودراسة المتطلبات."),
    ("هل يمكن بناء ميزات برمجية مخصصة أو تقارير خاصة غير متوفرة حاليًا؟", "general",
     "نعم. نحن الشركة المطورة للمنصة ولدينا فريق متخصص في البرمجيات المخصصة (Custom Software)، فندرس أي متطلب خاص أو تقرير غير متوفر حاليًا وإمكانية تنفيذه لمدرستك."),
]

# The six FAQs on the current manasety.ai, loaded hidden for review (spec: "تُحمَّل كبداية").
FAQ_LEGACY = [
    ("هل تقدمون مواقع أم أنظمة؟", "نحن نبني أنظمة ومنصات تشغيل للشركات (إدارة + متابعة + تقارير + صلاحيات) وليس مجرد مواقع شكلية."),
    ("هل الحل يكون مخصصاً؟", "نعم، كل نظام يُبنى حسب نشاط الشركة وطريقة التشغيل وحجم الفريق."),
    ("هل النظام قابل للتوسع مستقبلاً؟", "بالتأكيد، نضع النمو في الحسبان لإضافة مستخدمين وميزات وتقارير بدون كسر النظام."),
    ("هل يوجد دعم بعد التسليم؟", "نعم، نوفر دعماً وتحسينات وتطويراً مستمراً حسب الاتفاق، كشريك تقني لا كمورد فقط."),
    ("هل يمكن ربط النظام بأنظمة أخرى؟", "نعم، حسب احتياجك: بريد/إشعارات/واجهات تكامل/أنظمة داخلية... إلخ."),
    ("هل يمكن إضافة تقارير وذكاء اصطناعي؟", "نعم، بحسب الهدف: فلترة، تصنيف، اقتراح قرارات، Chatbots داخلية، ولوحات KPIs."),
]

CLIENTS = [  # consent pending for all → hidden until recorded (spec: written consent, WhatsApp is enough)
    ("معهد القدرات للتدريب", "client", "التعليم والتدريب"),
    ("مدارس الشيخ صالح الشريف للتعليم القرآني", "client", "التعليم القرآني"),
    ("إيزي جو", "client", ""),
    ("مزرعة الياسمين", "client", ""),
    ("دكتور بورسلين", "client", ""),
    ("قافر", "partner", "شريك في السعودية"),
]

CLIENT_URLS = {"قافر": "https://qaffer.com"}  # linked on the current site

CATEGORIES = [
    ("إدارة المدارس", "school-management"), ("التعلم الإلكتروني", "elearning"), ("التقييم", "assessment"),
    ("المالية المدرسية", "school-finance"), ("الحضور", "attendance"), ("الذكاء الاصطناعي في التعليم", "ai-in-education"),
    ("اختبارات القدرات والتحصيلي", "qudurat-tahsili"), ("عن منصتي", "about-manasety"),
]

GA_ID = "G-RB896Z7ZBD"
PIXEL_ID = "1365676268753546"
INTEGRATIONS = [
    {"name": "Meta domain verification", "kind": "verification", "placement": "head", "position": 0,
     "identifier": "rakz6coyf8znt856mdjcjputqivqsk",
     "code": '<meta name="facebook-domain-verification" content="rakz6coyf8znt856mdjcjputqivqsk" />',
     "notes": "مرتبط بتحقق Meta Business. يبقى بحرفه."},
    {"name": "Google Analytics 4", "kind": "script", "placement": "head", "position": 1, "identifier": GA_ID,
     "code": (f'<!-- Google Analytics -->\n<script async src="https://www.googletagmanager.com/gtag/js?id={GA_ID}"></script>\n'
              "<script>\n  window.dataLayer = window.dataLayer || [];\n  function gtag(){dataLayer.push(arguments);}\n"
              f"  gtag('js', new Date());\n  gtag('config', '{GA_ID}');\n</script>"),
     "notes": "نفس الـ Property القائمة؛ لا تُنشأ Property جديدة. أحداث click_whatsapp / click_submit_form / click_book_session يرسلها site.js."},
    {"name": "Meta Pixel", "kind": "script", "placement": "head", "position": 50, "identifier": PIXEL_ID,
     "code": ("<!-- Meta Pixel Code -->\n<script>\n!function(f,b,e,v,n,t,s){if(f.fbq)return;n=f.fbq=function(){n.callMethod?"
              "n.callMethod.apply(n,arguments):n.queue.push(arguments)};if(!f._fbq)f._fbq=n;n.push=n;n.loaded=!0;"
              "n.version='2.0';n.queue=[];t=b.createElement(e);t.async=!0;t.src=v;s=b.getElementsByTagName(e)[0];"
              "s.parentNode.insertBefore(t,s)}(window,document,'script','https://connect.facebook.net/en_US/fbevents.js');\n"
              f"fbq('init','{PIXEL_ID}');\nfbq('track','PageView');\n</script>\n"
              f"<noscript><img height='1' width='1' style='display:none' src='https://www.facebook.com/tr?id={PIXEL_ID}&ev=PageView&noscript=1'/></noscript>\n"
              "<!-- End Meta Pixel Code -->"),
     "notes": "نفس الـ Pixel. أحداث Lead (نموذج + واتساب) وWhatsAppClick يرسلها site.js بنفس الأسماء."},
    {"name": "Google Search Console", "kind": "verification", "placement": "none", "position": 90, "identifier": "manasety.ai",
     "code": "", "notes": "لا يوجد وسم تحقق في HTML الصفحة الحالية → التحقق غالبًا عبر DNS. لا يُمس؛ مرتبط بتسجيل Google Play Console."},
    {"name": "Marsoud CRM — leads", "kind": "api", "placement": "none", "position": 91,
     "identifier": "https://marsoud.com/api/v1/public/contact-lead",
     "code": "", "notes": "نُقل للسيرفر: services/leads.py. التوكن في MARSOUD_CONTACT_TOKEN (متغير بيئة) — لم يعد ظاهرًا في المتصفح. "
                          "صفحة contact.html القديمة ما زالت ترسل بنفسها."},
    {"name": "web3forms — email backup", "kind": "form", "placement": "none", "position": 92, "identifier": "api.web3forms.com",
     "code": "", "notes": "نُقل للسيرفر. المفتاح في WEB3FORMS_ACCESS_KEY."},
    {"name": "WhatsApp links (EG + SA)", "kind": "embed", "placement": "none", "position": 93, "identifier": "wa.me",
     "code": "", "notes": "الأرقام والرسالة الجاهزة من الإعدادات. الرقم السعودي لواتساب فقط بدون ادعاء مكتب."},
    {"name": "n8n lead webhook", "kind": "webhook", "placement": "none", "position": 94, "identifier": "", "is_active": False,
     "code": "", "notes": "اختياري لأي أتمتة لاحقة. الرابط في N8N_LEAD_WEBHOOK_URL."},
]


def _get_or_create(model: Any, defaults: dict | None = None, **lookup: Any) -> tuple[Any, bool]:
    row = db.session.query(model).filter_by(**lookup).first()
    if row:
        return row, False
    row = model(**lookup, **(defaults or {}))
    db.session.add(row)
    return row, True


def seed_all(legal_dir: Path | None = None, profile_pdf: Path | None = None) -> list[str]:
    log: list[str] = []

    page, created = _get_or_create(Page, {"title": "الصفحة الرئيسية", "seo": {"ar": {
        "title": "منصتي-سكول | نظام إدارة مدارس متكامل: الطلاب والتقييم والمالية والذكاء الاصطناعي",
        "description": "نظام واحد لمدرستك كلها: القبول والحضور والدرجات والفواتير والرواتب، وذكاء اصطناعي يوفّر وقت المعلم، كلها بهوية مدرستك. احجز عرضًا توضيحيًا.",
        "software_name": "منصتي-سكول (Manasety School)", "og_image": ""}, "en": {}}}, slug="home")
    if created:
        db.session.flush()
        for pos, s in enumerate(HOME_SECTIONS):
            db.session.add(Section(page_id=page.id, position=pos, is_visible=True, **s))
        db.session.flush()
        db.session.refresh(page)
        publish_page(page, note="المحتوى الأولي")
        log.append("home page + 13 sections (published)")

    if not db.session.query(Feature).count():
        for pos, (module, icon, name, desc, status) in enumerate(FEATURES):
            db.session.add(Feature(module=module, icon=icon, name=name, description=desc, status=status, position=pos,
                                   claim_note="سجل الادعاءات (مواصفات 26 أكتوبر 2026) — يُطابَق مع نتائج UAT قبل النشر"))
        log.append(f"{len(FEATURES)} features")

    if not db.session.query(FaqItem).count():
        for pos, (q, cat, a) in enumerate(FAQ_HOME):
            db.session.add(FaqItem(question=q, answer_html=f"<p>{a}</p>", category=cat, position=pos,
                                   source="سجل الادعاءات" if re.search(r"\d", a) else ""))
        for pos, (q, a) in enumerate(FAQ_LEGACY, start=len(FAQ_HOME)):
            db.session.add(FaqItem(question=q, answer_html=f"<p>{a}</p>", category="general", position=pos,
                                   is_visible=False, show_on_home=False, show_on_faq_page=True))
        log.append("FAQ: 8 home + 6 legacy (hidden for review)")

    clients = {}
    for pos, (name, kind, sector) in enumerate(CLIENTS):
        clients[name], made = _get_or_create(Client, {"kind": kind, "sector": sector, "position": pos, "consent": False,
                                                      "url": CLIENT_URLS.get(name, ""),
                                                      "consent_notes": "بانتظار موافقة كتابية"}, name=name)
        if made:
            log.append(f"client (hidden until consent): {name}")
    db.session.flush()

    if not db.session.query(CaseStudy).count():
        db.session.add(CaseStudy(
            client_id=clients["معهد القدرات للتدريب"].id, position=0, url="https://qdrat.manasety.ai",
            anonymous_label="معهد تدريب متخصص في اختبارات القدرات",
            challenge="معهد يدرّب على اختبارات متعددة ويحتاج منصة واحدة للبرامج والدورات والتقييم.",
            built="منصة تدريب كاملة: برامج القدرات العامة ودورات الاختبارات، ودورات إنجليزي بمنهج Headway، وشهادات السلامة المهنية، وتحليل الأداء والخطة العلاجية.",
            working_now="المنصة شغالة فعليًا.[[if:qdrat_students]] أكثر من [[fact:qdrat_students]] طالب على المنصة.[[/if]]"))
        db.session.add(CaseStudy(
            client_id=clients["مدارس الشيخ صالح الشريف للتعليم القرآني"].id, position=1, url="https://school.manasety.ai",
            anonymous_label="مدرسة حقيقية للتعليم القرآني",
            challenge="مدرسة تحفيظ لها احتياجات لا يغطيها قالب جاهز.",
            built="نسخة مخصصة من المنصة الأم بهوية المدرسة وموديولاتها.",
            working_now="النسخة شغالة فعليًا وتخدم المدرسة يوميًا."))
        log.append("2 case studies (client names hidden until consent)")

    for key, label, value, meaning in (
        ("qdrat_students", "طلاب منصة معهد القدرات", "2000", "عدد الطلاب المسجلين على منصة المعهد — يحتاج تأكيدًا كتابيًا وتاريخًا"),
        ("marsoud_clients", "عملاء مرصود", "400+", "ماذا يعدّ الرقم ومصدره وتاريخه غير معروف بعد"),
    ):
        _, made = _get_or_create(Fact, {"label": label, "value": value, "meaning": meaning, "is_visible": False}, key=key)
        if made:
            log.append(f"fact (hidden, unverified): {key}")

    for name, slug in CATEGORIES:
        _get_or_create(Category, {"name": name}, slug=slug)
    _get_or_create(Author, {"name": "عبدالحميد", "job_title": "مؤسس منصتي ومعلم تقني"}, slug="abdelhamid")

    for it in INTEGRATIONS:
        data = dict(it)
        name = data.pop("name")
        _, made = _get_or_create(Integration, {"owner": "", "last_verified_at": date(2026, 10, 26), **data}, name=name)
        if made:
            log.append(f"integration: {name}")

    _get_or_create(Redirect, {"to_path": "/", "code": 301, "note": "الصفحة القديمة"}, from_path="/index.html")

    if legal_dir:
        log += import_legal(legal_dir)
    if profile_pdf:
        log += import_profile(profile_pdf)

    db.session.commit()
    return log


_TITLE_RE = re.compile(r"<title>(.*?)</title>", re.S)
_DESC_RE = re.compile(r'<meta name="description" content="([^"]*)"')
_BODY_RE = re.compile(r"<body[^>]*>(.*)</body>", re.S)


def import_legal(directory: Path) -> list[str]:
    """Import privacy/terms/refund.html exactly as served today (body markup, title, description)."""
    log = []
    for slug in ("privacy", "terms", "refund"):
        path = Path(directory) / f"{slug}.html"
        if not path.exists() or db.session.query(LegalPage).filter_by(slug=slug).first():
            continue
        html = path.read_text(encoding="utf-8")
        body = _BODY_RE.search(html)
        body_html = re.sub(r'<script[^>]*src="legal\.js"[^>]*></script>', "", body.group(1) if body else "").strip()
        title = _TITLE_RE.search(html)
        desc = _DESC_RE.search(html)
        db.session.add(LegalPage(slug=slug, title=(title.group(1).strip() if title else slug),
                                 meta_description=desc.group(1) if desc else "", body_html=clean_legal(body_html),
                                 last_updated=date(2026, 9, 1)))
        log.append(f"legal page imported: /{slug}.html")
    return log


def import_profile(pdf: Path) -> list[str]:
    if db.session.query(DisplayFile).filter_by(public_path="manasety-profile.pdf").first():
        return []
    media_dir = Path(current_app.config["MEDIA_DIR"])
    media_dir.mkdir(parents=True, exist_ok=True)
    stored = "private/file-manasety-profile.pdf"
    (media_dir / "private").mkdir(parents=True, exist_ok=True)
    shutil.copyfile(pdf, media_dir / stored)
    db.session.add(DisplayFile(display_name="الملف التعريفي للشركة (PDF)", public_path="manasety-profile.pdf",
                               stored_filename=stored, placements=["footer"], is_visible=True, direct_link_enabled=True))
    return ["display file: /manasety-profile.pdf"]
