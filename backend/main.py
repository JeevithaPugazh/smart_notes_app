from __future__ import annotations  # Enable postponed evaluation of type hints for cleaner forward references.

# -----------------------------
# Imports: Standard Library (File Handling / Encoding / Configuration)
# -----------------------------
import base64  # Encodes uploaded binary note images into base64 for multimodal AI payloads.
import os  # Reads environment variables used for secure runtime configuration.
from pathlib import Path  # Provides robust cross-platform filesystem path management.

# -----------------------------
# Imports: Environment Variable Injection
# -----------------------------
from dotenv import load_dotenv  # Loads key/value pairs from .env into process environment.

load_dotenv()  # Inject environment variables so API keys and model settings are available at startup.

# -----------------------------
# Imports: FastAPI Core (Asynchronous processing / HTTP API)
# -----------------------------
from fastapi import BackgroundTasks, FastAPI, File, HTTPException, UploadFile  # Core request/response primitives for async file upload APIs.
from fastapi.middleware.cors import CORSMiddleware  # CORS Policy middleware so frontend can call backend during local demo.
from fastapi.responses import FileResponse  # Streams generated PDF/DOCX files back to the user as downloads.
from fastapi.staticfiles import StaticFiles  # Serves generated assets from uploads directory when needed.
from starlette.background import BackgroundTask  # Runs post-response cleanup tasks to keep demo workspace clean.

# -----------------------------
# Imports: AI / LangChain Integration
# -----------------------------
from langchain_core.messages import HumanMessage  # Defines multimodal message payloads sent to the LLM.
from langchain_groq import ChatGroq  # Groq-hosted chat model client for image/text note transformation.

# -----------------------------
# Imports: Document Export Services
# -----------------------------
from document_service import generate_docx_from_text, generate_pdf_from_text  # Converts markdown output into downloadable DOCX/PDF.

# -----------------------------
# Constants and App Configuration
# -----------------------------
BASE_DIR = Path(__file__).resolve().parent  # Resolve backend directory as stable root for files.
UPLOADS_DIR = BASE_DIR / "uploads"  # Define folder where temporary uploads and generated files are stored.
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)  # Ensure uploads directory exists before any request handling.
OCR_RESULT_PATH = BASE_DIR / "ocr_result.md"  # Persist latest markdown output for inspection/debug during demo.

GROQ_API_KEY = os.getenv("GROQ_API_KEY")  # Read Groq API key from environment for authenticated model calls.
MODEL_ALIASES = {  # Map deprecated model IDs to currently supported replacements.
    "llama-3.2-11b-vision": "llama-3.2-11b-vision-preview",  # Upgrade old shorthand vision model ID.
    "llama-3.2-11b-vision-preview": "meta-llama/llama-4-scout-17b-16e-instruct",  # Upgrade decommissioned preview model.
}  # Close model alias mapping.
FALLBACK_VISION_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"  # Provide safe fallback model for continuity when IDs fail.
ALLOWED_UPLOAD_EXTENSIONS = {".jpg", ".jpeg", ".png", ".pdf", ".txt"}  # Accept image/pdf/txt inputs used in classroom demo.

IMAGE_PROMPT = (  # Prompt used when user uploads image/pdf note content for multimodal processing.
    "You are a Master Transcriber and professional technical editor. "  # Set high-quality editorial role.
    "Do NOT perform raw OCR.\n\n"  # Instruct model to rewrite meaningfully, not dump noisy OCR.
    "Carefully READ the handwritten notes in the image, interpret their meaning "  # Ask for semantic interpretation.
    "with expert judgment, and completely REWRITE them as a polished professional "  # Require polished textbook language.
    "engineering document.\n\n"  # Frame final output as engineering-quality notes.
    "Mandatory corrections - apply these exactly:\n"  # Declare deterministic term corrections.
    '- "Nodes sv" -> "Node.js Server"\n'  # Correct known handwriting shorthand to canonical term.
    '- "VB engine" -> "V8 Engine"\n'  # Correct common misread technical term.
    '- "14 Sings" -> "Single-threaded"\n\n'  # Correct likely OCR/handwriting ambiguity.
    "Formatting rules (output ONLY valid Markdown):\n"  # Constrain output format for frontend renderer.
    "- Use # for the main title (textbook-style chapter heading).\n"  # Ensure predictable main heading structure.
    "- Use ## for section subheadings.\n"  # Ensure section hierarchy for readability.
    "- Use bullet lists for steps, lists, and key ideas.\n"  # Normalize fragmented notes into scannable bullets.
    "- Use **bold** for every important technical term and concept.\n\n"  # Highlight key terms for student review.
    "Quality rules:\n"  # Introduce content-quality constraints.
    "- Fix all spelling and grammar errors.\n"  # Clean language quality for presentation.
    "- Reorganize content where needed so it reads like a page from a modern "  # Ask for narrative coherence.
    "programming textbook.\n"  # Anchor tone to textbook style.
    "- If handwriting is messy or ambiguous, use context clues to choose the "  # Permit contextual inference.
    "most logical and technically correct interpretation.\n"  # Prioritize technical correctness.
    "- Output ONLY the final Markdown document. Do not explain your process, "  # Prevent chain-of-thought leakage.
    "add preamble, or include any text outside the document."  # Keep response directly usable in UI/export.
)  # Close image prompt definition.

TEXT_PROMPT = (  # Prompt used when user uploads a .txt transcript instead of an image.
    "This is a raw text transcript of notes. Please format them into a "  # Clarify source modality for model behavior.
    "professional textbook style with Markdown.\n\n"  # Require polished markdown output.
    "Formatting rules (output ONLY valid Markdown):\n"  # Enforce markdown-only contract.
    "- Use # for the main title (textbook-style chapter heading).\n"  # Define heading convention.
    "- Use ## for section subheadings.\n"  # Define section structure.
    "- Use bullet lists for steps, lists, and key ideas.\n"  # Convert raw text to structured points.
    "- Use **bold** for every important technical term and concept.\n\n"  # Emphasize important concepts.
    "Quality rules:\n"  # Introduce quality requirements.
    "- Fix spelling and grammar errors.\n"  # Correct language mistakes.
    "- Reorganize content for clarity while preserving meaning.\n"  # Improve readability without changing intent.
    "- Output ONLY the final Markdown document."  # Keep response immediately renderable/exportable.
)  # Close text prompt definition.


def _resolve_model_name(model_name: str) -> str:  # Define helper to map legacy model names.
    return MODEL_ALIASES.get(model_name, model_name)  # Return alias replacement or original model ID.


GROQ_MODEL = _resolve_model_name(os.getenv("GROQ_MODEL", FALLBACK_VISION_MODEL))  # Resolve configured model with fallback and alias handling.


def _build_groq_client(model_name: str) -> ChatGroq:  # Factory function for consistent Groq client construction.
    return ChatGroq(  # Instantiate LangChain Groq chat model client.
        api_key=GROQ_API_KEY,  # Supply API credential from environment.
        model=model_name,  # Select active model ID used for this app session.
        temperature=0.7,  # Use moderate creativity for polished rewriting.
        max_tokens=4096,  # Allow sufficient output size for long note pages.
    )  # Return configured ChatGroq instance.


groq_client = (  # Build global client once at startup for reuse across requests.
    _build_groq_client(GROQ_MODEL)  # Create client with resolved model when key exists.
    if GROQ_API_KEY  # Guard creation behind API key presence.
    else None  # Keep None so routes can raise clear configuration error.
)  # Close global client assignment.

app = FastAPI(title="Smart Notes API")  # Initialize FastAPI app metadata shown in docs.

app.add_middleware(  # Register middleware stack.
    CORSMiddleware,  # Apply CORS Policy for browser-to-API calls in local dev.
    allow_origins=["*"],  # Allow frontend origin access during demo.
    allow_credentials=True,  # Allow credentialed cross-origin requests when needed.
    allow_methods=["*"],  # Permit all HTTP methods for simplicity in demo.
    allow_headers=["*"],  # Permit all request headers from frontend.
)  # Close middleware registration.

app.mount("/uploads", StaticFiles(directory=str(UPLOADS_DIR)), name="uploads")  # Mount uploads path for static serving of generated files when required.


# -----------------------------
# Helper Functions
# -----------------------------

def _detect_image_mime_type(image_bytes: bytes) -> str:  # Infer MIME type from file signature for valid data URLs.
    if image_bytes.startswith(b"\xff\xd8\xff"):  # Detect JPEG magic bytes.
        return "image/jpeg"  # Return JPEG MIME.
    if image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):  # Detect PNG signature.
        return "image/png"  # Return PNG MIME.
    if image_bytes.startswith(b"GIF87a") or image_bytes.startswith(b"GIF89a"):  # Detect GIF signatures.
        return "image/gif"  # Return GIF MIME.
    if image_bytes[:4] == b"RIFF" and image_bytes[8:12] == b"WEBP":  # Detect WEBP container pattern.
        return "image/webp"  # Return WEBP MIME.
    return "image/jpeg"  # Default to JPEG for broad model compatibility.


def encode_image_to_base64(image_bytes: bytes) -> str:  # Convert binary image payload to text-safe base64 string.
    return base64.b64encode(image_bytes).decode("utf-8")  # Encode bytes and decode to UTF-8 string.


def _extract_markdown_content(content: object) -> str:  # Normalize varying provider response formats into plain markdown.
    if isinstance(content, str):  # Handle simple string response.
        return content.strip()  # Trim whitespace and return markdown.

    if isinstance(content, list):  # Handle chunked list responses from model providers.
        chunks: list[str] = []  # Collect extracted text pieces.
        for item in content:  # Iterate through each response segment.
            if isinstance(item, dict):  # Process dictionary-based segments.
                text = item.get("text")  # Extract text key when present.
                if isinstance(text, str) and text.strip():  # Keep only non-empty string text.
                    chunks.append(text.strip())  # Add clean text segment to output list.
            elif isinstance(item, str) and item.strip():  # Handle direct string segments.
                chunks.append(item.strip())  # Add cleaned string segment.
        return "\n\n".join(chunks).strip()  # Join segments into markdown paragraphs.

    return str(content).strip()  # Fallback: stringify unknown content types safely.


def _save_markdown_result(markdown_text: str) -> None:  # Persist latest model output for traceability in demo.
    OCR_RESULT_PATH.write_text(markdown_text, encoding="utf-8")  # Write markdown file using UTF-8 encoding.


def _delete_uploaded_file(file_path: Path) -> None:  # Cleanup helper to remove temp files after response.
    file_path.unlink(missing_ok=True)  # Delete file silently even if already removed.


def _wipe_uploads_folder() -> None:  # Startup cleanup to avoid stale files between demo runs.
    for entry in UPLOADS_DIR.iterdir():  # Iterate all entries in uploads directory.
        if entry.is_file():  # Target only files, not directories.
            entry.unlink(missing_ok=True)  # Remove each file quietly.


def _invoke_groq_with_fallback(message: HumanMessage) -> tuple[object, str]:  # Centralized model invocation with resilience for model lifecycle changes.
    if groq_client is None:  # Validate API client availability before making requests.
        raise RuntimeError("GROQ_API_KEY is not configured for Groq OCR.")  # Provide explicit configuration error.

    engine_model = GROQ_MODEL  # Track model actually used for observability in API response.
    try:  # Start primary model invocation attempt.
        response = groq_client.invoke([message])  # Send LangChain message to Groq model.
    except Exception as exc:  # Catch provider errors to support fallback behavior.
        error_text = str(exc)  # Normalize exception to string for pattern checks.
        model_missing = "model_not_found" in error_text or "does not exist" in error_text  # Detect missing/invalid model errors.
        model_decommissioned = "model_decommissioned" in error_text or "decommissioned" in error_text  # Detect retired model errors.
        should_fallback = model_missing or model_decommissioned  # Decide whether fallback is appropriate.
        if should_fallback and GROQ_MODEL != FALLBACK_VISION_MODEL:  # Fallback only when needed and not already on fallback model.
            fallback_client = _build_groq_client(FALLBACK_VISION_MODEL)  # Instantiate fallback model client.
            response = fallback_client.invoke([message])  # Retry same request with fallback model.
            engine_model = FALLBACK_VISION_MODEL  # Record fallback model as active engine.
        else:  # No safe fallback path available.
            raise  # Re-raise original exception for API error handling.

    return response, engine_model  # Return provider response plus effective model name.


def process_image(image_bytes: bytes) -> dict:  # Process image/pdf uploads through multimodal AI pipeline.
    if not image_bytes:  # Validate request includes file content.
        raise ValueError("No image data provided.")  # Fail fast with clear validation error.

    mime_type = _detect_image_mime_type(image_bytes)  # Determine MIME for data URL packaging.
    image_base64 = encode_image_to_base64(image_bytes)  # Convert binary image into base64 text.
    image_data_url = f"data:{mime_type};base64,{image_base64}"  # Build browser-style data URL for model input.

    message = HumanMessage(  # Build multimodal user message for LangChain.
        content=[  # Provide both instruction text and visual payload.
            {"type": "text", "text": IMAGE_PROMPT},  # Supply academic/editorial prompt.
            {"type": "image_url", "image_url": {"url": image_data_url}},  # Attach encoded image payload.
        ]  # Close content list.
    )  # Close HumanMessage construction.

    response, engine_model = _invoke_groq_with_fallback(message)  # Execute model call with automatic fallback support.

    markdown = _extract_markdown_content(getattr(response, "content", ""))  # Extract normalized markdown from provider output.

    if not markdown:  # Validate model produced usable output.
        raise RuntimeError("Groq OCR response was empty.")  # Raise explicit runtime error for empty model output.

    _save_markdown_result(markdown)  # Persist markdown for local inspection and traceability.

    return {  # Return structured response consumed by routes and exports.
        "engine": engine_model,  # Report actual model used (primary or fallback).
        "raw_text": markdown,  # Preserve generated markdown as raw output.
        "notes_text": markdown,  # Provide normalized notes text field for downstream functions.
    }  # Close result payload.


def process_text_transcript(notes_text: str) -> dict:  # Process .txt uploads through text-only formatting pipeline.
    if not notes_text.strip():  # Validate transcript has meaningful content.
        raise ValueError("No text content provided.")  # Fail fast for empty text uploads.

    message = HumanMessage(  # Build text-only message for transcript formatting.
        content=[  # Use single text block for model input.
            {"type": "text", "text": f"{TEXT_PROMPT}\n\nTranscript:\n{notes_text}"},  # Concatenate instructions with uploaded transcript.
        ]  # Close content list.
    )  # Close HumanMessage creation.

    response, engine_model = _invoke_groq_with_fallback(message)  # Execute text formatting request with same fallback logic.

    markdown = _extract_markdown_content(getattr(response, "content", ""))  # Normalize model response into markdown.

    if not markdown:  # Guard against empty generation.
        raise RuntimeError("Groq text-format response was empty.")  # Raise explicit error for UI visibility.

    _save_markdown_result(markdown)  # Persist generated markdown snapshot for demo verification.

    return {  # Return consistent output shape with image workflow.
        "engine": engine_model,  # Include effective model metadata.
        "raw_text": markdown,  # Expose raw generated markdown.
        "notes_text": markdown,  # Provide canonical notes text for exports.
    }  # Close result payload.


def process_uploaded_file(filename: str, file_bytes: bytes) -> dict:  # Route uploaded file to correct processing path by extension.
    extension = Path(filename).suffix.lower()  # Extract normalized lowercase file extension.
    if extension not in ALLOWED_UPLOAD_EXTENSIONS:  # Enforce supported input formats.
        raise HTTPException(status_code=400, detail="Unsupported file type.")  # Return user-facing validation error.

    if extension == ".txt":  # Route plain text files to transcript formatter.
        transcript = file_bytes.decode("utf-8", errors="replace")  # Decode bytes to text safely for mixed encodings.
        return process_text_transcript(transcript)  # Process text transcript path.

    return process_image(file_bytes)  # Process image/pdf path via multimodal pipeline.


# -----------------------------
# API Routes
# -----------------------------

@app.get("/health")  # Health endpoint for quick uptime checks.
def health():  # Define health route handler.
    return {"status": "ok"}  # Return simple service status payload.


@app.on_event("startup")  # Register startup hook.
def cleanup_uploads_on_startup() -> None:  # Define startup cleanup routine.
    _wipe_uploads_folder()  # Remove stale files to keep demo filesystem clean.


@app.post("/ocr")  # OCR/format endpoint returning markdown JSON.
async def ocr(background_tasks: BackgroundTasks, file: UploadFile = File(...)):  # Accept async file upload and schedule cleanup task.
    upload_path: Path | None = None  # Track saved temporary path for guaranteed cleanup.
    try:  # Begin request processing.
        data = await file.read()  # Asynchronously read uploaded file bytes.
        if not data:  # Validate non-empty upload.
            raise HTTPException(status_code=400, detail="Empty file upload.")  # Return client error for empty file.

        upload_name = Path(file.filename or "uploaded_image").name  # Normalize/sanitize incoming filename.
        upload_path = UPLOADS_DIR / upload_name  # Build temporary file path inside uploads directory.
        upload_path.write_bytes(data)  # Persist upload so it can be cleaned and inspected during demo.

        result = process_uploaded_file(upload_name, data)  # Process input through txt or vision pipeline.
        background_tasks.add_task(_delete_uploaded_file, upload_path)  # Schedule temp upload deletion after response is sent.
    except HTTPException:  # Preserve explicit HTTP errors.
        if upload_path is not None:  # Check whether temp file was created.
            _delete_uploaded_file(upload_path)  # Cleanup temp file even on error path.
        raise  # Re-raise original HTTP exception.
    except Exception as exc:  # Catch unexpected runtime/provider errors.
        if upload_path is not None:  # Check whether temp file exists.
            _delete_uploaded_file(upload_path)  # Ensure cleanup before returning server error.
        raise HTTPException(status_code=500, detail=f"OCR failed: {exc}") from exc  # Return standardized API error payload.

    return {  # Return successful OCR response to frontend.
        "filename": file.filename,  # Echo original filename for UI context.
        "engine": result["engine"],  # Report model used for generation.
        "text": result["notes_text"],  # Return markdown text for renderer panel.
    }  # Close OCR response payload.


@app.post("/export/pdf")  # Export endpoint returning PDF binary stream.
async def export_pdf(file: UploadFile = File(...)):  # Accept async upload for direct PDF generation.
    try:  # Begin PDF export flow.
        data = await file.read()  # Asynchronously read uploaded bytes.
        if not data:  # Validate upload content.
            raise HTTPException(status_code=400, detail="Empty file upload.")  # Reject empty files with client error.

        source_name = Path(file.filename or "uploaded_file").name  # Normalize source filename for extension routing.
        result = process_uploaded_file(source_name, data)  # Produce markdown from uploaded input.
        notes_text = result["notes_text"]  # Extract markdown text for document rendering.
        out_path = generate_pdf_from_text(notes_text, out_dir=UPLOADS_DIR, stem="smart_notes")  # Generate PDF artifact in uploads folder.
    except HTTPException:  # Preserve handled API errors.
        raise  # Bubble up HTTP status/details unchanged.
    except Exception as exc:  # Handle unexpected export/model failures.
        raise HTTPException(status_code=500, detail=f"PDF export failed: {exc}") from exc  # Return consistent 500 response message.

    return FileResponse(  # Stream generated PDF as downloadable response.
        path=out_path,  # Point response to generated file path.
        media_type="application/pdf",  # Set PDF content type for browser handling.
        filename=out_path.name,  # Provide friendly download filename.
        background=BackgroundTask(_delete_uploaded_file, out_path),  # Delete generated PDF after response lifecycle begins.
    )  # Close FileResponse payload.


@app.post("/export/docx")  # Export endpoint returning DOCX binary stream.
async def export_docx(file: UploadFile = File(...)):  # Accept async upload for direct DOCX generation.
    try:  # Begin DOCX export flow.
        data = await file.read()  # Asynchronously read uploaded bytes.
        if not data:  # Validate upload content.
            raise HTTPException(status_code=400, detail="Empty file upload.")  # Reject empty files with client error.

        source_name = Path(file.filename or "uploaded_file").name  # Normalize source filename for extension routing.
        result = process_uploaded_file(source_name, data)  # Produce markdown from uploaded input.
        notes_text = result["notes_text"]  # Extract markdown text for DOCX rendering.
        out_path = generate_docx_from_text(notes_text, out_dir=UPLOADS_DIR, stem="smart_notes")  # Generate DOCX artifact in uploads folder.
    except HTTPException:  # Preserve handled API errors.
        raise  # Bubble up HTTP status/details unchanged.
    except Exception as exc:  # Handle unexpected export/model failures.
        raise HTTPException(status_code=500, detail=f"DOCX export failed: {exc}") from exc  # Return consistent 500 response message.

    return FileResponse(  # Stream generated DOCX as downloadable response.
        path=out_path,  # Point response to generated DOCX path.
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",  # Set official DOCX MIME type.
        filename=out_path.name,  # Provide friendly download filename.
        background=BackgroundTask(_delete_uploaded_file, out_path),  # Delete generated DOCX after response lifecycle begins.
    )  # Close FileResponse payload.
