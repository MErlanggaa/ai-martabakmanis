import os
import shutil
import streamlit as st

# --- LangChain & friends
from langchain_community.document_loaders import (
    PyPDFLoader,
    PyMuPDFLoader,
    PDFPlumberLoader,
)
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from pypdf.errors import PdfReadError, PdfStreamError
from google.api_core.exceptions import NotFound
from langchain_google_genai import (
    GoogleGenerativeAIEmbeddings,
    ChatGoogleGenerativeAI,
)
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough

# --- Google GenAI SDK (untuk set api_version="v1")
import google.generativeai as genai

# =========================
# Konfigurasi dasar
# =========================
UPLOAD_DIR = "temp"
DB_DIR = "faiss_db"
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(DB_DIR, exist_ok=True)

# Pastikan API Key terbaca dari environment
API_KEY = os.getenv("GOOGLE_API_KEY") or os.getenv("GOOGLE_GENAI_API_KEY")
if API_KEY:
    # Konfigurasi SDK Google AI; versi API ditangani internal oleh SDK (tidak perlu set api_version)
    genai.configure(api_key=API_KEY)

# Embeddings yang direkomendasikan
embedding_model = GoogleGenerativeAIEmbeddings(model="models/text-embedding-004")

# Default model chat: pindah ke lini 2.5 (lebih stabil & terbaru)
_GEMINI_DEFAULT = "gemini-2.5-flash"
_gemini_model = os.environ.get("GEMINI_MODEL", _GEMINI_DEFAULT)
chat_model = ChatGoogleGenerativeAI(model=_gemini_model)

# Urutan fallback hanya lini 2.x (tanpa 1.5-* yang sering 404)
_GEMINI_MODEL_CANDIDATES = [
    _gemini_model,
    "gemini-2.5-flash",
    "gemini-2.5-pro",
    "gemini-2.0-flash",
    "gemini-2.0-pro",
]


def load_faiss_or_none():
    index_path = os.path.join(DB_DIR)
    try:
        return FAISS.load_local(index_path, embedding_model, allow_dangerous_deserialization=True)
    except Exception:
        return None


vectorstore = load_faiss_or_none()

# =========================
# RAG chain
# =========================
RAG_TEMPLATE = """
You are a helpful assistant for an UMKM catalog (small businesses and their menus/products).

Always do two things:
1) Decide the user's intent as one of:
   - list_umkm : user asks which UMKM have joined / daftar UMKM
   - recommend : user asks for recommendations / saran menu atau tempat
   - qa        : other questions
2) Produce a JSON object with this shape (and nothing else):
{{"intent":"list_umkm|recommend|qa","answer":"string","umkm_list":["<UMKM name>"],"recommendations":[{{"umkm":"<UMKM>","menu":"<menu/item>","reason":"short why"}}]}}

Rules:
- Use ONLY the provided <context> to extract UMKM names and menus; if unsure, leave arrays empty and say you don't know.
- For intent = recommend: every recommended menu MUST include the UMKM name that provides it. Prefer 3–5 items maximum.
- For intent = list_umkm: fill umkm_list with UNIQUE names you find.
- For intent = qa: keep umkm_list empty unless explicitly asked; you may still cite UMKM in the natural-language answer if relevant.
- Keep JSON valid and minified.

<context>
{context}
</context>

Question: {question}
"""
rag_prompt = ChatPromptTemplate.from_template(RAG_TEMPLATE)


def format_docs(docs):
    """Gabungkan isi dokumen jadi satu teks utuh"""
    return "\n\n".join(doc.page_content for doc in docs)


chain = (
    RunnablePassthrough.assign(context=lambda x: format_docs(x["context"]))
    | rag_prompt
    | chat_model
    | StrOutputParser()
)

# =========================
# UI (Streamlit)
# =========================
st.set_page_config(page_title="AI Product Chat (Gemini)", page_icon="🤖")
st.title("🤖 Chat Produk (Gemini Mode)")

mode = st.sidebar.selectbox("Pilih Mode:", ["User", "Admin"])

if mode == "Admin":
    st.subheader("📂 Upload dan Simpan Data Produk")
    uploaded_file = st.file_uploader("📄 Upload PDF di sini", type=["pdf"])

    if uploaded_file:
        pdf_path = os.path.join(UPLOAD_DIR, uploaded_file.name)
        with open(pdf_path, "wb") as f:
            shutil.copyfileobj(uploaded_file, f)

        # Validasi header PDF sederhana untuk menghindari file rusak / bukan PDF
        try:
            with open(pdf_path, "rb") as f:
                header = f.read(5)
            if not header.startswith(b"%PDF-"):
                st.error("File yang diunggah bukan PDF yang valid. Coba unggah ulang.")
                os.remove(pdf_path)
                st.stop()
        except Exception:
            st.error("Gagal membaca file yang diunggah. Coba unggah ulang.")
            try:
                os.remove(pdf_path)
            except Exception:
                pass
            st.stop()

        st.info("📚 Memproses dokumen...")
        # Coba beberapa loader agar kompatibel dengan lebih banyak variasi PDF
        docs = None
        loader_errors = []
        for LoaderCls in (PyPDFLoader, PyMuPDFLoader, PDFPlumberLoader):
            try:
                loader = LoaderCls(pdf_path)
                docs = loader.load()
                break
            except (PdfReadError, PdfStreamError) as e:
                loader_errors.append(f"{LoaderCls.__name__}: {e}")
                continue
            except Exception as e:
                loader_errors.append(f"{LoaderCls.__name__}: {e}")
                continue
        if not docs:
            st.error(
                "Tidak bisa membaca PDF ini dengan beberapa parser. Pastikan file tidak terenkripsi/scan-only. "
                "Jika ini hasil scan gambar, aktifkan OCR dulu dan coba lagi."
            )
            try:
                os.remove(pdf_path)
            except Exception:
                pass
            st.caption("Detail error loader: " + " | ".join(loader_errors))
            st.stop()

        splitter = RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=100)
        splits = splitter.split_documents(docs)

        # Init or append to FAISS index, then persist
        if vectorstore is None:
            vectorstore = FAISS.from_documents(splits, embedding_model)
        else:
            vectorstore.add_documents(splits)
        vectorstore.save_local(DB_DIR)
        st.success("✅ Dokumen berhasil disimpan dan siap digunakan!")

else:
    st.subheader("💬 Tanya tentang produk yang sudah diunggah")
    query = st.text_input("Masukkan pertanyaan kamu:")

    if query:
        with st.spinner("🧠 Mencari jawaban..."):
            local_vs = vectorstore or load_faiss_or_none()
            if local_vs is None:
                st.warning("Database belum ada. Masuk ke mode Admin untuk mengunggah dokumen dulu.")
                st.stop()
            docs = local_vs.similarity_search(query, k=8)
            if not docs:
                st.warning("Tidak ada informasi relevan dalam database.")
            else:
                import json
                try:
                    raw = chain.invoke({"context": docs, "question": query})
                except NotFound:
                    raw = None
                    for m in _GEMINI_MODEL_CANDIDATES:
                        try:
                            tmp_chat = ChatGoogleGenerativeAI(model=m)
                            tmp_chain = (
                                RunnablePassthrough.assign(context=lambda x: format_docs(x["context"]))
                                | rag_prompt
                                | tmp_chat
                                | StrOutputParser()
                            )
                            raw = tmp_chain.invoke({"context": docs, "question": query})
                            st.info(f"Model diganti otomatis ke: {m}")
                            os.environ["GEMINI_MODEL"] = m
                            break
                        except NotFound:
                            continue
                    if raw is None:
                        st.error("Tidak ada model Gemini 2.x yang tersedia untuk API key ini.")
                        st.stop()

                # Coba parse JSON dari LLM
                data = None
                if isinstance(raw, str):
                    try:
                        data = json.loads(raw)
                    except Exception:
                        data = None

                if not data or not isinstance(data, dict):
                    # fallback: tampilkan raw text biasa
                    st.write("**Jawaban:**")
                    st.write(raw)
                else:
                    intent = data.get("intent", "qa")
                    answer = data.get("answer", "")
                    umkm_list = data.get("umkm_list", []) or []
                    recs = data.get("recommendations", []) or []

                    if intent == "list_umkm":
                        st.markdown("**Daftar UMKM yang bergabung:**")
                        if umkm_list:
                            for name in sorted(set(umkm_list)):
                                st.write(f"• {name}")
                        else:
                            st.write("(Belum ada data UMKM yang terdeteksi dari dokumen.)")
                    elif intent == "recommend":
                        st.markdown("**Rekomendasi:**")
                        if recs:
                            for r in recs[:5]:
                                st.write(f"• **{r.get('menu','?')}** — _oleh_ **{r.get('umkm','?')}**. Alasan: {r.get('reason','')} ")
                        else:
                            st.write("(Belum bisa merekomendasikan dari data yang ada.)")
                        if answer:
                            st.write("")
                            st.write(answer)
                    else:
                        # intent qa
                        st.write("**Jawaban:**")
                        st.write(answer if answer else raw)
