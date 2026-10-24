"use client";

import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import { api, type FilePreview as Preview, type StoredFile } from "@/lib/api";

function PdfPreview({ url }: { url: string }) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const [page, setPage] = useState(1);
  const [pages, setPages] = useState(0);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    let cleanup: (() => void) | undefined;
    async function draw() {
      try {
        const pdfjs = await import("pdfjs-dist");
        pdfjs.GlobalWorkerOptions.workerSrc = new URL(
          "pdfjs-dist/build/pdf.worker.min.mjs", import.meta.url,
        ).toString();
        const task = pdfjs.getDocument({ url, isEvalSupported: false, useSystemFonts: false });
        cleanup = () => { void task.destroy(); };
        const document = await task.promise;
        if (cancelled) return;
        setPages(document.numPages);
        const pdfPage = await document.getPage(page);
        if (cancelled || !canvas.current) return;
        const viewport = pdfPage.getViewport({ scale: Math.min(1.6, 850 / pdfPage.getViewport({ scale: 1 }).width) });
        const context = canvas.current.getContext("2d");
        if (!context) return;
        canvas.current.width = Math.ceil(viewport.width);
        canvas.current.height = Math.ceil(viewport.height);
        await pdfPage.render({ canvas: canvas.current, canvasContext: context, viewport }).promise;
      } catch {
        if (!cancelled) setError("This PDF could not be rendered.");
      }
    }
    void draw();
    return () => { cancelled = true; cleanup?.(); };
  }, [url, page]);

  if (error) return <p role="alert">{error}</p>;
  return <div className="pdf-preview">
    <div className="preview-controls">
      <button className="secondary" disabled={page <= 1} onClick={() => setPage(page - 1)}>Previous</button>
      <span>Page {page} of {pages || "…"}</span>
      <button className="secondary" disabled={!pages || page >= pages} onClick={() => setPage(page + 1)}>Next</button>
    </div>
    <canvas ref={canvas} aria-label={`PDF page ${page}`} />
  </div>;
}

export default function FilePreview({ file }: { file: StoredFile }) {
  const [preview, setPreview] = useState<Preview | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    let objectUrl: string | undefined;
    api.preview(file.id, controller.signal).then((result) => {
      if (controller.signal.aborted) {
        if ("url" in result) URL.revokeObjectURL(result.url);
        return;
      }
      if ("url" in result) objectUrl = result.url;
      setPreview(result);
    }).catch((reason: Error) => {
      if (!controller.signal.aborted) setError(reason.message);
    });
    return () => { controller.abort(); if (objectUrl) URL.revokeObjectURL(objectUrl); };
  }, [file.id]);

  if (error) return <p className="form-error" role="alert">{error}</p>;
  if (!preview) return <p role="status">Loading preview…</p>;
  // Private blob URLs cannot be routed through the Next image optimizer.
  // eslint-disable-next-line @next/next/no-img-element
  if (preview.kind === "image") return <img className="image-preview" src={preview.url} alt={file.filename} />;
  if (preview.kind === "pdf") return <PdfPreview url={preview.url} />;
  if (preview.kind === "table") return <div className="table-preview"><table><tbody>
    {preview.rows.map((row, index) => <tr key={index}>{row.map((cell, col) =>
      index === 0 ? <th key={col} scope="col">{cell}</th> : <td key={col}>{cell}</td>)}</tr>)}
  </tbody></table>{preview.truncated && <p>Showing the first part of this file.</p>}</div>;
  return <div className="source-preview">
    {preview.kind === "markdown" ? <div className="markdown-preview"><ReactMarkdown components={{
      img: ({ alt }) => <span>[Image: {alt || "embedded image"}]</span>,
      a: ({ href, children }) => href && /^https?:\/\//i.test(href)
        ? <a href={href} target="_blank" rel="noopener noreferrer">{children}</a> : <span>{children}</span>,
    }}>{preview.text}</ReactMarkdown></div>
      : <pre><code>{preview.text}</code></pre>}
    {preview.truncated && <p>Showing the first part of this file.</p>}
  </div>;
}
