(() => {
  const textarea = document.getElementById("anvaya-note-body");
  const fileInput = document.getElementById("anvaya-note-files");
  const selectedTray = document.getElementById("anvaya-selected-media");

  const replaceSelection = (before, after = "") => {
    if (!textarea) return;
    const start = textarea.selectionStart ?? textarea.value.length;
    const end = textarea.selectionEnd ?? start;
    const selected = textarea.value.slice(start, end);
    textarea.setRangeText(before + selected + after, start, end, "end");
    textarea.focus();
  };

  document.querySelectorAll("[data-note-insert]").forEach((button) => {
    button.addEventListener("click", () => replaceSelection(button.dataset.noteInsert || ""));
  });

  document.querySelectorAll("[data-note-wrap]").forEach((button) => {
    button.addEventListener("click", () => {
      const token = button.dataset.noteWrap || "";
      replaceSelection(token, token);
    });
  });

  const escapeCaption = (value) =>
    String(value || "")
      .replace(/[|\]]/g, " ")
      .replace(/[\r\n]+/g, " ")
      .replace(/\s+/g, " ")
      .trim()
      .slice(0, 160);

  const escapeHtml = (value) =>
    String(value || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");

  const mediaDirective = (kind, id, container) => {
    const width = container.querySelector("[data-media-width]")?.value || "70";
    const rotate = container.querySelector("[data-media-rotate]")?.value || "0";
    const crop = container.querySelector("[data-media-crop]")?.value || "original";
    const caption = escapeCaption(container.querySelector("[data-media-caption]")?.value || "");
    return `[[anvaya-${kind}:${id}|width=${width}|rotate=${rotate}|crop=${crop}|caption=${caption}]]\n`;
  };

  document.querySelectorAll("[data-insert-existing]").forEach((button) => {
    button.addEventListener("click", () => {
      const item = button.closest(".anvaya-media-item");
      replaceSelection("\n" + mediaDirective("image", button.dataset.insertExisting, item) + "\n");
    });
  });

  const removeImageDirectives = (assetId) => {
    if (!textarea) return;
    const pattern = new RegExp(
      "\\n?\\[\\[anvaya-image:" + String(assetId) +
      "(?:\\|[^\\]\\r\\n]*)?\\]\\]\\n?",
      "g"
    );
    textarea.value = textarea.value
      .replace(pattern, "\n")
      .replace(/\n{3,}/g, "\n\n");
  };

  document.querySelectorAll("[data-remove-existing]").forEach((button) => {
    button.addEventListener("click", () => {
      const assetId = button.dataset.removeExisting || "";
      if (!assetId) return;

      const item = button.closest(".anvaya-media-item");
      const hiddenHost = document.getElementById("anvaya-remove-asset-inputs");
      if (hiddenHost && !hiddenHost.querySelector('[data-remove-id="' + assetId + '"]')) {
        const input = document.createElement("input");
        input.type = "hidden";
        input.name = "remove_asset_ids";
        input.value = assetId;
        input.dataset.removeId = assetId;
        hiddenHost.appendChild(input);
      }

      removeImageDirectives(assetId);
      item?.classList.add("is-pending-delete");
      item?.querySelectorAll("button, select, input").forEach((control) => {
        if (control !== button) control.disabled = true;
      });
      button.disabled = true;
      button.textContent = "Will delete on save";
    });
  });

  let previewUrls = [];
  const revokePreviews = () => {
    previewUrls.forEach((url) => URL.revokeObjectURL(url));
    previewUrls = [];
  };

  const controlMarkup = (caption) =>
    '<div class="anvaya-media-controls">' +
      '<label>Size<select data-media-width>' +
        '<option value="25">25%</option>' +
        '<option value="40">40%</option>' +
        '<option value="55">55%</option>' +
        '<option value="70" selected>70%</option>' +
        '<option value="85">85%</option>' +
        '<option value="100">100%</option>' +
      '</select></label>' +
      '<label>Rotate<select data-media-rotate>' +
        '<option value="0">0°</option>' +
        '<option value="90">90°</option>' +
        '<option value="180">180°</option>' +
        '<option value="270">270°</option>' +
      '</select></label>' +
      '<label>Crop<select data-media-crop>' +
        '<option value="original">Original</option>' +
        '<option value="1:1">Square 1:1</option>' +
        '<option value="4:3">4:3</option>' +
        '<option value="3:4">3:4</option>' +
        '<option value="16:9">16:9</option>' +
      '</select></label>' +
      '<label class="anvaya-media-caption">Caption' +
        '<input data-media-caption maxlength="160" value="' + escapeHtml(caption) + '">' +
      '</label>' +
    '</div>';

  const removeUploadDirectives = (removedIndex) => {
    if (!textarea) return;
    const pattern = new RegExp(
      "\\n?\\[\\[anvaya-upload:" + removedIndex +
      "(?:\\|[^\\]\\r\\n]*)?\\]\\]\\n?",
      "g"
    );
    textarea.value = textarea.value
      .replace(pattern, "\n")
      .replace(/\n{3,}/g, "\n\n");
  };

  const renumberUploadDirectives = (removedIndex) => {
    if (!textarea) return;
    textarea.value = textarea.value.replace(
      /\[\[anvaya-upload:(\d+)(\|[^\]\r\n]*)?\]\]/g,
      (match, rawIndex, options = "") => {
        const index = Number(rawIndex);
        if (index <= removedIndex) return match;
        return "[[anvaya-upload:" + (index - 1) + (options || "") + "]]";
      }
    );
  };

  const removeNewUpload = (removedIndex) => {
    if (!fileInput) return;
    const files = Array.from(fileInput.files || []);
    if (removedIndex < 0 || removedIndex >= files.length) return;

    removeUploadDirectives(removedIndex);
    renumberUploadDirectives(removedIndex);

    if (typeof DataTransfer === "undefined") {
      fileInput.value = "";
      if (textarea) {
        textarea.value = textarea.value.replace(
          /\n?\[\[anvaya-upload:\d+(?:\|[^\]\r\n]*)?\]\]\n?/g,
          "\n"
        );
      }
      renderSelectedFiles();
      return;
    }

    const transfer = new DataTransfer();
    files.forEach((file, index) => {
      if (index !== removedIndex) transfer.items.add(file);
    });
    fileInput.files = transfer.files;
    renderSelectedFiles();
  };

  const renderSelectedFiles = () => {
    if (!selectedTray || !fileInput) return;
    revokePreviews();
    selectedTray.innerHTML = "";

    Array.from(fileInput.files || []).forEach((file, index) => {
      const name = file.name || ("Upload " + (index + 1));
      const lower = name.toLowerCase();
      const isImage = file.type.startsWith("image/") || /\.(png|jpe?g)$/.test(lower);
      const isZip = lower.endsWith(".zip");
      const isPdf = lower.endsWith(".pdf");

      const item = document.createElement("article");
      item.className = "anvaya-media-item";
      item.dataset.newUploadIndex = String(index);

      const thumb = document.createElement("div");
      thumb.className = "anvaya-media-thumb";

      if (isImage) {
        const url = URL.createObjectURL(file);
        previewUrls.push(url);
        const img = document.createElement("img");
        img.src = url;
        img.alt = "";
        thumb.appendChild(img);
      } else {
        const badge = document.createElement("span");
        badge.className = "anvaya-media-file-badge";
        badge.textContent = isZip ? "ZIP" : (isPdf ? "PDF" : "FILE");
        thumb.appendChild(badge);
      }

      const main = document.createElement("div");
      main.className = "anvaya-media-item-main";

      const title = document.createElement("strong");
      title.textContent = name;
      main.appendChild(title);

      if (isImage || isZip) {
        const controls = document.createElement("div");
        controls.innerHTML = controlMarkup(name.replace(/\.[^.]+$/, ""));
        while (controls.firstChild) main.appendChild(controls.firstChild);

        const insertButton = document.createElement("button");
        insertButton.type = "button";
        insertButton.className = "button secondary-button anvaya-media-insert";
        insertButton.textContent = isZip ? "Insert ZIP images here" : "Insert at cursor";
        insertButton.addEventListener("click", () => {
          replaceSelection(
            "\n" + mediaDirective("upload", String(index), item) + "\n"
          );
        });
        main.appendChild(insertButton);
      } else {
        const note = document.createElement("small");
        note.textContent = "PDF will remain available as an attachment.";
        main.appendChild(note);
      }

      const removeButton = document.createElement("button");
      removeButton.type = "button";
      removeButton.className = "button secondary-button anvaya-media-delete";
      removeButton.textContent = "Remove selected file";
      removeButton.setAttribute("data-remove-new-upload", String(index));
      removeButton.addEventListener("click", () => removeNewUpload(index));
      main.appendChild(removeButton);

      item.appendChild(thumb);
      item.appendChild(main);
      selectedTray.appendChild(item);
    });
  };

  if (fileInput && selectedTray) {
    fileInput.addEventListener("change", renderSelectedFiles);
  }

  window.addEventListener("beforeunload", revokePreviews);
})();
