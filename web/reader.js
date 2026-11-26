"use strict";

const paper = document.querySelector("#paper");
const status = document.querySelector("#status");
const drive = document.querySelector("#drive");
const disconnect = document.querySelector("#disconnect");
const input = document.querySelector("#file");
const scope = "https://www.googleapis.com/auth/drive.file";
const maxFileBytes = 80 * 1024 * 1024;
const allowedTags = new Set([
  "h1", "h2", "h3", "p", "hr", "small", "em", "strong",
  "details", "summary", "blockquote", "figure", "img"
]);
let readingRequest = 0;
let download;

function copyContent(source, destination) {
  for (const child of source.childNodes) {
    if (child.nodeType === Node.TEXT_NODE) {
      destination.append(document.createTextNode(child.data));
      continue;
    }
    if (child.namespaceURI !== "http://www.w3.org/1999/xhtml" ||
        !allowedTags.has(child.localName)) continue;
    const element = document.createElement(child.localName);
    if (child.localName === "img") {
      const src = child.getAttribute("src");
      if (!src || !/^data:image\/png;base64,iVBORw0KGgo[A-Za-z0-9+/]*={0,2}$/.test(src)) continue;
      element.src = src;
      element.alt = child.getAttribute("alt") || "図表";
      element.loading = "lazy";
    } else {
      if (child.classList.contains("ref")) element.classList.add("ref");
      if (child.classList.contains("center")) element.classList.add("center");
      copyContent(child, element);
    }
    destination.append(element);
  }
}

async function readPaper(load) {
  const request = ++readingRequest;
  download?.abort();
  const controller = new AbortController();
  download = controller;
  status.textContent = "論文を読み込んでいます…";
  try {
    const file = await load(controller.signal);
    if (request !== readingRequest) return;
    if (file.size > maxFileBytes) {
      throw new Error("ファイルが80 MBを超えています。PDFを含めずに書き出したHTMLを選んでください。");
    }
    // Template contents are inert. Only newly created, allowlisted nodes enter the page.
    const template = document.createElement("template");
    template.innerHTML = await file.text();
    if (request !== readingRequest) return;
    const exportedPaper = template.content.querySelector("main");
    const title = exportedPaper?.querySelector("h1")?.textContent.trim();
    if (!title) throw new Error("MLab Web Libraryの読書用ファイル（.html）を選んでください。");
    const content = document.createDocumentFragment();
    copyContent(exportedPaper, content);
    paper.replaceChildren(content);
    status.textContent = title;
    window.scrollTo(0, 0);
  } catch (error) {
    if (request === readingRequest) status.textContent = error.message;
  } finally {
    if (request === readingRequest) download = undefined;
  }
}

input.addEventListener("change", () => {
  const file = input.files[0];
  input.value = "";
  if (file) readPaper(() => file);
});

function loadScript(url) {
  return new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.src = url;
    script.onload = resolve;
    script.onerror = reject;
    document.head.append(script);
  });
}

async function connectDrive(config) {
  await Promise.all([
    loadScript("https://accounts.google.com/gsi/client"),
    loadScript("https://apis.google.com/js/api.js").then(() => new Promise((resolve, reject) => {
      window.gapi.load("picker", { callback: resolve, onerror: reject, timeout: 10000, ontimeout: reject });
    }))
  ]);
  const oauth = window.google.accounts.oauth2;
  const picker = window.google.picker;
  let token = "";
  let expiresAt = 0;

  function openPicker() {
    const view = new picker.DocsView(picker.ViewId.DOCS);
    view.setMode(picker.DocsViewMode.LIST);
    view.setMimeTypes("text/html");
    view.setIncludeFolders(true);
    const selector = new picker.PickerBuilder()
      .addView(view)
      .setAppId(config.projectNumber)
      .setDeveloperKey(config.apiKey)
      .setOAuthToken(token)
      .setOrigin(window.location.origin)
      .setLocale("ja")
      .setTitle("MLab Web Libraryの読書用ファイルを選択")
      .setCallback(result => {
        if (result.action !== picker.Action.PICKED) return;
        const file = result.docs[0];
        if (!token || !file?.id || !file.name?.toLowerCase().endsWith(".html")) {
          status.textContent = "MLab Web Libraryの読書用ファイル（.html）を選んでください。";
          return;
        }
        readPaper(async signal => {
          const url = new URL("https://www.googleapis.com/drive/v3/files/" + encodeURIComponent(file.id));
          url.search = new URLSearchParams({ alt: "media", supportsAllDrives: "true" });
          const headers = { Authorization: "Bearer " + token };
          if (file.resourceKey) headers["X-Goog-Drive-Resource-Keys"] = file.id + "/" + file.resourceKey;
          const response = await fetch(url, { headers, signal, cache: "no-store" });
          if (response.status === 401) {
            expiresAt = 0;
            throw new Error("Google Driveの認証が期限切れです。「Google Driveから開く」を押し直してください。");
          }
          if (!response.ok) {
            throw new Error("Driveからファイルを読めませんでした。アクセス権と同期状況を確認してください。");
          }
          return response.blob();
        });
      })
      .build();
    selector.setVisible(true);
  }

  function finishAuthorization(message) {
    drive.disabled = false;
    status.textContent = message;
  }

  const login = oauth.initTokenClient({
    client_id: config.clientId,
    scope,
    include_granted_scopes: false,
    callback: response => {
      if (response.error || !response.access_token || !oauth.hasGrantedAllScopes(response, scope)) {
        finishAuthorization("Google Driveへのアクセスは許可されませんでした。");
        return;
      }
      token = response.access_token;
      expiresAt = Date.now() + Number(response.expires_in) * 1000;
      disconnect.hidden = false;
      finishAuthorization("MLab Web Libraryの読書用ファイルを選んでください。");
      openPicker();
    },
    error_callback: () => finishAuthorization("Google認証を開けませんでした。ポップアップ設定を確認して再試行してください。")
  });
  drive.addEventListener("click", () => {
    if (token && Date.now() + 5000 < expiresAt) {
      openPicker();
      return;
    }
    drive.disabled = true;
    login.requestAccessToken({ prompt: token ? "" : "select_account" });
  });
  disconnect.addEventListener("click", () => {
    ++readingRequest;
    download?.abort();
    download = undefined;
    const revokedToken = token;
    token = "";
    expiresAt = 0;
    paper.replaceChildren();
    disconnect.hidden = true;
    status.textContent = "Google連携を解除しています…";
    drive.disabled = true;
    oauth.revoke(revokedToken, result => finishAuthorization(result.successful
      ? "Google連携を解除しました。"
      : "この画面の連携を終了しました。Googleアカウント設定からアクセス許可を取り消せます。"));
  });
  drive.disabled = false;
}

const config = window.mlabGoogleDrive;
if (config?.clientId && config.apiKey && config.projectNumber) {
  connectDrive(config).catch(() => {
    drive.title = "Google Drive連携を読み込めませんでした。";
    status.textContent = drive.title + " 端末のファイルは開けます。";
  });
} else {
  drive.hidden = true;
  status.textContent += " Google Drive連携は現在準備中です。";
}
