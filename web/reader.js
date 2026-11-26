"use strict";

const paper = document.querySelector("#paper");
const status = document.querySelector("#status");
const input = document.querySelector("#file");
const maxFileBytes = 80 * 1024 * 1024;
const allowedTags = new Set([
  "h1", "h2", "h3", "p", "hr", "small", "em", "strong",
  "details", "summary", "blockquote", "figure", "img"
]);
let readingRequest = 0;

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

async function readPaper(file) {
  const request = ++readingRequest;
  status.textContent = "論文を読み込んでいます…";
  try {
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
  }
}

input.addEventListener("change", () => {
  const file = input.files[0];
  input.value = "";
  if (file) readPaper(file);
});
