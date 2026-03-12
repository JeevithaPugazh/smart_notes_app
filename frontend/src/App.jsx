import { useEffect, useState } from "react"; // Import React hooks for component state and lifecycle cleanup.
import ReactMarkdown from "react-markdown"; // Render markdown returned by backend into styled HTML.
import { exportDocx, exportPdf, ocrImage } from "./api.js"; // API helpers that call FastAPI OCR/export endpoints.
import MagicLoading from "./MagicLoading.jsx"; // Loading animation shown during asynchronous conversion.
import "./App.css"; // Component stylesheet containing light-purple glassmorphism layout.

const UploadIcon = () => ( // Upload icon for drag/click file input affordance.
  <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="#7c3aed" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"> {/* Purple-stroked SVG to match accent theme. */}
    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" /> {/* Tray line conveys upload destination. */}
    <polyline points="17 8 12 3 7 8" /> {/* Arrowhead showing upward transfer. */}
    <line x1="12" y1="3" x2="12" y2="15" /> {/* Arrow shaft for clear icon readability. */}
  </svg>
); // End UploadIcon component.

const FileIcon = () => ( // Small badge icon shown next to selected filename.
  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#7c3aed" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"> {/* Compact outlined document icon. */}
    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" /> {/* File outline path. */}
    <polyline points="14 2 14 8 20 8" /> {/* Folded corner detail for document appearance. */}
  </svg>
); // End FileIcon component.

const ImagePlaceholderIcon = () => ( // Placeholder icon when no preview is available in left panel.
  <svg width="42" height="42" viewBox="0 0 24 24" fill="none" stroke="#b7acd8" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round"> {/* Muted lavender stroke for inactive state. */}
    <rect x="3" y="3" width="18" height="18" rx="2" /> {/* Photo frame boundary. */}
    <circle cx="8.5" cy="8.5" r="1.5" /> {/* Sun/indicator point in image icon. */}
    <polyline points="21 15 16 10 5 21" /> {/* Mountain lines in image placeholder. */}
  </svg>
); // End ImagePlaceholderIcon component.

const DocPlaceholderIcon = () => ( // Placeholder icon when no generated textbook result exists yet.
  <svg width="42" height="42" viewBox="0 0 24 24" fill="none" stroke="#b7acd8" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round"> {/* Match inactive placeholder visual style. */}
    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" /> {/* Document outline. */}
    <polyline points="14 2 14 8 20 8" /> {/* Folded corner accent. */}
    <line x1="16" y1="13" x2="8" y2="13" /> {/* Text line 1 indicator. */}
    <line x1="16" y1="17" x2="8" y2="17" /> {/* Text line 2 indicator. */}
    <polyline points="10 9 9 9 8 9" /> {/* Small marker line detail. */}
  </svg>
); // End DocPlaceholderIcon component.

const SparkleLogo = () => ( // Brand mark for Smart Notes header identity.
  <svg className="brand-logo" viewBox="0 0 24 24" aria-hidden="true"> {/* Animated logo, decorative only for screen readers. */}
    <defs> {/* Define reusable gradient fill for sparkle star. */}
      <linearGradient id="brandStar" x1="0%" y1="0%" x2="100%" y2="100%"> {/* Purple-blue diagonal gradient. */}
        <stop offset="0%" stopColor="#93c5fd" /> {/* Light blue gradient start. */}
        <stop offset="60%" stopColor="#c4b5fd" /> {/* Lavender midpoint. */}
        <stop offset="100%" stopColor="#5eead4" /> {/* Mint endpoint for subtle contrast. */}
      </linearGradient>
    </defs>
    <path d="M12 2.2l1.9 5.9L20 10l-6.1 1.9L12 17.8l-1.9-5.9L4 10l6.1-1.9L12 2.2z" fill="url(#brandStar)" /> {/* Star path with animated glow in CSS. */}
  </svg>
); // End SparkleLogo component.

/**
 * Smart Notes dashboard component.
 *
 * Use-case flow:
 * 1) User uploads image/pdf/txt.
 * 2) Frontend calls `/ocr` for markdown plus `/export/pdf` and `/export/docx` in parallel.
 * 3) Backend handles Groq processing and BackgroundTask cleanup after responses are sent.
 */
export default function App() { // Main React component export.
  const [file, setFile] = useState(null); // Store currently selected file object.
  const [previewName, setPreviewName] = useState(""); // Track selected file name for UI badge.
  const [previewUrl, setPreviewUrl] = useState(""); // Hold object URL for image preview rendering.
  const [previewText, setPreviewText] = useState(""); // Hold decoded text for .txt preview pane.
  const [previewMode, setPreviewMode] = useState("none"); // Control left panel mode: image, text, or none.
  const [notesText, setNotesText] = useState(""); // Store markdown textbook output returned by OCR endpoint.
  const [loading, setLoading] = useState(false); // Track asynchronous conversion state for UX feedback.
  const [error, setError] = useState(""); // Store API error message for user-facing alert.
  const [pdfUrl, setPdfUrl] = useState(""); // Object URL for generated PDF download link.
  const [docxUrl, setDocxUrl] = useState(""); // Object URL for generated DOCX download link.
  const [pdfName, setPdfName] = useState("smart_notes.pdf"); // Download filename for PDF anchor.
  const [docxName, setDocxName] = useState("smart_notes.docx"); // Download filename for DOCX anchor.

  function revokeDownloadUrls() { // Release generated object URLs to avoid browser memory leaks.
    if (pdfUrl) URL.revokeObjectURL(pdfUrl); // Revoke PDF blob URL when stale/replaced.
    if (docxUrl) URL.revokeObjectURL(docxUrl); // Revoke DOCX blob URL when stale/replaced.
  } // End URL cleanup helper.

  function resetOutputState() { // Reset conversion outputs when input file changes.
    setNotesText(""); // Clear old markdown result.
    setError(""); // Clear previous error state.
    setPdfUrl(""); // Clear previous PDF URL.
    setDocxUrl(""); // Clear previous DOCX URL.
    setPdfName("smart_notes.pdf"); // Reset default PDF filename.
    setDocxName("smart_notes.docx"); // Reset default DOCX filename.
  } // End reset helper.

  useEffect(() => { // Register component unmount cleanup for object URLs.
    return () => { // Return cleanup callback executed on dependency change/unmount.
      if (previewUrl) URL.revokeObjectURL(previewUrl); // Revoke image preview object URL.
      revokeDownloadUrls(); // Revoke export object URLs.
    }; // End cleanup function.
  }, [previewUrl, pdfUrl, docxUrl]); // Re-run cleanup binding when any URL reference changes.

  async function onFileChange(event) { // Handle file input selection and generate local preview.
    const nextFile = event.target.files?.[0] ?? null; // Read first selected file safely.
    setFile(nextFile); // Persist selected file for API submission.
    setPreviewName(nextFile ? nextFile.name : ""); // Update filename badge label.

    if (previewUrl) URL.revokeObjectURL(previewUrl); // Free previous image preview URL.
    revokeDownloadUrls(); // Free previous export blob URLs when file changes.

    setPreviewUrl(""); // Clear image preview state before mode detection.
    setPreviewText(""); // Clear text preview state before mode detection.
    setPreviewMode("none"); // Reset panel mode until file type is known.

    if (nextFile) { // Continue only when a file was actually selected.
      const fileExt = nextFile.name.split(".").pop()?.toLowerCase() || ""; // Get lowercase extension for fallback type detection.
      const isImage = nextFile.type.startsWith("image/"); // Detect browser-recognized image MIME types.
      const isTxt = nextFile.type.startsWith("text/") || fileExt === "txt"; // Detect plain text uploads by MIME or extension.

      if (isImage) { // Build image preview path.
        setPreviewUrl(URL.createObjectURL(nextFile)); // Generate temporary browser URL for image rendering.
        setPreviewMode("image"); // Switch left panel to image mode.
      } else if (isTxt) { // Build text preview path.
        const textContent = await nextFile.text(); // Asynchronously decode selected text file client-side.
        setPreviewText(textContent); // Save decoded text for notepad-style preview.
        setPreviewMode("text"); // Switch left panel to text mode.
      } // End type-specific preview handling.
    } // End nextFile guard.

    resetOutputState(); // Clear old conversion output when new input is selected.
  } // End file change handler.

  async function onConvert(event) { // Trigger full conversion flow: OCR + exports.
    event.preventDefault(); // Stop default form submission to keep SPA behavior.
    if (!file || loading) return; // Guard against missing input or duplicate in-flight request.

    setLoading(true); // Show loading indicator and disable convert button.
    setError(""); // Clear old error message before new request cycle.
    revokeDownloadUrls(); // Clear old export URLs to prevent stale downloads.
    setPdfUrl(""); // Reset PDF URL while waiting for new export.
    setDocxUrl(""); // Reset DOCX URL while waiting for new export.
    setNotesText(""); // Reset markdown panel while new generation runs.

    try { // Begin asynchronous API workflow.
      const [ocrRes, pdfRes, docxRes] = await Promise.all([ // Run all endpoints in parallel to reduce total wait time.
        ocrImage(file), // Calls FastAPI /ocr route (Groq processing + BackgroundTasks cleanup of temp upload).
        exportPdf(file), // Calls FastAPI /export/pdf route (FileResponse + BackgroundTask file deletion).
        exportDocx(file), // Calls FastAPI /export/docx route (FileResponse + BackgroundTask file deletion).
      ]); // End parallel API calls.

      setNotesText(ocrRes.text || ""); // Update right panel with generated markdown result.
      setPdfUrl(pdfRes.objectUrl || ""); // Save returned PDF blob URL for download anchor.
      setDocxUrl(docxRes.objectUrl || ""); // Save returned DOCX blob URL for download anchor.
      setPdfName(pdfRes.filename || "smart_notes.pdf"); // Save backend-provided PDF filename.
      setDocxName(docxRes.filename || "smart_notes.docx"); // Save backend-provided DOCX filename.
    } catch (err) { // Handle request failures from any endpoint.
      setError(err?.message || "Conversion failed"); // Surface readable error message to user.
    } finally { // Always execute after try/catch.
      setLoading(false); // Exit loading mode regardless of success/failure.
    } // End request lifecycle cleanup.
  } // End convert handler.

  const hasDownloads = !!pdfUrl || !!docxUrl; // Compute whether at least one export is available.
  const btnDisabled = !file || loading; // Disable convert action when input missing or request in progress.

  return ( // Render fixed-height dashboard layout.
    <div className="app-shell"> {/* App root shell locked to viewport height in CSS. */}
      <div className="dashboard-glass"> {/* Main glassmorphism container for dashboard content. */}
        <header className="dash-header"> {/* Top navigation header with brand identity. */}
          <div className="brand-wrap"> {/* Left-aligned brand group. */}
            <SparkleLogo /> {/* Animated sparkle logo. */}
            <div className="brand-text"> {/* Brand title/subtitle container. */}
              <h1>Smart Notes</h1> {/* Product name shown in top-left corner. */}
              <p>AI textbook generator</p> {/* Compact descriptor for the app purpose. */}
            </div>
          </div>
          <div className="nav-pill">Vision + Text Pipeline</div> {/* Status badge indicating multimodal support. */}
        </header>

        <form onSubmit={onConvert} className="dash-toolbar"> {/* Toolbar form binds submit to async conversion handler. */}
          <label className="upload-zone"> {/* Styled upload drop area wrapping hidden file input. */}
            <span className="upload-icon-wrap"> {/* Circular icon background container. */}
              <UploadIcon /> {/* Upload icon. */}
            </span>
            <span className="upload-copy">Drop your notes here or click to browse: JPG, PNG, PDF, TXT</span> {/* Supported file type guidance. */}
            <input type="file" accept="image/*,.pdf,.txt" onChange={onFileChange} className="hidden-input" /> {/* Hidden native file input that triggers preview workflow. */}
          </label>

          {previewName && ( // Show selected file badge only when a file is chosen.
            <div className="selected-file"> {/* Compact selected-file metadata chip. */}
              <FileIcon /> {/* File icon for visual cue. */}
              <span>{previewName}</span> {/* Display selected filename text. */}
            </div>
          )} {/* End selected-file conditional block. */}

          <button type="submit" className="convert-btn" disabled={btnDisabled}> {/* Primary action button for conversion workflow. */}
            {loading ? "Converting..." : "Convert"} {/* Dynamic button label based on async state. */}
          </button>
        </form>

        {error && <div className="error-banner">{error}</div>} {/* Render validation/runtime errors in alert banner. */}

        <main className="dash-main"> {/* Two-panel content area with independent scroll containers. */}
          <section className="panel panel-preview"> {/* Left panel: original uploaded content preview. */}
            <div className="panel-head"> {/* Fixed panel header area. */}
              <div className="panel-title">Original Notes</div> {/* Left panel title label. */}
            </div>
            <div className="panel-scroll preview-scroll"> {/* Scrollable preview content wrapper. */}
              {previewMode === "image" && previewUrl ? ( // Image preview rendering path.
                <img src={previewUrl} alt={previewName || "Uploaded notes"} className="preview-image" /> // Render uploaded image preview.
              ) : previewMode === "text" ? ( // Text preview rendering path.
                <div className="notepad-box"> {/* Notepad-styled container for text uploads. */}
                  <div className="notepad-head">Notepad Preview</div> {/* Sub-header clarifies this is transcript content. */}
                  <pre>{previewText || "(This text file is empty)"}</pre> {/* Preserve line breaks/spacing for note readability. */}
                </div>
              ) : ( // Empty-state rendering path.
                <div className="panel-placeholder"> {/* Placeholder container for no-file state. */}
                  <ImagePlaceholderIcon /> {/* Placeholder icon. */}
                  <span>Uploaded content preview appears here</span> {/* Placeholder helper text. */}
                </div>
              )} {/* End preview mode conditional rendering. */}
            </div>
          </section>

          <section className="panel panel-result"> {/* Right panel: AI generated textbook output. */}
            <div className="result-actions"> {/* Sticky header with title + downloads. */}
              <span className="panel-title">AI Textbook</span> {/* Right panel title label. */}
              <div className="download-actions"> {/* Download button group. */}
                {pdfUrl && ( // Show PDF button only when URL exists.
                  <a href={pdfUrl} download={pdfName} className="download-btn download-pdf">Download PDF</a> // PDF file download trigger.
                )}
                {docxUrl && ( // Show DOCX button only when URL exists.
                  <a href={docxUrl} download={docxName} className="download-btn download-docx">Download Word</a> // DOCX file download trigger.
                )}
              </div>
            </div>

            <div className="panel-scroll result-scroll"> {/* Scrollable markdown result container. */}
              {loading ? ( // Show loading visual while async APIs are processing.
                <MagicLoading /> // Display custom loading animation.
              ) : notesText ? ( // Show markdown only when OCR text exists.
                <div className="md-prose result-enter"> {/* Styled markdown wrapper with appearance animation. */}
                  <ReactMarkdown>{notesText}</ReactMarkdown> {/* Convert markdown text to rendered HTML. */}
                </div>
              ) : ( // Empty-state before first conversion.
                <div className="panel-placeholder"> {/* Placeholder container for result panel. */}
                  <DocPlaceholderIcon /> {/* Placeholder icon. */}
                  <span>Generated textbook notes appear here</span> {/* Placeholder helper text. */}
                </div>
              )} {/* End result mode conditional rendering. */}
            </div>
          </section>
        </main>

        <footer className="dash-footer"> {/* Footer status bar at bottom of fixed dashboard. */}
          <span>{hasDownloads ? "Downloads ready" : "Convert to unlock exports"}</span> {/* Dynamic status message based on export readiness. */}
        </footer>
      </div>
    </div>
  ); // End component JSX tree.
} // End App component.
