let fieldCount = 0;

function escapeHtml(value) {
    return value
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
}

function normaliseHexColour(value) {
    const cleaned = value.trim().replace("#", "");

    if (/^[0-9a-fA-F]{6}$/.test(cleaned)) {
        return "#" + cleaned.toUpperCase();
    }

    return null;
}

function openColourPicker() {
    document.getElementById("colour_picker").click();
}

function syncColourFromPicker() {
    const picker = document.getElementById("colour_picker");
    const input = document.getElementById("colour");

    input.value = picker.value.toUpperCase();
    updatePreview();
}

function syncColourFromText() {
    const picker = document.getElementById("colour_picker");
    const input = document.getElementById("colour");

    const normalised = normaliseHexColour(input.value);

    if (normalised !== null) {
        picker.value = normalised;
    }

    updatePreview();
}

function addField(name = "", value = "", inline = false) {
    fieldCount += 1;
    const fieldId = fieldCount;

    const wrapper = document.createElement("div");
    wrapper.className = "field-card";
    wrapper.dataset.fieldCard = "true";

    wrapper.innerHTML = `
        <div class="field-card-header">
            <strong>Field ${fieldId}</strong>
            <button type="button" class="danger" onclick="removeField(this)">Remove</button>
        </div>

        <input type="hidden" name="field_id[]" value="${fieldId}">

        <label>Name</label>
        <input name="field_${fieldId}_name" class="field-name" maxlength="256" value="${escapeHtml(name)}">

        <label>Value</label>
        <textarea name="field_${fieldId}_value" class="field-value" maxlength="1024" rows="3">${escapeHtml(value)}</textarea>

        <label class="checkbox-row">
            <input type="checkbox" name="field_${fieldId}_inline" class="field-inline" ${inline ? "checked" : ""}>
            Inline
        </label>
    `;

    document.getElementById("fields").appendChild(wrapper);

    wrapper.querySelectorAll("input, textarea").forEach((element) => {
        element.addEventListener("input", updatePreview);
        element.addEventListener("change", updatePreview);
    });

    updatePreview();
}

function removeField(button) {
    button.closest("[data-field-card='true']").remove();
    updatePreview();
}

function getValue(id) {
    return document.getElementById(id).value.trim();
}

function getSelectedUploadPreviewUrl(selectId) {
    const select = document.getElementById(selectId);
    const option = select.options[select.selectedIndex];

    if (!option) {
        return "";
    }

    return option.dataset.url || "";
}

function getImagePreviewUrl(uploadSelectId, urlInputId) {
    const uploadedUrl = getSelectedUploadPreviewUrl(uploadSelectId);

    if (uploadedUrl) {
        return uploadedUrl;
    }

    return getValue(urlInputId);
}

function setImage(id, url) {
    const image = document.getElementById(id);
    const error = document.getElementById(id + "-error");

    image.onload = null;
    image.onerror = null;
    image.style.display = "none";
    image.removeAttribute("src");

    if (error) {
        error.style.display = "none";
    }

    if (!url) {
        return;
    }

    image.dataset.previewUrl = url;

    image.onload = function () {
        if (image.dataset.previewUrl !== url) {
            return;
        }

        image.style.display = "block";

        if (error) {
            error.style.display = "none";
        }
    };

    image.onerror = function () {
        if (image.dataset.previewUrl !== url) {
            return;
        }

        image.style.display = "none";

        if (error) {
            error.style.display = "block";
        }
    };

    image.src = url;
}

function clearEmbedForm() {
    document.getElementById("title").value = "";
    document.getElementById("description").value = "";
    document.getElementById("colour").value = "#5865F2";
    document.getElementById("colour_picker").value = "#5865F2";
    document.getElementById("image_upload_filename").value = "";
    document.getElementById("image_url").value = "";
    document.getElementById("thumbnail_upload_filename").value = "";
    document.getElementById("thumbnail_url").value = "";
    document.getElementById("author_name").value = "";
    document.getElementById("author_icon_url").value = "";
    document.getElementById("footer").value = "TFSBot";
    document.getElementById("author_icon_upload_filename").value = "";

    document.getElementById("fields").innerHTML = "";
    fieldCount = 0;
    addField();

    updatePreview();
}

function updatePreview() {
    const title = getValue("title") || "Embed title";
    const description = getValue("description") || "Embed description will appear here.";
    const colour = normaliseHexColour(getValue("colour")) || "#5865F2";
    const imageUrl = getImagePreviewUrl("image_upload_filename", "image_url");
    const thumbnailUrl = getImagePreviewUrl("thumbnail_upload_filename", "thumbnail_url");
    const authorName = getValue("author_name");
    const authorIconUrl = getImagePreviewUrl("author_icon_upload_filename", "author_icon_url");
    const footer = getValue("footer");

    document.getElementById("preview-title").textContent = title;
    document.getElementById("preview-description").textContent = description;
    document.getElementById("preview-footer").textContent = footer;

    document.getElementById("preview-embed").style.borderLeftColor = colour;

    setImage("preview-image", imageUrl);
    setImage("preview-thumbnail", thumbnailUrl);

    const authorWrap = document.getElementById("preview-author-wrap");
    const author = document.getElementById("preview-author");
    const authorIcon = document.getElementById("preview-author-icon");

    if (authorName || authorIconUrl) {
        authorWrap.style.display = "flex";
        author.textContent = authorName || "Author";

        if (authorIconUrl) {
            authorIcon.src = authorIconUrl;
            authorIcon.style.display = "inline-block";
        } else {
            authorIcon.style.display = "none";
            authorIcon.removeAttribute("src");
        }
    } else {
        authorWrap.style.display = "none";
        author.textContent = "";
        authorIcon.style.display = "none";
        authorIcon.removeAttribute("src");
    }

    const previewFields = document.getElementById("preview-fields");
    previewFields.innerHTML = "";

    document.querySelectorAll("[data-field-card='true']").forEach((card) => {
        const fieldName = card.querySelector(".field-name").value.trim();
        const fieldValue = card.querySelector(".field-value").value.trim();
        const inline = card.querySelector(".field-inline").checked;

        if (!fieldName || !fieldValue) {
            return;
        }

        const field = document.createElement("div");
        field.className = "embed-field" + (inline ? " inline" : "");

        field.innerHTML = `
            <div class="embed-field-name"></div>
            <div class="embed-field-value"></div>
        `;

        field.querySelector(".embed-field-name").textContent = fieldName;
        field.querySelector(".embed-field-value").textContent = fieldValue;

        previewFields.appendChild(field);
    });
}

document.querySelectorAll("#embed-form input, #embed-form textarea, #embed-form select").forEach((element) => {
    element.addEventListener("input", updatePreview);
    element.addEventListener("change", updatePreview);
});

document.getElementById("colour_picker").addEventListener("input", syncColourFromPicker);
document.getElementById("colour").addEventListener("input", syncColourFromText);
document.getElementById("colour").addEventListener("click", openColourPicker);

addField();
updatePreview();