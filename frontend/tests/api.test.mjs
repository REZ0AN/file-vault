import assert from "node:assert/strict";
import { test } from "node:test";

import { api, ApiError } from "../lib/api.ts";

test("password login sends a credentialed JSON request", async (t) => {
  let observed;
  t.mock.method(globalThis, "fetch", async (url, init) => {
    observed = { url, init };
    return Response.json({ id: "user-1", email: "alice@example.com" });
  });

  const user = await api.login("alice@example.com", "secret-password");
  assert.equal(user.email, "alice@example.com");
  assert.match(observed.url, /\/api\/v1\/auth\/login$/);
  assert.equal(observed.init.credentials, "include");
  assert.equal(observed.init.method, "POST");
  assert.deepEqual(JSON.parse(observed.init.body), {
    email: "alice@example.com", password: "secret-password",
  });
});

test("upload sends multipart data to the central storage file route", async (t) => {
  let observed;
  t.mock.method(globalThis, "fetch", async (url, init) => {
    observed = { url, init };
    return Response.json({ id: "file-1", filename: "note.txt" }, { status: 201 });
  });
  const file = new File(["hello"], "note.txt", { type: "text/plain" });
  const saved = await api.upload(file);
  assert.equal(saved.id, "file-1");
  assert.match(observed.url, /\/api\/v1\/files$/);
  assert.equal(observed.init.credentials, "include");
  assert.equal(observed.init.body.get("file").name, "note.txt");
});

test("file list requests a bounded page and reads pagination metadata", async (t) => {
  let observed;
  t.mock.method(globalThis, "fetch", async (url, init) => {
    observed = { url, init };
    return Response.json({ items: [{ id: "file-1" }], total: 12, page: 2, page_size: 10 });
  });
  const result = await api.files(2, 10);
  assert.equal(result.total, 12);
  assert.equal(result.items[0].id, "file-1");
  assert.match(observed.url, /\/api\/v1\/files\?page=2&page_size=10$/);
  assert.equal(observed.init.credentials, "include");
});

test("sending to Drive uses the stored file ID and surfaces backend errors", async (t) => {
  let observed;
  t.mock.method(globalThis, "fetch", async (url, init) => {
    observed = { url, init };
    return Response.json({ detail: "Connect Google Drive first" }, { status: 409 });
  });
  await assert.rejects(api.sendToDrive("file-1"), (error) => {
    assert.ok(error instanceof ApiError);
    assert.equal(error.status, 409);
    assert.equal(error.message, "Connect Google Drive first");
    return true;
  });
  assert.match(observed.url, /\/api\/v1\/files\/file-1\/drive$/);
  assert.deepEqual(JSON.parse(observed.init.body), {});
});

test("draft creation sends the recipient address for a stored file", async (t) => {
  let observed;
  t.mock.method(globalThis, "fetch", async (url, init) => {
    observed = { url, init };
    return Response.json({ draft_id: "draft-1", recipient: "friend@gmail.com" });
  });
  const draft = await api.createGmailDraft("file-1", "friend@gmail.com");
  assert.equal(draft.recipient, "friend@gmail.com");
  assert.equal(draft.draft_id, "draft-1");
  assert.match(observed.url, /\/api\/v1\/files\/file-1\/gmail-draft$/);
  assert.equal(observed.init.credentials, "include");
  assert.deepEqual(JSON.parse(observed.init.body), { email: "friend@gmail.com" });
});

test("preview fetches owner-protected text without caching", async (t) => {
  let observed;
  t.mock.method(globalThis, "fetch", async (url, init) => {
    observed = { url, init };
    return Response.json({ kind: "text", text: "<script>safe source</script>", truncated: false });
  });
  const result = await api.preview("file-1");
  assert.equal(result.kind, "text");
  assert.equal(result.text, "<script>safe source</script>");
  assert.match(observed.url, /\/api\/v1\/files\/file-1\/preview$/);
  assert.equal(observed.init.credentials, "include");
  assert.equal(observed.init.cache, "no-store");
});

test("preview creates a local URL for private PDF bytes", async (t) => {
  t.mock.method(globalThis, "fetch", async () => new Response(new Blob(["%PDF-1.7"], {
    type: "application/pdf",
  }), { headers: { "Content-Type": "application/pdf" } }));
  const result = await api.preview("file-2");
  assert.equal(result.kind, "pdf");
  assert.match(result.url, /^blob:/);
  URL.revokeObjectURL(result.url);
});
