import os
import shutil
import json
from typing import Optional

from fastapi import FastAPI, UploadFile, File, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# LangChain & related
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

import google.generativeai as genai


# =========================
# Directories & Config
# =========================
UPLOAD_DIR = "temp"
DB_DIR = "faiss_db"
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(DB_DIR, exist_ok=True)

# API Key for Google
API_KEY = os.getenv("GOOGLE_API_KEY") or os.getenv("GOOGLE_GENAI_API_KEY")
if API_KEY:
	genai.configure(api_key=API_KEY)

# Embeddings & Chat models
embedding_model = GoogleGenerativeAIEmbeddings(model="models/text-embedding-004")

_GEMINI_DEFAULT = "gemini-2.5-flash"
_gemini_model = os.environ.get("GEMINI_MODEL", _GEMINI_DEFAULT)
chat_model = ChatGoogleGenerativeAI(model=_gemini_model)

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
	return "\n\n".join(doc.page_content for doc in docs)


chain = (
	RunnablePassthrough.assign(context=lambda x: format_docs(x["context"]))
	| rag_prompt
	| chat_model
	| StrOutputParser()
)


# =========================
# FastAPI app
# =========================
app = FastAPI(title="UMKM AI API", version="1.0.0")

# CORS (adjust origins for your Laravel host)
app.add_middleware(
	CORSMiddleware,
	allow_origins=["*"],
	allow_credentials=True,
	allow_methods=["*"],
	allow_headers=["*"],
)


class ChatRequest(BaseModel):
	question: str


@app.get("/health")
def health():
	return {"status": "ok"}


@app.get("/admin/status")
def admin_status():
	local_vs = load_faiss_or_none()
	if local_vs is None:
		return {
			"index": "missing", 
			"vectors": 0,
			"message": "Database belum ada. Upload PDF via /admin/upload terlebih dahulu."
		}
	# Best-effort: try to read vector count
	vectors = 0
	try:
		vectors = int(getattr(local_vs.index, "ntotal", 0))
	except Exception:
		vectors = 0
	
	# Cek apakah ada file di temp directory
	pdf_files = []
	try:
		if os.path.exists(UPLOAD_DIR):
			pdf_files = [f for f in os.listdir(UPLOAD_DIR) if f.lower().endswith('.pdf')]
	except Exception:
		pass
	
	return {
		"index": "ready" if vectors > 0 else "empty", 
		"vectors": vectors,
		"pdf_files_uploaded": len(pdf_files),
		"message": f"Database siap dengan {vectors} dokumen terindeks." if vectors > 0 else "Database kosong. Upload PDF terlebih dahulu."
	}


@app.post("/admin/upload")
async def admin_upload(file: UploadFile = File(...)):
	global vectorstore
	if not file.filename.lower().endswith(".pdf"):
		raise HTTPException(status_code=400, detail="Only PDF is supported")

	pdf_path = os.path.join(UPLOAD_DIR, file.filename)
	with open(pdf_path, "wb") as f:
		shutil.copyfileobj(file.file, f)

	# Validate simple PDF header
	try:
		with open(pdf_path, "rb") as f:
			header = f.read(5)
		if not header.startswith(b"%PDF-"):
			os.remove(pdf_path)
			raise HTTPException(status_code=400, detail="Invalid PDF file")
	except HTTPException:
		raise
	except Exception:
		try:
			os.remove(pdf_path)
		except Exception:
			pass
		raise HTTPException(status_code=400, detail="Failed to read uploaded file")

	# Try multiple loaders for compatibility
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
		try:
			os.remove(pdf_path)
		except Exception:
			pass
		raise HTTPException(status_code=400, detail="Cannot read this PDF with available parsers")

	splitter = RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=100)
	splits = splitter.split_documents(docs)

	if vectorstore is None:
		vectorstore = FAISS.from_documents(splits, embedding_model)
	else:
		vectorstore.add_documents(splits)
	vectorstore.save_local(DB_DIR)

	return {"status": "ok", "added_chunks": len(splits)}


def _invoke_chain_with_fallback(docs, question: str) -> Optional[dict]:
	try:
		raw = chain.invoke({"context": docs, "question": question})
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
				raw = tmp_chain.invoke({"context": docs, "question": question})
				os.environ["GEMINI_MODEL"] = m
				break
			except NotFound:
				continue

	if raw is None:
		return None

	if isinstance(raw, str):
		try:
			return json.loads(raw)
		except Exception:
			# Return raw text when JSON parsing fails
			return {"intent": "qa", "answer": raw, "umkm_list": [], "recommendations": []}

	return raw if isinstance(raw, dict) else None


@app.post("/chat")
def chat_post(body: ChatRequest):
	# Reload vectorstore setiap kali untuk memastikan data terbaru
	local_vs = load_faiss_or_none()
	if local_vs is None:
		raise HTTPException(status_code=400, detail="Index is not ready. Upload via /admin/upload first.")
	
	# Cek jumlah dokumen di index
	try:
		num_docs = local_vs.index.ntotal if hasattr(local_vs, 'index') and hasattr(local_vs.index, 'ntotal') else 0
	except Exception:
		num_docs = 0
	
	if num_docs == 0:
		raise HTTPException(status_code=400, detail="Database kosong. Upload PDF via /admin/upload terlebih dahulu.")
	
	# Search dengan lebih banyak dokumen untuk memastikan ada hasil
	docs = local_vs.similarity_search(body.question, k=min(8, num_docs))
	
	if not docs:
		return {
			"intent": "qa", 
			"answer": "Maaf, tidak ada informasi relevan dalam database untuk pertanyaan Anda. Pastikan PDF sudah diupload dan berisi informasi yang relevan.", 
			"umkm_list": [], 
			"recommendations": [],
			"debug": {"num_docs_in_index": num_docs, "docs_found": 0}
		}
	
	# Debug: log context yang ditemukan (opsional, bisa dihapus di production)
	context_preview = format_docs(docs[:2])[:200] if docs else ""
	
	data = _invoke_chain_with_fallback(docs, body.question)
	if data is None:
		raise HTTPException(status_code=503, detail="No available Gemini 2.x model for this API key.")
	
	# Tambahkan debug info jika tidak ada data dari context
	if isinstance(data, dict):
		if not data.get("umkm_list") and not data.get("recommendations") and "tidak" in data.get("answer", "").lower():
			data["debug"] = {
				"num_docs_in_index": num_docs,
				"docs_found": len(docs),
				"context_preview": context_preview
			}
	
	return data


@app.get("/chat")
def chat_get(question: str = Query(..., description="User question")):
	return chat_post(ChatRequest(question=question))


# Run with: uvicorn server:app --host 0.0.0.0 --port 8000


