from __future__ import annotations

from pathlib import Path
import os
import base64

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, File, UploadFile, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage

from document_service import generate_pdf_from_text, generate_docx_from_text

BASE_DIR = Path(__file__).resolve().parent
UPLOADS_DIR = BASE_DIR / "uploads"
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
OCR_RESULT_PATH = BASE_DIR / "ocr_result.md"

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
MODEL_ALIASES = {
    "llama-3.2-11b-vision": "llama-3.2-11b-vision-preview",
    "llama-3.2-11b-vision-preview": "meta-llama/llama-4-scout-17b-16e-instruct",
}
FALLBACK_VISION_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"


def _resolve_model_name(model_name: str) -> str:
    return MODEL_ALIASES.get(model_name, model_name)


GROQ_MODEL = _resolve_model_name(os.getenv("GROQ_MODEL", FALLBACK_VISION_MODEL))


def _build_groq_client(model_name: str) -> ChatGroq:
    return ChatGroq(
        api_key=GROQ_API_KEY,
        model=model_name,
        temperature=0.7,
        max_tokens=4096,
    )

groq_client = (
    _build_groq_client(GROQ_MODEL)
    if GROQ_API_KEY
    else None
)

app = FastAPI(title="Smart Notes API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/uploads", StaticFiles(directory=str(UPLOADS_DIR)), name="uploads")


def _detect_image_mime_type(image_bytes: bytes) -> str:
    if image_bytes.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if image_bytes.startswith(b"GIF87a") or image_bytes.startswith(b"GIF89a"):
        return "image/gif"
    if image_bytes[:4] == b"RIFF" and image_bytes[8:12] == b"WEBP":
        return "image/webp"
    return "image/jpeg"


def encode_image_to_base64(image_bytes: bytes) -> str:
    return base64.b64encode(image_bytes).decode("utf-8")


def _extract_markdown_content(content: object) -> str:
    if isinstance(content, str):
        return content.strip()

    if isinstance(content, list):
        chunks: list[str] = []
        for item in content:
            if isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str) and text.strip():
                    chunks.append(text.strip())
            elif isinstance(item, str) and item.strip():
                chunks.append(item.strip())
        return "\n\n".join(chunks).strip()

    return str(content).strip()


def _save_markdown_result(markdown_text: str) -> None:
    OCR_RESULT_PATH.write_text(markdown_text, encoding="utf-8")


def process_image(image_bytes: bytes) -> dict:
    if not image_bytes:
        raise ValueError("No image data provided.")

    if groq_client is None:
        raise RuntimeError("GROQ_API_KEY is not configured for Groq OCR.")

    prompt = (
        "You are a Master Transcriber and professional technical editor. "
        "Do NOT perform raw OCR.\n\n"
        "Carefully READ the handwritten notes in the image, interpret their meaning "
        "with expert judgment, and completely REWRITE them as a polished professional "
        "engineering document.\n\n"
        "Mandatory corrections - apply these exactly:\n"
        '- "Nodes sv" -> "Node.js Server"\n'
        '- "VB engine" -> "V8 Engine"\n'
        '- "14 Sings" -> "Single-threaded"\n\n'
        "Formatting rules (output ONLY valid Markdown):\n"
        "- Use # for the main title (textbook-style chapter heading).\n"
        "- Use ## for section subheadings.\n"
        "- Use bullet lists for steps, lists, and key ideas.\n"
        "- Use **bold** for every important technical term and concept.\n\n"
        "Quality rules:\n"
        "- Fix all spelling and grammar errors.\n"
        "- Reorganize content where needed so it reads like a page from a modern "
        "programming textbook.\n"
        "- If handwriting is messy or ambiguous, use context clues to choose the "
        "most logical and technically correct interpretation.\n"
        "- Output ONLY the final Markdown document. Do not explain your process, "
        "add preamble, or include any text outside the document."
    )

    mime_type = _detect_image_mime_type(image_bytes)
    image_base64 = encode_image_to_base64(image_bytes)
    image_data_url = f"data:{mime_type};base64,{image_base64}"

    message = HumanMessage(
        content=[
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": image_data_url}},
        ]
    )

    engine_model = GROQ_MODEL
    try:
        response = groq_client.invoke([message])
    except Exception as exc:
        error_text = str(exc)
        model_missing = "model_not_found" in error_text or "does not exist" in error_text
        model_decommissioned = "model_decommissioned" in error_text or "decommissioned" in error_text
        should_fallback = model_missing or model_decommissioned
        if should_fallback and GROQ_MODEL != FALLBACK_VISION_MODEL:
            fallback_client = _build_groq_client(FALLBACK_VISION_MODEL)
            response = fallback_client.invoke([message])
            engine_model = FALLBACK_VISION_MODEL
        else:
            raise

    markdown = _extract_markdown_content(getattr(response, "content", ""))

    if not markdown:
        raise RuntimeError("Groq OCR response was empty.")

    _save_markdown_result(markdown)

    return {
        "engine": engine_model,
        "raw_text": markdown,
        "notes_text": markdown,
    }


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/ocr")
async def ocr(file: UploadFile = File(...)):
    try:
        data = await file.read()
        if not data:
            raise HTTPException(status_code=400, detail="Empty file upload.")

        result = process_image(data)
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover - defensive
        raise HTTPException(status_code=500, detail=f"OCR failed: {exc}") from exc

    return {
        "filename": file.filename,
        "engine": result["engine"],
        "text": result["notes_text"],
    }


@app.post("/export/pdf")
async def export_pdf(request: Request, file: UploadFile = File(...)):
    try:
        data = await file.read()
        if not data:
            raise HTTPException(status_code=400, detail="Empty file upload.")

        result = process_image(data)
        notes_text = result["notes_text"]
        out_path = generate_pdf_from_text(notes_text, out_dir=UPLOADS_DIR, stem="smart_notes")
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=500, detail=f"PDF export failed: {exc}") from exc

    download_url = request.url_for("uploads", path=out_path.name)
    return {
        "filename": file.filename,
        "engine": result["engine"],
        "text": notes_text,
        "download_url": str(download_url),
    }


@app.post("/export/docx")
async def export_docx(request: Request, file: UploadFile = File(...)):
    try:
        data = await file.read()
        if not data:
            raise HTTPException(status_code=400, detail="Empty file upload.")

        result = process_image(data)
        notes_text = result["notes_text"]
        out_path = generate_docx_from_text(notes_text, out_dir=UPLOADS_DIR, stem="smart_notes")
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=500, detail=f"DOCX export failed: {exc}") from exc

    download_url = request.url_for("uploads", path=out_path.name)
    return {
        "filename": file.filename,
        "engine": result["engine"],
        "text": notes_text,
        "download_url": str(download_url),
    }
