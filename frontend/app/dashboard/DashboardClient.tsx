"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { api, type StoredFile, type User } from "@/lib/api";
import FilePreview from "./FilePreview";
import { ToastViewport, useToast } from "../Toast";

const MAX_SIZE = 5 * 1024 * 1024;
const PAGE_SIZE = 10;
type Modal = { kind: "upload" } | { kind: "draft" | "preview"; file: StoredFile } | null;

function Icon({ name }: { name: "download" | "drive" | "mail" | "preview" }) {
  return <svg aria-hidden="true" width="20" height="20" viewBox="0 0 24 24" fill="none"
    stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
    {name === "download" && <path d="M12 3v12m-4-4 4 4 4-4M4 17v3h16v-3" />}
    {name === "drive" && <path d="M7 17a5 5 0 0 1-.8-9.9A6 6 0 0 1 17.8 9 4 4 0 1 1 18 17h-2m-4 3V10m-3 3 3-3 3 3" />}
    {name === "mail" && <path d="M3 6h18v12H3zM3 7l9 7 9-7" />}
    {name === "preview" && <><path d="M2 12s3.5-6 10-6 10 6 10 6-3.5 6-10 6S2 12 2 12Z" /><circle cx="12" cy="12" r="2.5" /></>}
  </svg>;
}

export default function DashboardClient({ user, initialMessage }: { user: User; initialMessage: string }) {
  const router = useRouter();
  const dialogRef = useRef<HTMLDialogElement>(null);
  const [files, setFiles] = useState<StoredFile[]>([]);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [refresh, setRefresh] = useState(0);
  const [loadingFiles, setLoadingFiles] = useState(true);
  const [googleConnected, setGoogleConnected] = useState(false);
  const [gmailReady, setGmailReady] = useState(false);
  const [googleEmail, setGoogleEmail] = useState<string | null>(null);
  const [modal, setModal] = useState<Modal>(null);
  const [selected, setSelected] = useState<File | null>(null);
  const [draftEmail, setDraftEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const { toast, showToast, dismissToast } = useToast(initialMessage);

  useEffect(() => {
    let active = true;
    api.files(page, PAGE_SIZE).then((result) => {
      if (!active) return;
      setFiles(result.items);
      setTotal(result.total);
    }).catch((error: Error) => {
      if (active) showToast(error.message, "error");
    }).finally(() => {
      if (active) setLoadingFiles(false);
    });
    return () => { active = false; };
  }, [page, refresh, showToast]);

  useEffect(() => {
    api.googleStatus().then((status) => {
      setGoogleConnected(status.connected);
      setGoogleEmail(status.email);
      setGmailReady(status.gmail_ready);
    }).catch((error: Error) => showToast(error.message, "error"));
  }, [showToast]);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (modal && !dialog.open) dialog.showModal();
    if (!modal && dialog.open) dialog.close();
  }, [modal]);

  function closeModal() {
    if (busy) return;
    setModal(null);
    setSelected(null);
    setDraftEmail("");
  }

  async function upload(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selected) return;
    if (selected.size === 0 || selected.size > MAX_SIZE) {
      showToast("Choose a file up to 5 MiB.", "error");
      return;
    }
    setBusy(true);
    try {
      await api.upload(selected);
      setPage(1);
      setRefresh((value) => value + 1);
      setLoadingFiles(true);
      setModal(null);
      setSelected(null);
      showToast("File uploaded.");
    } catch (error) {
      showToast((error as Error).message, "error");
    } finally {
      setBusy(false);
    }
  }

  async function sendToDrive(file: StoredFile) {
    setBusy(true);
    try {
      const result = await api.sendToDrive(file.id);
      setFiles((current) => current.map((item) => item.id === file.id
        ? { ...item, drive_file_id: result.drive_file_id } : item));
      showToast(result.uploaded ? "Saved to Drive." : "Already in Drive.");
    } catch (error) {
      showToast((error as Error).message, "error");
    } finally {
      setBusy(false);
    }
  }

  async function createDraft(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (modal?.kind !== "draft" || !draftEmail.trim()) return;
    const gmailTab = window.open("about:blank", "_blank");
    if (gmailTab) {
      gmailTab.opener = null;
      gmailTab.document.body.textContent = "Creating your Gmail draft…";
    }
    setBusy(true);
    try {
      await api.createGmailDraft(modal.file.id, draftEmail.trim());
      const gmailUrl = "https://mail.google.com/mail/#drafts";
      if (gmailTab) gmailTab.location.replace(gmailUrl);
      else window.location.assign(gmailUrl);
      setModal(null);
      setDraftEmail("");
      showToast("Gmail draft created. Review it before sending.");
    } catch (error) {
      gmailTab?.close();
      showToast((error as Error).message, "error");
    } finally {
      setBusy(false);
    }
  }

  async function logout() {
    try { await api.logout(); router.replace("/"); router.refresh(); }
    catch (error) { showToast((error as Error).message, "error"); }
  }

  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE));
  return <main className="shell">
    <header className="header-row">
      <div><p className="eyebrow">FILE VAULT <span aria-hidden="true">/</span> YOUR WORKSPACE</p><h1>YOUR FILES<span className="accent-text">.</span></h1><p className="account-label">Signed in as <strong>{user.email}</strong></p></div>
      <button className="secondary" onClick={logout}>Sign out</button>
    </header>

    <section className="card">
      <div className="section-heading">
        <div><div className="step">01 / LIBRARY</div><h2>Stored files</h2></div>
        <button onClick={() => setModal({ kind: "upload" })}>+ Upload file</button>
      </div>
      <p>{googleConnected
        ? `Connected to ${googleEmail ?? "Google"}. Drive and Gmail actions use this account.`
        : "Connect Google to copy files to Drive or create Gmail drafts."}</p>
      {!googleConnected && <a className="button" href={api.googleConnectUrl}>Connect Google</a>}
      {googleConnected && !gmailReady && <a className="button" href={api.googleConnectUrl}>Reconnect for Gmail access</a>}

      <div className="file-list" aria-busy={loadingFiles}>
        {loadingFiles && <p>Loading files…</p>}
        {!loadingFiles && files.length === 0 && <p>No files yet.</p>}
        {!loadingFiles && files.map((file) => <div className="file-row" key={file.id}>
          <div className="file-details"><strong>{file.filename}</strong>
            <small>{(file.size_bytes / 1024).toFixed(1)} KB · {file.drive_file_id ? "In Drive" : "Private"}</small>
          </div>
          <div className="file-actions">
            <button className="icon-button" aria-label={`Preview ${file.filename}`} title="Preview"
              onClick={() => setModal({ kind: "preview", file })}><Icon name="preview" /></button>
            <a className="icon-button" href={api.downloadUrl(file.id)}
              aria-label={`Download ${file.filename}`} title="Download"><Icon name="download" /></a>
            <button className="icon-button" disabled={busy || !googleConnected || Boolean(file.drive_file_id)}
              aria-label={file.drive_file_id ? `${file.filename} is in Drive` : `Save ${file.filename} to Drive`}
              title={file.drive_file_id ? "Already in Drive" : "Save to Drive"}
              onClick={() => sendToDrive(file)}><Icon name="drive" /></button>
            <button className="icon-button" disabled={busy || !gmailReady}
              aria-label={`Create Gmail draft with ${file.filename}`} title="Share by Gmail draft"
              onClick={() => setModal({ kind: "draft", file })}><Icon name="mail" /></button>
          </div>
        </div>)}
      </div>
      <nav className="pagination" aria-label="File pages">
        <span>{total === 0 ? "0 files" : `${(page - 1) * PAGE_SIZE + 1}–${Math.min(page * PAGE_SIZE, total)} of ${total}`}</span>
        <div>
          <button className="secondary" disabled={loadingFiles || page === 1}
            onClick={() => { setLoadingFiles(true); setPage((value) => value - 1); }}>Previous</button>
          <span>Page {page} of {pageCount}</span>
          <button className="secondary" disabled={loadingFiles || page >= pageCount}
            onClick={() => { setLoadingFiles(true); setPage((value) => value + 1); }}>Next</button>
        </div>
      </nav>
    </section>

    <dialog ref={dialogRef} className={`action-modal${modal?.kind === "preview" ? " preview-modal" : ""}`} onClose={closeModal}
      onCancel={(event) => { if (busy) event.preventDefault(); else closeModal(); }}
      aria-labelledby="modal-title">
      {modal?.kind === "upload" && <>
        <h2 id="modal-title">Upload a private file</h2>
        <p>Choose a file up to 5 MiB.</p>
        <form onSubmit={upload} className="modal-form">
          <label htmlFor="upload-file">File</label>
          <input id="upload-file" type="file" required onChange={(event) => setSelected(event.target.files?.[0] ?? null)} />
          <div className="modal-actions"><button type="button" className="secondary" onClick={closeModal} disabled={busy}>Cancel</button>
            <button disabled={busy || !selected}>Save file</button></div>
        </form>
      </>}
      {modal?.kind === "draft" && <>
        <h2 id="modal-title">Create Gmail draft</h2>
        <p>Attach <strong>{modal.file.filename}</strong> to a draft in {googleEmail ?? "your connected Gmail"}. Review it in Gmail before sending.</p>
        <form onSubmit={createDraft} className="modal-form">
          <label htmlFor="recipient-email">Recipient email</label>
          <input id="recipient-email" type="email" required placeholder="recipient@gmail.com"
            value={draftEmail} onChange={(event) => setDraftEmail(event.target.value)} />
          <div className="modal-actions"><button type="button" className="secondary" onClick={closeModal} disabled={busy}>Cancel</button>
            <button disabled={busy || !draftEmail.trim()}>Create draft</button></div>
        </form>
      </>}
      {modal?.kind === "preview" && <>
        <div className="preview-heading"><h2 id="modal-title">{modal.file.filename}</h2>
          <button className="secondary" onClick={closeModal} aria-label="Close preview">Close</button></div>
        <FilePreview key={modal.file.id} file={modal.file} />
      </>}
      {modal && <ToastViewport toast={toast} onDismiss={dismissToast} />}
    </dialog>
    {!modal && <ToastViewport toast={toast} onDismiss={dismissToast} />}
    <footer><span>FILE VAULT © 2026</span><span>PRIVATE BY DEFAULT.</span></footer>
  </main>;
}
