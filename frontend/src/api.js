const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";

function makeFormData(file) {
  const form = new FormData();
  form.append("file", file);
  return form;
}

async function postFormJson(endpoint, file) {
  const res = await fetch(`${API_BASE_URL}${endpoint}`, {
    method: "POST",
    body: makeFormData(file)
  });

  if (!res.ok) {
    const msg = await res.text().catch(() => "");
    throw new Error(msg || `HTTP ${res.status}`);
  }

  return await res.json();
}

function parseFilename(contentDisposition, fallback) {
  if (!contentDisposition) return fallback;

  const utf8Match = contentDisposition.match(/filename\*=UTF-8''([^;]+)/i);
  if (utf8Match?.[1]) {
    return decodeURIComponent(utf8Match[1]);
  }

  const plainMatch = contentDisposition.match(/filename="?([^";]+)"?/i);
  return plainMatch?.[1] || fallback;
}

async function postFormFile(endpoint, file, fallbackName) {
  const res = await fetch(`${API_BASE_URL}${endpoint}`, {
    method: "POST",
    body: makeFormData(file)
  });

  if (!res.ok) {
    const msg = await res.text().catch(() => "");
    throw new Error(msg || `HTTP ${res.status}`);
  }

  const blob = await res.blob();
  const objectUrl = URL.createObjectURL(blob);
  const filename = parseFilename(res.headers.get("content-disposition"), fallbackName);

  return { objectUrl, filename };
}

export function ocrImage(file) {
  return postFormJson("/ocr", file);
}

export function exportPdf(file) {
  return postFormFile("/export/pdf", file, "smart_notes.pdf");
}

export function exportDocx(file) {
  return postFormFile("/export/docx", file, "smart_notes.docx");
}

