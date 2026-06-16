import re
import unicodedata
import os
import faster_whisper
from langdetect import detect
from database import get_setting

whisper_model = faster_whisper.WhisperModel("small", device="cpu", compute_type="int8")

LANG_NOT_SUPPORTED_MSG = (
    "عذراً، لا أستطيع الردّ إلا باللغتين العربية والإنجليزية.\n"
    "Sorry, I can only respond in Arabic or English."
)
UNCLEAR_AUDIO_MSG = "عذراً، لم أستطع سماع الكلام بوضوح. حاول مرة أخرى مع صوت أوضح أو بدون ضجيج، أو اكتب سؤالك يدويًا."
TRANSCRIBE_FAILED_MSG = "عذراً، تعذر تحويل الرسالة الصوتية إلى نص حالياً."
MAX_AUDIO_SECONDS = 60
AUDIO_TOO_LONG_MSG = "عذراً، التسجيل الصوتي طويل (أكثر من دقيقة واحدة). رجاءً أعد المحاولة بتسجيل أقصر."

def normalize_arabic_text(text):
    """Clean and normalize Arabic text for better processing"""
    if not text:
        return text
    
    # Normalize unicode
    text = unicodedata.normalize('NFKC', text)
    
    # Remove diacritics (tashkeel)
    text = re.sub(r'[\u064B-\u065F\u0670]', '', text)
    
    # Normalize alef/hamza forms
    text = re.sub(r'[إأآا]', 'ا', text)
    text = re.sub(r'ى', 'ي', text)
    text = re.sub(r'ة', 'ه', text)
    
    # Remove extra spaces
    text = re.sub(r'\s+', ' ', text)
    
    return text.strip()

def detect_language(text):
    """Detect if text is Arabic or English"""
    try:
        # Check for Arabic characters
        arabic_chars = sum(1 for c in text if '\u0600' <= c <= '\u06FF')
        if arabic_chars / max(len(text), 1) > 0.2:
            return 'ar'
        return detect(text)
    except:
        return 'ar'  # Default to Arabic

def split_arabic_sentences(text):
    """Split Arabic text into sentences"""
    delimiters = r'(?<=[۔؟!])\s+'
    sentences = re.split(delimiters, text)
    return [s.strip() for s in sentences if s.strip()]


def transcribe_audio(file_path: str) -> str:
    try:
        # Use VAD to ignore silence/noise segments (typically improves accuracy).
        segments, info = whisper_model.transcribe(
            file_path,
            beam_size=5,
            vad_filter=True,
        )

        # Enforce duration limit (hard backend cap).
        detected_duration = float(getattr(info, "duration", 0.0) or 0.0)
        if detected_duration > MAX_AUDIO_SECONDS:
            return AUDIO_TOO_LONG_MSG

        text = " ".join((segment.text or "").strip() for segment in segments if (segment.text or "").strip()).strip()
        if not text or len(text) < 2:
            return UNCLEAR_AUDIO_MSG

        detected_language = getattr(info, "language", None)
        detected_probability = float(getattr(info, "language_probability", 0.0) or 0.0)

        # Strict rejection when the detected language is clearly not supported.
        if detected_language not in ["ar", "en"] and detected_probability >= 0.6:
            return LANG_NOT_SUPPORTED_MSG

        # If we are confident about ar/en, accept and post-process Arabic.
        if detected_language in ["ar", "en"] and detected_probability >= 0.55:
            return normalize_arabic_text(text) if detected_language == "ar" else text

        # Otherwise, re-transcribe forcing both ar/en and choose the better one.
        segments_ar, info_ar = whisper_model.transcribe(
            file_path,
            language="ar",
            beam_size=5,
            vad_filter=True,
        )
        text_ar = " ".join((segment.text or "").strip() for segment in segments_ar if (segment.text or "").strip()).strip()
        if not text_ar or len(text_ar) < 2:
            text_ar = ""

        segments_en, info_en = whisper_model.transcribe(
            file_path,
            language="en",
            beam_size=5,
            vad_filter=True,
        )
        text_en = " ".join((segment.text or "").strip() for segment in segments_en if (segment.text or "").strip()).strip()
        if not text_en or len(text_en) < 2:
            text_en = ""

        prob_ar = float(getattr(info_ar, "language_probability", 0.0) or 0.0)
        prob_en = float(getattr(info_en, "language_probability", 0.0) or 0.0)

        score_ar = (len(text_ar) * prob_ar) if text_ar else 0.0
        score_en = (len(text_en) * prob_en) if text_en else 0.0

        if max(score_ar, score_en) <= 10.0:
            return UNCLEAR_AUDIO_MSG

        if score_ar >= score_en:
            return normalize_arabic_text(text_ar)
        return text_en
    except Exception:
        return TRANSCRIBE_FAILED_MSG


# ─── Out-of-scope detection ──────────────────────────────────────────────────
# Checked on the REWRITTEN (standalone) query inside ask_with_context,
# right after rewrite_query() — before vector search or tool routing.

# Other Palestinian / Arab / international universities (not Hebron).
_OTHER_UNIVERSITY_KEYWORDS = [
    "بيرزيت", "birzeit", "bir zeit",
    "النجاح", "an-najah", "annajah", "najah university",
    "بوليتكنك", "polytechnic",
    "جامعة القدس", "al-quds university",
    "جامعة أبو ديس", "abu dis university",
    "جامعة بيت لحم", "bethlehem university",
    "الجامعة الإسلامية", "islamic university of gaza",
    "جامعة الأزهر غزة",
    "arab american university", "الجامعة العربية الأمريكية",
    "جامعة الأقصى",
    "اليرموك", "الجامعة الأردنية", "جامعة عمان",
    "جامعة القاهرة", "الجامعة الأمريكية في القاهرة",
    "جامعة دمشق", "جامعة بيروت", "الجامعة اللبنانية",
    r"\bharvard\b", r"\boxford\b", r"\bcambridge\b", r"\bmit\b",
    r"\bstanford\b", r"\byale\b", r"\bprinceton\b",
]

# Pure general-knowledge patterns that have no Hebron University relevance.
_GENERAL_KNOWLEDGE_PATTERNS = [
    r"(?:ما\s+(?:هي\s+)?عاصمة|عاصمة\s+\w+\b|capital\s+of\b|what(?:'s|\s+is)\s+the\s+capital\b)",
    r"\b(?:أطول|أعلى|أكبر|أصغر|أعمق)\s+(?:نهر|جبل|دولة|مدينة|قارة|بحيرة)\s+(?:في\s+)?(?:العالم|الأرض)",
    r"\b(?:longest|tallest|largest|smallest|deepest)\s+(?:river|mountain|country|city|continent|lake)\b",
    r"(?:كيف\s+أطبخ|وصفة\s+(?:طعام|طبخ|حلوى|كعكة|تشيز|شوكولاتة|برغر|دجاج))",
    r"\b(?:recipe\s+for|how\s+to\s+(?:bake|cook|make)\b)",
    r"(?:رئيس\s+(?:جمهورية|وزراء|حكومة)\s+(?:الأردن|مصر|أمريكا|تركيا|روسيا|الصين|فرنسا|بريطانيا|ألمانيا|إيطاليا|إسرائيل))",
    r"\bpresident\s+of\s+(?:the\s+)?(?:united\s+states|usa|america|egypt|jordan|turkey|russia|china|france|uk|germany|israel)\b",
    r"\bprime\s+minister\s+of\s+(?:the\s+)?(?:uk|united\s+kingdom|israel|jordan|egypt|turkey|india|pakistan|canada|australia)\b",
    r"\bرئيس\s+وزراء\s+(?:الأردن|إسرائيل|بريطانيا|الهند|كندا|أستراليا|مصر|تركيا)\b",
    r"(?:سعر\s+(?:الدولار|اليورو|الذهب|النفط|البيتكوين))",
    r"\b(?:dollar|euro|gold|oil|bitcoin)\s+price\b",
    r"\b(?:نتيجة|نتائج)\s+(?:مباراة|مباريات|دوري)\s+(?!.*(?:جامعة|امتحان))",
    r"\b(?:score|result)\s+of\s+(?:the\s+)?(?:match|game)\b",
    r"\b(?:توقعات\s+الطقس|حالة\s+الجو)\s+(?:في\s+)?(?:عمّان|القاهرة|بيروت|الرياض|دبي|إسطنبول)\b",
    r"\bweather\s+(?:in|forecast\s+for)\s+(?!hebron|الخليل)",
]

# University-service vocabulary — if present, always pass through to RAG.
_IN_SCOPE_TERMS = (
    "كلية", "عمادة", "تسجيل", "مساق", "فصل دراسي",
    "بكالوريوس", "ماجستير", "دكتوراه", "منحة دراسية",
    "رئيس الجامعة", "عميد", "موعد التسجيل", "رسوم الجامعة",
    "admission", "registration", "semester", "dean", "tuition",
    "scholarship", "campus", "university president",
)


def check_out_of_scope(question: str, lang: str = "ar") -> str | None:
    """
    Return an out-of-scope message when the (rewritten) question clearly falls
    outside Hebron University scope. Returns None to let RAG proceed normally.

    Safety valves — always returns None (RAG handles it):
      • 'الخليل' or 'hebron' anywhere in text → explicit university reference.
      • Any _IN_SCOPE_TERMS token present    → university-service question.
      • No pattern matched                    → ambiguous, let RAG try.
    """
    if not question or not question.strip():
        return None

    clean = question.strip().lower()

    if any(m in clean for m in ("الخليل", "hebron")):
        return None

    if any(t in clean for t in _IN_SCOPE_TERMS):
        return None

    for kw in _OTHER_UNIVERSITY_KEYWORDS:
        if re.search(kw, clean, re.IGNORECASE):
            return get_setting("ar_out_of_scope") if lang == "ar" else get_setting("en_out_of_scope")

    for pat in _GENERAL_KNOWLEDGE_PATTERNS:
        if re.search(pat, clean, re.IGNORECASE):
            return get_setting("ar_out_of_scope") if lang == "ar" else get_setting("en_out_of_scope")

    return None