import os
import json
import logging
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

import threading
from typing import Optional, Tuple
import pandas as pd  # <-- added for Excel row processing

from langchain_community.llms import Ollama
from langchain_community.embeddings import OllamaEmbeddings
from langchain_community.vectorstores import Chroma
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import (
    TextLoader,
    PyPDFLoader,
    Docx2txtLoader,
)
from langchain_core.documents import Document
from src.utils import normalize_arabic_text, detect_language, check_out_of_scope
from database import get_setting, add_unanswered_query

# Optional reranker – install with: pip install sentence-transformers
try:
    from sentence_transformers import CrossEncoder
    RERANKER_AVAILABLE = True
except ImportError:
    RERANKER_AVAILABLE = False

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Markdown links break many RTL chat UIs (wrong bracket direction, ')' glued to the URL).
# Flatten [label](http...) to "label: url" or plain url; skip image syntax ![...](...).
# URL end is the ')' that closes the link opener, with inner '( )' pairs counted so paths
# like https://wiki.org/Thing_(disambiguation) are not truncated.


def _starts_with_http_scheme(s: str, k: int) -> bool:
    if k >= len(s):
        return False
    if s[k : k + 8].lower().startswith("https://"):
        return True
    return s[k : k + 7].lower().startswith("http://")


def _parse_inline_md_url(s: str, url_start: int) -> Optional[Tuple[str, int]]:
    """
    After '[label](' return (url, closing_paren_index) where closing_paren_index
    is the index of the ')' that ends the Markdown link. Inner parentheses in the
    URL are balanced so a literal ) inside the path does not end the URL early.
    Returns None if there is no closing parenthesis.
    """
    depth = 0
    i = url_start
    n = len(s)
    while i < n:
        c = s[i]
        if c == "(":
            depth += 1
        elif c == ")":
            if depth > 0:
                depth -= 1
            else:
                return s[url_start:i], i
        i += 1
    return None


def normalize_channel_answer(text: str) -> str:
    """
    Convert Markdown http(s) links to plain text for messaging apps and web widgets:
    [نص](https://...) → "نص: https://..." ; [https://x](https://x) → "https://x".
    Skips ![alt](url). URLs may contain ')' when balanced with '(' inside the path.
    Safe to run on any assistant reply before sending to clients.
    """
    if not text or not text.strip():
        return text

    s = str(text)
    out: list[str] = []
    i = 0
    n = len(s)

    while i < n:
        if s[i] == "[" and (i == 0 or s[i - 1] != "!"):
            j = s.find("]", i + 1)
            if j != -1 and j + 1 < n and s[j + 1] == "(":
                k = j + 2
                if k < n and _starts_with_http_scheme(s, k):
                    parsed = _parse_inline_md_url(s, k)
                    if parsed is not None:
                        raw_url, end_paren = parsed
                        url = raw_url.strip().rstrip(".,;،")
                        if url:
                            label = s[i + 1 : j].strip()
                            if not label or label == url:
                                out.append(url)
                            else:
                                out.append(f"{label}: {url}")
                            i = end_paren + 1
                            continue

        out.append(s[i])
        i += 1

    return "".join(out)


# ── Multi-provider LLM configuration ─────────────────────────────────────────
# Env vars are the baseline; DB values (loaded in __init__) take priority so
# admin-panel changes apply without restarting Flask.
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "ollama").strip().lower()
LLM_API_KEY = os.getenv("LLM_API_KEY", "").strip()
LLM_API_BASE_URL = os.getenv("LLM_API_BASE_URL", "").strip()
LLM_MODEL_ENV = os.getenv("LLM_MODEL", "").strip()

try:
    from langchain_openai import ChatOpenAI
    _OPENAI_AVAILABLE = True
except ImportError:
    _OPENAI_AVAILABLE = False
    logger.warning(
        "langchain-openai is not installed — openai_compatible provider unavailable. "
        "Run: pip install langchain-openai"
    )

class ArabicRAGChatbot:
    def __init__(
        self,
        llm_model: str = "deepseek-v3.1:671b-cloud",
        embed_model: str = "bge-m3",
        persist_dir: str = "./chroma_db",
        ollama_base_url: Optional[str] = None,
        retrieval_strategy: str = "mmr",
    ):
        self.llm_model = llm_model
        self.embed_model = embed_model
        self.persist_dir = persist_dir
        self.retrieval_strategy = retrieval_strategy
        self._lock = threading.RLock()

        self.ollama_base_url = (
            ollama_base_url
            or os.getenv("OLLAMA_BASE_URL")
            or "http://localhost:11434"
        )
        
        # env LLM_MODEL overrides the constructor argument when set
        if LLM_MODEL_ENV:
            llm_model = LLM_MODEL_ENV
        self._default_llm_model = llm_model  # remember for reload

        # DB config overrides env vars (so admin-panel changes work without restart)
        self._apply_db_llm_config()

        logger.info(
            "Initializing with LLM: %s (provider=%s), Embeddings: %s",
            self._llm_model_name, self._llm_provider, embed_model,
        )
        self.llm = self._build_llm()
        
        # Initialize embeddings model (use a dedicated embedding model)
        self.embeddings = OllamaEmbeddings(
            model=embed_model,
            base_url=self.ollama_base_url
        )
        
        # Arabic-aware text splitter – larger chunks for better context
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=200,
            separators=["\n\n", "\n", "۔", "؟", "!", ". ", " ", ""],
            length_function=len,
        )
        
        # Optional reranker for better relevance
        self.reranker = None
        if RERANKER_AVAILABLE:
            try:
                # Change to a multilingual model!
                self.reranker = CrossEncoder('cross-encoder/mmarco-mMiniLMv2-L12-H384-v1')
                logger.info("✅ Reranker loaded")
            except Exception as e:
                logger.warning(f"Could not load reranker: {e}")
        
        # Load existing vector store if available (persistence!)
        self.vectorstore = None
        if os.path.isdir(persist_dir) and any(os.scandir(persist_dir)):
            try:
                self.vectorstore = Chroma(
                    persist_directory=persist_dir,
                    embedding_function=self.embeddings
                )
                logger.info(f"✅ Loaded existing vector store from {persist_dir}")
            except Exception as e:
                logger.warning(f"Could not load existing DB: {e}")

    # ------------------------------------------------------------------
    # LLM provider management
    # ------------------------------------------------------------------

    def _apply_db_llm_config(self) -> None:
        """
        Load LLM config from the database and store on self.
        DB values override env vars; env vars are the fallback.
        """
        try:
            from database import get_llm_config
            cfg = get_llm_config()
        except Exception as exc:
            logger.warning("Could not load LLM config from DB: %s — using env vars", exc)
            cfg = {}

        # DB value wins; fall back to env var; fall back to hardcoded default
        self._llm_provider = (
            cfg.get("llm_provider") or LLM_PROVIDER or "ollama"
        ).strip().lower()
        self._llm_api_key = cfg.get("llm_api_key") or LLM_API_KEY or ""
        self._llm_api_base_url = cfg.get("llm_api_base_url") or LLM_API_BASE_URL or ""
        self._llm_model_name = (
            cfg.get("llm_model_name") or LLM_MODEL_ENV or self._default_llm_model
        )

    def _build_llm(self):
        """Construct and return the LLM object from current self._llm_* attributes."""
        if self._llm_provider == "openai_compatible" and _OPENAI_AVAILABLE:
            llm = ChatOpenAI(
                model=self._llm_model_name,
                api_key=self._llm_api_key or "dummy",
                base_url=self._llm_api_base_url or None,
                temperature=0.3,
                max_tokens=512,
                timeout=90,
                max_retries=1,
            )
            logger.info(
                "LLM: OpenAI-compatible → %s at %s",
                self._llm_model_name, self._llm_api_base_url,
            )
            return llm

        # Ollama (default)
        try:
            llm = Ollama(
                model=self._llm_model_name,
                base_url=self.ollama_base_url,
                temperature=0.3,
                num_predict=512,
                num_ctx=8192,
                top_k=40,
                top_p=0.9,
            )
        except TypeError:
            llm = Ollama(
                model=self._llm_model_name,
                temperature=0.3,
                num_predict=512,
                num_ctx=8192,
                top_k=40,
                top_p=0.9,
            )
        logger.info("LLM: Ollama → %s at %s", self._llm_model_name, self.ollama_base_url)
        return llm

    def reload_llm(self) -> dict:
        """
        Re-read LLM config from DB and reinitialise self.llm.
        Called by the admin API after saving new settings so changes
        take effect immediately without restarting Flask.
        Returns a summary dict for the API response.
        """
        with self._lock:
            self._apply_db_llm_config()
            self.llm = self._build_llm()
        logger.info(
            "LLM reloaded: provider=%s model=%s",
            self._llm_provider, self._llm_model_name,
        )
        return {
            "provider": self._llm_provider,
            "model": self._llm_model_name,
            "api_base_url": self._llm_api_base_url,
            "api_key_set": bool(self._llm_api_key),
        }

    # ------------------------------------------------------------------
    # LLM invocation helper (normalises Ollama str vs ChatOpenAI AIMessage)
    # ------------------------------------------------------------------

    def _llm_invoke(self, prompt: str) -> str:
        """Invoke the LLM and always return a plain string regardless of provider."""
        response = self.llm.invoke(prompt)
        if hasattr(response, "content"):
            return response.content  # ChatOpenAI / AIMessage
        return str(response)         # Ollama returns str directly

    # ------------------------------------------------------------------
    # Question classifier – no extra LLM call; keyword heuristic only
    # ------------------------------------------------------------------

    # Arabic and English keywords that signal the user wants live/dynamic data
    _LIVE_KEYWORDS = (
        # Arabic – calendar / schedule
        "تقويم", "جدول", "مواعيد", "موعد", "أحداث", "فعاليات",
        # Arabic – announcements / news
        "إعلان", "إعلانات", "أخبار", "خبر",
        # Arabic – registration / admissions
        "قبول", "تسجيل", "التسجيل", "التقديم", "قبولات",
        # Arabic – faculty / staff (includes Palestinian dialect variants)
        "دكتور", "دكتورة", "الدكتور", "الدكتورة", "للدكتور",
        "أستاذ", "أستاذة", "الأستاذ", "مدرس", "هيئة التدريس",
        "عميد", "عميدة", "رئيس قسم", "رئيسة قسم",
        "ساعات المكتب", "ساعات مكتبية", "الساعات المكتبية", "وقت الدكتور",
        "بريد الدكتور", "ايميل الدكتور", "إيميل",
        # Arabic – fees / financial
        "رسوم", "رسم", "أقساط", "قسط",
        "تكاليف", "تكلفة", "مالية", "مبلغ", "دفع", "سداد",
        "تأمين صحي", "حجز مقعد", "إعادة قيد", "تأجيل فصل",
        # Arabic – time hints
        "اليوم", "هذا الأسبوع", "هذا الفصل", "الفصل الحالي",
        "القادم", "القادمة", "الجاري", "الجارية", "الآن", "هذه السنة",
        # English equivalents
        "calendar", "schedule", "upcoming", "announcement", "news",
        "registration", "admission", "deadline", "today", "this week",
        "this semester", "current semester",
        # English – faculty
        "professor", "doctor", "dr.", " dr ", "faculty", "staff", "lecturer",
        "dean", "department head", "office hours", "college of", "head of",
        # English – fees
        "fee", "fees", "tuition", "cost", "payment",
        "insurance", "financial", "charge", "dinar", "jod",
    )

    def _classify_question(self, question: str) -> str:
        """
        Return "live" if the question is about current dates, schedules,
        announcements, or registration; return "static" otherwise.
        Uses a keyword heuristic — no extra LLM call.
        """
        lower = question.lower()
        for kw in self._LIVE_KEYWORDS:
            if kw in lower:
                return "live"
        return "static"

    # ------------------------------------------------------------------
    # Per-format loaders
    # ------------------------------------------------------------------

    def _df_to_docs(self, df: "pd.DataFrame", source_name: str, format_label: str) -> list:
        """
        Shared helper: convert a pandas DataFrame into one Document per row.
        Each document is formatted as "column: value" lines, which gives the
        retriever enough context to understand what each value means.
        Empty cells are skipped so chunks stay compact.
        """
        docs = []
        for idx, row in df.iterrows():
            parts = []
            for col in df.columns:
                value = str(row[col]).strip()
                if value and value.lower() not in ("nan", "none", ""):
                    parts.append(f"{col}: {value}")
            if not parts:
                continue                # skip entirely empty rows
            content = "\n".join(parts)
            entity = str(row[df.columns[0]]).strip() if len(df.columns) > 0 else ""
            docs.append(Document(
                page_content=content,
                metadata={"source": source_name, "row": idx, "entity": entity},
            ))
        logger.info("Loaded %d documents from %s (one per row)", len(docs), format_label)
        return docs

    def _load_excel_row_per_doc(self, file_path: str) -> list:
        """One Document per Excel row — no splitting (rows are atomic records)."""
        source_name = os.path.basename(file_path)
        try:
            df = pd.read_excel(file_path, dtype=str).fillna("")
        except Exception as e:
            logger.error("Failed to read Excel file %r: %s", file_path, e)
            return []
        return self._df_to_docs(df, source_name, "Excel")

    def _load_csv_row_per_doc(self, file_path: str) -> list:
        """
        One Document per CSV row — same strategy as Excel, no splitting.
        CSV is structurally identical to Excel for university data (schedules,
        course lists, etc.); splitting rows at character boundaries would break
        the column-value relationship.
        Tries UTF-8 first, then falls back to Windows-1256 (common for Arabic CSV).
        """
        source_name = os.path.basename(file_path)
        for enc in ("utf-8", "utf-8-sig", "windows-1256", "latin-1"):
            try:
                df = pd.read_csv(file_path, dtype=str, encoding=enc).fillna("")
                logger.info("Read CSV %r with encoding %s", file_path, enc)
                return self._df_to_docs(df, source_name, "CSV")
            except UnicodeDecodeError:
                continue
            except Exception as e:
                logger.error("Failed to read CSV file %r: %s", file_path, e)
                return []
        logger.error("Could not decode CSV %r with any known encoding", file_path)
        return []

    def _load_json(self, file_path: str) -> list:
        """
        Load a JSON file intelligently:
        - JSON array of objects → one Document per item (same philosophy as
          Excel/CSV rows and the dynamic API connectors).
        - Any other structure (single object, nested) → one Document for the
          whole file, passed to the text splitter downstream.
        """
        source_name = os.path.basename(file_path)
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        if isinstance(data, list) and data and isinstance(data[0], dict):
            # Array of records — one Document per item
            docs = []
            for idx, item in enumerate(data):
                parts = []
                for key, val in item.items():
                    if val is not None and str(val).strip():
                        parts.append(f"{key}: {val}")
                content = "\n".join(parts)
                if not content.strip():
                    continue
                docs.append(Document(
                    page_content=content,
                    metadata={"source": source_name, "row": idx},
                ))
            logger.info("Loaded %d documents from JSON array in %r", len(docs), file_path)
            return docs

        # Non-array JSON: serialise the whole structure and let the text splitter handle it
        content = json.dumps(data, ensure_ascii=False, indent=2)
        logger.info("Loaded JSON %r as single document (non-array structure)", file_path)
        return [Document(page_content=content, metadata={"source": source_name})]

    def load_documents(self, file_path):
        """
        Load, process and index a document file into Chroma.

        Splitting strategy (controlled per format):
          Prose formats  (PDF, DOCX, TXT, non-array JSON) → RecursiveCharacterTextSplitter
          Tabular formats (Excel, CSV, JSON-array)         → NO splitting; one chunk per row/item

        Returns the number of chunks indexed.
        """
        logger.info("Loading documents from: %s", file_path)
        fp_lower = file_path.lower()
        source_name = os.path.basename(file_path)

        # ── Select loader + decide whether to split ───────────────────────
        if fp_lower.endswith('.pdf'):
            loader = PyPDFLoader(file_path)
            raw_docs = loader.load()
            should_split = True

        elif fp_lower.endswith(('.docx', '.doc')):
            loader = Docx2txtLoader(file_path)
            raw_docs = loader.load()
            should_split = True

        elif fp_lower.endswith(('.xlsx', '.xls')):
            raw_docs = self._load_excel_row_per_doc(file_path)
            should_split = False        # rows are atomic records — never split

        elif fp_lower.endswith('.csv'):
            raw_docs = self._load_csv_row_per_doc(file_path)
            should_split = False        # same as Excel: row = one chunk

        elif fp_lower.endswith('.json'):
            raw_docs = self._load_json(file_path)
            # _load_json sets should_split based on detected structure:
            # array-of-records → False (each item is already one chunk)
            # single-object/other → True (may be a large config blob)
            should_split = not (
                len(raw_docs) > 1 or                              # multiple docs = array mode
                (len(raw_docs) == 1 and raw_docs[0].metadata.get("row") is not None)
            )

        else:
            # Plain text fallback (.txt and anything unrecognised)
            loader = TextLoader(file_path, encoding='utf-8')
            raw_docs = loader.load()
            should_split = True

        # ── Normalise text + enforce consistent source key ─────────────────
        processed_docs = []
        for doc in raw_docs:
            doc.page_content = normalize_arabic_text(doc.page_content)
            doc.metadata = doc.metadata or {}
            doc.metadata["source"] = source_name  # always use bare filename
            processed_docs.append(doc)

        # ── Split (prose) or keep intact (tabular) ────────────────────────
        if should_split:
            chunks = self.text_splitter.split_documents(processed_docs)
            logger.info("Split into %d chunks (splitter applied)", len(chunks))
        else:
            chunks = processed_docs
            logger.info("Keeping %d documents intact (tabular/structured format)", len(chunks))

        # ── Index into Chroma ──────────────────────────────────────────────
        with self._lock:
            if self.vectorstore is None:
                self.vectorstore = Chroma.from_documents(
                    documents=chunks,
                    embedding=self.embeddings,
                    persist_directory=self.persist_dir,
                )
            else:
                self.vectorstore.add_documents(chunks)
            self.vectorstore.persist()

        return len(chunks)

    def get_file_chunks(self, filename: str) -> list[dict]:
        """
        Return all chunks in the vector store whose metadata 'source' matches filename.
        Returns a list of dicts with 'page_content' and 'metadata' for each chunk.
        """
        if self.vectorstore is None:
            return []
        collection = self.vectorstore._collection
        try:
            # Use $eq for compatibility; limit to avoid ever returning the whole collection
            result = collection.get(
                where={"source": {"$eq": filename}},
                include=["documents", "metadatas"],
                limit=50000,
            )
        except Exception as e:
            logger.warning(f"get_file_chunks failed for {filename!r}: {e}")
            return []
        documents = result.get("documents") or []
        metadatas = result.get("metadatas") or []
        # Pad metadatas if Chroma returns fewer (e.g. no metadata for some)
        while len(metadatas) < len(documents):
            metadatas.append({})
        return [
            {"page_content": doc, "metadata": meta}
            for doc, meta in zip(documents, metadatas)
        ]

    def delete_file(self, filename: str) -> None:
        """
        Delete all documents in the Chroma collection whose metadata 'source' matches filename.
        Persists the vector store after deletion.
        """
        if self.vectorstore is None:
            return
        with self._lock:
            try:
                self.vectorstore._collection.delete(where={"source": {"$eq": filename}})
                self.vectorstore.persist()
                logger.info(f"Deleted chunks for file {filename!r} from vector store")
            except Exception as e:
                logger.warning(f"delete_file failed for {filename!r}: {e}")
                raise

    def replace_file(self, old_filename: str, new_file_path: str, new_stored_name: str) -> int:
        """
        Atomic replace: delete all Chroma chunks keyed to `old_filename`, then
        load and index the new file under `new_stored_name`.

        Returns the number of new chunks created.
        This is the correct way to update a static document without creating
        orphaned chunks or changing the logical record identity.
        """
        # Step 1: remove old chunks
        if self.vectorstore is not None:
            with self._lock:
                try:
                    self.vectorstore._collection.delete(where={"source": {"$eq": old_filename}})
                    self.vectorstore.persist()
                    logger.info("replace_file: deleted old chunks for %r", old_filename)
                except Exception as e:
                    logger.warning("replace_file: could not delete old chunks for %r: %s", old_filename, e)
                    raise

        # Step 2: load and index the new file
        return self.load_documents(new_file_path)

    def _build_history_block(self, history: list[dict[str, str]]) -> str:
        """Format a short conversation history block for the prompt."""
        if not history:
            return ""
        lines = []
        # Keep last few turns only to stay within context window
        for turn in history[-6:]:
            role = "User" if turn["role"] == "user" else "Assistant"
            lines.append(f"{role}: {turn['content']}")
        return "\n".join(lines)

    def rewrite_query(self, question: str, history: list) -> str:
        if not history:
            return question
            
        # Get the last few messages for context
        hist_text = "\n".join([f"{msg.get('role', 'user')}: {msg.get('content', '')}" for msg in history[-4:]])
        
        # Use an Arabic prompt to match the conversation language and strictly forbid answering
        rewrite_prompt = f"""أنت أداة مساعدة لتحليل النصوص. مهمتك الوحيدة هي إعادة صياغة "السؤال الأخير" بناءً على "سياق المحادثة" ليكون سؤالاً مستقلاً ومفهوماً بدون الحاجة للعودة للسياق.

تحذير هام جداً:
- لا تقم بالإجابة على السؤال إطلاقاً!
- لا تضف أي مقدمات مثل "You are a helpful assistant" أو "السؤال المستقل هو".
- أعد كتابة السؤال فقط. وإذا كان السؤال واضحاً ومستقلاً بالفعل، أرجعه كما هو بالضبط.

سياق المحادثة:
{hist_text}

السؤال الأخير: {question}
السؤال المستقل:"""

        try:
            response = self._llm_invoke(rewrite_prompt)
            standalone = response.strip().replace("السؤال المستقل:", "").replace("Standalone Question:", "").strip()
            
            # --- Safety Checks (Guardrails) ---
            # 1. If the LLM generated a massive dialogue (e.g., > 150 chars longer than original), it hallucinated.
            # 2. If it contains English conversational filler while the question is Arabic.
            # 3. If it contains "Answer:" or "الإجابة:"
            lower_standalone = standalone.lower()
            if (len(standalone) > len(question) + 150 or 
                "you are a helpful assistant" in lower_standalone or 
                "answer:" in lower_standalone or 
                "الإجابة" in standalone):
                
                logger.warning(f"Query rewrite hallucinated. Falling back to original. LLM output: {standalone}")
                return question
                
            return standalone if standalone else question
            
        except Exception as e:
            logger.warning(f"Query rewrite failed, falling back to original: {e}")
            return question

    def get_prompt(self, context: str, question: str, lang: str, history: Optional[list[dict[str, str]]] = None) -> str:
        """Prompt with Hebron University persona, strict grounding, and language control."""
        history_block = self._build_history_block(history or [])

        if lang == "ar":
            sys_prompt = get_setting("ar_system_prompt")
            dont_know_msg = get_setting("ar_dont_know")
            return f"""
{sys_prompt}

تنبيه حاسم للذكاء الاصطناعي (CRITICAL INSTRUCTION):
إذا لم تكن الإجابة موجودة في السياق أدناه، يجب عليك أن ترد حرفياً بهذا النص فقط ولا تضف عليه شيئاً:
"{dont_know_msg}"

محادثة سابقة (إن وجدت):
{history_block}

المعلومات السياقية:
{context}

سؤال المستخدم:
{question}

إجابتك:"""
        else:
            sys_prompt = get_setting("en_system_prompt")
            dont_know_msg = get_setting("en_dont_know")
            return f"""
{sys_prompt}

CRITICAL INSTRUCTION:
If the answer does not exist in the context below, you must reply with this exact text only and add nothing else:
"{dont_know_msg}"

Previous conversation (if any):
{history_block}

Context:
{context}

User question:
{question}

Your answer:"""
    
    def ask_with_context(
        self,
        question: str,
        k: int = 15,
        rerank_top_k: int = 10,
        session_id: Optional[str] = None,
        history: Optional[list] = None,
    ) -> Tuple[str, str]:
        """
        Ask with retrieval; returns (answer, retrieved_context_string).
        Context is empty when the vector store is missing or no chunks were retrieved.
        """
        def _out(msg: str, ctx: str) -> Tuple[str, str]:
            return normalize_channel_answer(msg), ctx

        try:
            if self.vectorstore is None:
                logger.warning(
                    "No vector store loaded (persist_dir=%s). Upload files via Admin / POST /load.",
                    self.persist_dir,
                )
                return _out(
                    (
                        "عذراً، قاعدة المعرفة فارغة ولم يتم رفع أي مستندات بعد. "
                        "يرجى رفع ملفات (PDF، نص، Excel، …) من لوحة الإدارة أو عبر POST /load على خادم RAG ثم أعد السؤال.\n\n"
                        "The knowledge base has no documents yet. Upload files from the Admin panel "
                        "or POST /load on the RAG API, then try again."
                    ),
                    "",
                )

            history = history or []

            # Detect language
            detected_lang = detect_language(question)
            if detected_lang == "ar":
                question = normalize_arabic_text(question)
                lang = "ar"
            elif detected_lang == "en":
                lang = "en"
            else:
                # Unsupported language fallback
                return _out(get_setting("lang_not_supported"), "")

            # 1. Rewrite the query first — follow-up questions like "and his email?"
            #    become fully standalone ("what is Dr. X's email?") after rewriting.
            #    Classification must happen on the rewritten query so that the
            #    resolved context (name, topic) is available for keyword matching.
            search_query = self.rewrite_query(question, history)
            logger.info(f"Original: {question} | Rewritten: {search_query}")

            # 1b. Scope check on the rewritten query.
            #     Fires after rewriting so follow-up questions are fully resolved
            #     (e.g. "and what about birzeit?" → standalone before checking).
            scope_msg = check_out_of_scope(search_query, lang)
            if scope_msg:
                add_unanswered_query(question, "السؤال خارج نطاق جامعة الخليل (كشف مبكر)")
                return _out(scope_msg, "")

            # 2. Classify using the rewritten (standalone) query.
            question_class = self._classify_question(search_query)
            is_live_routing = (
                question_class == "live"
                and self._llm_provider == "openai_compatible"
                and _OPENAI_AVAILABLE
            )
            logger.info("Question class: %s | live routing: %s", question_class, is_live_routing)

            # 3. Search using the REWRITTEN query
            with self._lock:
                if self.retrieval_strategy == "mmr":
                    try:
                        docs = self.vectorstore.max_marginal_relevance_search(
                            search_query, k=k, fetch_k=max(k * 3, 30)
                        )
                    except Exception:
                        docs = self.vectorstore.similarity_search(search_query, k=k)
                else:
                    docs = self.vectorstore.similarity_search(search_query, k=k)

            # 4. Rerank if available.
            #    For live-routed questions, skip the low-confidence early return —
            #    the answer will come from API tools so a low Chroma score is expected.
            #    For static questions that score low AND the provider supports tools,
            #    set a flag to attempt a live fallback instead of giving up.
            static_needs_live_fallback = False

            if self.reranker and len(docs) > 0:
                pairs = [[search_query, doc.page_content] for doc in docs]
                scores = self.reranker.predict(pairs)
                scored_docs = sorted(zip(docs, scores), key=lambda x: x[1], reverse=True)
                highest_score = scored_docs[0][1]
                top_docs = [doc for doc, score in scored_docs[:rerank_top_k]]
                logger.info(f"Reranked: selected top {rerank_top_k} from {len(docs)}")
                context = "\n\n---\n\n".join([doc.page_content for doc in top_docs])

                if highest_score < -1.0 and not is_live_routing:
                    logger.warning("Low confidence score (%.3f) on static question.", highest_score)
                    can_try_live = self._llm_provider == "openai_compatible" and _OPENAI_AVAILABLE
                    if can_try_live:
                        # Don't give up yet — try live tools as a fallback
                        logger.info("Static path low-confidence → attempting live tool fallback.")
                        static_needs_live_fallback = True
                    else:
                        fallback_msg = get_setting("ar_low_conf") if lang == "ar" else get_setting("en_low_conf")
                        return _out(fallback_msg, context)
            else:
                top_docs = docs[:rerank_top_k]
                context = "\n\n---\n\n".join([doc.page_content for doc in top_docs])

            # ── Tool routing ───────────────────────────────────────────────
            # Runs when:  (a) question was classified "live" from the start, OR
            #             (b) question was "static" but Chroma came back empty/low.
            tool_context_parts: list[str] = []

            if is_live_routing or static_needs_live_fallback:
                try:
                    from src.tools import get_university_calendar, get_announcements, get_admissions_info, get_financial_info, get_faculty_info
                    tools_list = [get_university_calendar, get_announcements, get_admissions_info, get_financial_info, get_faculty_info]
                    tool_map = {t.name: t for t in tools_list}

                    # Ask the LLM which tool(s) to call.
                    # A system message is included to strongly bias the LLM
                    # toward calling tools rather than answering from memory.
                    from langchain_core.messages import SystemMessage, HumanMessage
                    routing_system = SystemMessage(content=(
                        "You are a tool-routing assistant for Hebron University chatbot. "
                        "Your ONLY job is to decide which tool to call based on the user's question. "
                        "You MUST call a tool — do not answer from memory or refuse. "
                        "Available tools:\n"
                        "- get_university_calendar: questions about events, dates, schedule, academic calendar, vacations, exams\n"
                        "- get_announcements: questions about news, announcements, updates\n"
                        "- get_admissions_info: questions about admission, registration, deadlines, enrollment\n"
                        "- get_financial_info: questions about fees, tuition, costs, payments\n"
                        "- get_faculty_info: questions about professors, doctors, staff, office hours, department heads, deans, email, college. "
                        "IMPORTANT: extract ONLY the person's name or department name from the question and pass it as `query`. "
                        "Do NOT pass the full question. Examples: query='خليل مصري', query='Khalil Massri', query='كلية الآداب'.\n"
                        "Always pick the most relevant tool and call it immediately."
                    ))
                    llm_with_tools = self.llm.bind_tools(tools_list)
                    # Use the rewritten (standalone) query — not the original — so
                    # the LLM sees the full context (name, topic) even for follow-ups.
                    routing_response = llm_with_tools.invoke([routing_system, HumanMessage(content=search_query)])

                    # Execute every requested tool call.
                    # Error strings returned by tools (Arabic "عذراً...") are dropped
                    # so they never pollute the prompt — Chroma context takes over instead.
                    if hasattr(routing_response, "tool_calls") and routing_response.tool_calls:
                        for tc in routing_response.tool_calls:
                            tool_name = tc.get("name", "")
                            tool_args = tc.get("args", {})
                            if tool_name in tool_map:
                                result = tool_map[tool_name].invoke(tool_args)
                                # Treat any result starting with "عذراً" as a failure —
                                # keep it out of context so Chroma can answer instead.
                                if isinstance(result, str) and result.strip().startswith("عذراً"):
                                    logger.warning(
                                        "Tool %s returned an error — dropping result, "
                                        "Chroma context will be used as fallback. Error: %s",
                                        tool_name, result[:120],
                                    )
                                else:
                                    tool_context_parts.append(result)
                                    logger.info("Tool call executed: %s → %d chars", tool_name, len(result))
                    else:
                        logger.info("LLM chose no tools for this question.")
                except Exception as tool_err:
                    logger.warning("Tool routing failed: %s", tool_err)

            # If the fallback path ran but tools returned nothing useful,
            # fall back to the original "I don't know" message.
            if static_needs_live_fallback and not tool_context_parts:
                logger.info("Live fallback produced no results — returning low-confidence message.")
                fallback_msg = get_setting("ar_low_conf") if lang == "ar" else get_setting("en_low_conf")
                return _out(fallback_msg, context)

            # Merge tool results (if any) ahead of the Chroma context
            if tool_context_parts:
                live_block = "\n\n---\n\n".join(tool_context_parts)
                context = live_block + ("\n\n---\n\n" + context if context else "")

            # ── Final answer generation ────────────────────────────────────
            prompt = self.get_prompt(context, question, lang, history=history)
            answer = self._llm_invoke(prompt).strip()
            return _out(answer, context)

        except Exception as e:
            logger.error(f"Error in ask_with_context: {e}")
            return _out("عذراً، حدث خطأ.", "")

    def ask(self, question: str, k: int = 15, rerank_top_k: int = 10, session_id: Optional[str] = None, history: Optional[list] = None) -> str:
        """Ask a question with improved retrieval. History is passed in from the API (from DB)."""
        answer, _ = self.ask_with_context(
            question, k=k, rerank_top_k=rerank_top_k, session_id=session_id, history=history
        )
        return answer
    
    def clear_database(self):
        """Clear the vector database"""
        import shutil
        if os.path.exists(self.persist_dir):
            shutil.rmtree(self.persist_dir)
            logger.info(f"Cleared database")
        self.vectorstore = None