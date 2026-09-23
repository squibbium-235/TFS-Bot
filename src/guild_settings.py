let welcomeFieldCount = 0;

const localPreviewUrls = new Map();


function escapeHtml(value) {
    return String(value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
}


function getValue(id) {
    const element = document.getElementById(id);

    if (!element) {
        return "";
    }

    return String(element.value || "").trim();
}


function normaliseHexColour(value) {
    const cleaned = String(value || "")
        .trim()
        .replace(/^#/, "")
        .replace(/^0x/i, "");

    if (/^[0-9a-fA-F]{6}$/.test(cleaned)) {
        return "#" + cleaned.toUpperCase();
    }

    return null;
}


function addWelcomeField(
    name = "",
    value = "",
    inline = false
) {
    welcomeFieldCount += 1;

    const fieldId = welcomeFieldCount;
    const wrapper = document.createElement("div");

    wrapper.className = "field-card compact-field-card";
    wrapper.dataset.fieldCard = "true";

    wrapper.innerHTML = `
        <div class="field-card-header">
            <strong>Field ${fieldId}</strong>
            <button
                type="button"
                class="danger-button small-button"
                onclick="removeWelcomeField(this)"
            >Remove</button>
        </div>

        <input
            type="hidden"
            name="field_id[]"
            value="${fieldId}"
        >

        <div class="setting-grid compact-setting-grid">
            <div>
                <label>Name</label>
                <input
                    name="field_${fieldId}_name"
                    class="field-name"
                    maxlength="256"
                    value="${escapeHtml(name)}"
                >
            </div>

            <div>
                <label class="checkbox-row compact-checkbox">
                    <input
                        type="checkbox"
                        name="field_${fieldId}_inline"
                        class="field-inline"
                        ${inline ? "checked" : ""}
                    >
                    Inline
                </label>
            </div>
        </div>

        <label>Value</label>
        <textarea
            name="field_${fieldId}_value"
            class="field-value"
            maxlength="1024"
            rows="3"
        >${escapeHtml(value)}</textarea>
    `;

    const container = document.getElementById("fields");

    if (!container) {
        return;
    }

    container.appendChild(wrapper);

    wrapper
        .querySelectorAll("input, textarea")
        .forEach((element) => {
            element.addEventListener(
                "input",
                updateWelcomePreview
            );

            element.addEventListener(
                "change",
                updateWelcomePreview
            );
        });

    updateWelcomePreview();
}


function removeWelcomeField(button) {
    const card = button.closest(
        "[data-field-card='true']"
    );

    if (card) {
        card.remove();
    }

    updateWelcomePreview();
}


function selectedUploadPreview(selectId) {
    const select = document.getElementById(selectId);

    if (!select || select.selectedIndex < 0) {
        return "";
    }

    const option = select.options[select.selectedIndex];
    return option?.dataset?.preview || "";
}


function localFilePreview(fileInputId) {
    const input = document.getElementById(fileInputId);

    if (!input || !input.files || input.files.length === 0) {
        const existing = localPreviewUrls.get(fileInputId);

        if (existing) {
            URL.revokeObjectURL(existing);
            localPreviewUrls.delete(fileInputId);
        }

        return "";
    }

    const oldUrl = localPreviewUrls.get(fileInputId);

    if (oldUrl) {
        URL.revokeObjectURL(oldUrl);
    }

    const newUrl = URL.createObjectURL(input.files[0]);
    localPreviewUrls.set(fileInputId, newUrl);

    return newUrl;
}


function resolveAssetPreview(
    fileInputId,
    urlInputId,
    uploadSelectId
) {
    const fileUrl = localFilePreview(fileInputId);

    if (fileUrl) {
        return fileUrl;
    }

    const externalUrl = getValue(urlInputId);

    if (externalUrl) {
        return externalUrl;
    }

    return selectedUploadPreview(uploadSelectId);
}


function setPreviewImage(id, url) {
    const image = document.getElementById(id);
    const error = document.getElementById(id + "-error");

    if (!image) {
        return;
    }

    image.onload = null;
    image.onerror = null;
    image.style.display = "none";
    image.removeAttribute("src");

    if (error) {
        error.style.display = "none";
    }

    if (!url || url.includes("{")) {
        return;
    }

    image.onload = function () {
        image.style.display = "block";
    };

    image.onerror = function () {
        image.style.display = "none";

        if (error) {
            error.style.display = "block";
        }
    };

    image.src = url;
}


function updateWelcomePreview() {
    const title = getValue("title") || "Welcome {user}!";
    const description = (
        getValue("description") || "Welcome to {server}!"
    );

    const colour = (
        normaliseHexColour(getValue("colour"))
        || "#5865F2"
    );

    const thumbnailUrl = resolveAssetPreview(
        "thumbnail_upload",
        "thumbnail_url",
        "thumbnail_upload_reference"
    );

    const imageUrl = resolveAssetPreview(
        "image_upload",
        "image_url",
        "image_upload_reference"
    );

    const authorName = getValue("author_name");

    const authorIconUrl = resolveAssetPreview(
        "author_icon_upload",
        "author_icon_url",
        "author_icon_upload_reference"
    );

    const footer = getValue("footer");

    const titleElement = document.getElementById("preview-title");
    const descriptionElement = document.getElementById(
        "preview-description"
    );
    const footerElement = document.getElementById("preview-footer");
    const embedElement = document.getElementById("preview-embed");

    if (titleElement) {
        titleElement.textContent = title;
    }

    if (descriptionElement) {
        descriptionElement.textContent = description;
    }

    if (footerElement) {
        footerElement.textContent = footer;
    }

    if (embedElement) {
        embedElement.style.borderLeftColor = colour;
    }

    setPreviewImage(
        "preview-thumbnail",
        thumbnailUrl
    );

    setPreviewImage(
        "preview-image",
        imageUrl
    );

    const authorWrap = document.getElementById(
        "preview-author-wrap"
    );
    const authorText = document.getElementById("preview-author");
    const authorIcon = document.getElementById(
        "preview-author-icon"
    );

    if (authorWrap && authorText && authorIcon) {
        if (authorName || authorIconUrl) {
            authorWrap.style.display = "flex";
            authorText.textContent = authorName || "Author";

            if (
                authorIconUrl
                && !authorIconUrl.includes("{")
            ) {
                authorIcon.src = authorIconUrl;
                authorIcon.style.display = "inline-block";
            } else {
                authorIcon.style.display = "none";
                authorIcon.removeAttribute("src");
            }
        } else {
            authorWrap.style.display = "none";
            authorIcon.style.display = "none";
            authorIcon.removeAttribute("src");
        }
    }

    const previewFields = document.getElementById(
        "preview-fields"
    );

    if (!previewFields) {
        return;
    }

    previewFields.innerHTML = "";

    document
        .querySelectorAll("[data-field-card='true']")
        .forEach((card) => {
            const nameInput = card.querySelector(".field-name");
            const valueInput = card.querySelector(".field-value");
            const inlineInput = card.querySelector(".field-inline");

            const name = String(nameInput?.value || "").trim();
            const value = String(valueInput?.value || "").trim();
            const inline = Boolean(inlineInput?.checked);

            if (!name || !value) {
                return;
            }

            const field = document.createElement("div");

            field.className = (
                "embed-field"
                + (inline ? " inline" : "")
            );

            const fieldName = document.createElement("div");
            const fieldValue = document.createElement("div");

            fieldName.className = "embed-field-name";
            fieldValue.className = "embed-field-value";

            fieldName.textContent = name;
            fieldValue.textContent = value;

            field.appendChild(fieldName);
            field.appendChild(fieldValue);
            previewFields.appendChild(field);
        });
}


function bindAssetControls(
    fileInputId,
    urlInputId,
    uploadSelectId
) {
    const fileInput = document.getElementById(fileInputId);
    const urlInput = document.getElementById(urlInputId);
    const uploadSelect = document.getElementById(uploadSelectId);

    if (uploadSelect && urlInput) {
        uploadSelect.addEventListener(
            "change",
            () => {
                if (uploadSelect.value) {
                    urlInput.value = "";

                    if (fileInput) {
                        fileInput.value = "";
                    }
                }

                updateWelcomePreview();
            }
        );
    }

    if (fileInput && urlInput) {
        fileInput.addEventListener(
            "change",
            () => {
                if (fileInput.files && fileInput.files.length > 0) {
                    urlInput.value = "";

                    if (uploadSelect) {
                        uploadSelect.value = "";
                    }
                }

                updateWelcomePreview();
            }
        );
    }

    if (urlInput) {
        urlInput.addEventListener(
            "input",
            () => {
                if (urlInput.value.trim()) {
                    if (uploadSelect) {
                        uploadSelect.value = "";
                    }

                    if (fileInput) {
                        fileInput.value = "";
                    }
                }

                updateWelcomePreview();
            }
        );
    }
}


const colourInput = document.getElementById("colour");
const colourPicker = document.getElementById("colour_picker");


if (colourInput && colourPicker) {
    colourInput.addEventListener(
        "input",
        function () {
            const normalised = normaliseHexColour(
                colourInput.value
            );

            if (normalised) {
                colourPicker.value = normalised;
            }

            updateWelcomePreview();
        }
    );

    colourPicker.addEventListener(
        "input",
        function () {
            colourInput.value = colourPicker.value.toUpperCase();
            updateWelcomePreview();
        }
    );
}


bindAssetControls(
    "thumbnail_upload",
    "thumbnail_url",
    "thumbnail_upload_reference"
);

bindAssetControls(
    "image_upload",
    "image_url",
    "image_upload_reference"
);

bindAssetControls(
    "author_icon_upload",
    "author_icon_url",
    "author_icon_upload_reference"
);


document
    .querySelectorAll(
        "#welcome-form input, "
        + "#welcome-form textarea, "
        + "#welcome-form select"
    )
    .forEach((element) => {
        element.addEventListener(
            "input",
            updateWelcomePreview
        );

        element.addEventListener(
            "change",
            updateWelcomePreview
        );
    });


let loadedFields = [];

const loadedFieldsElement = document.getElementById(
    "welcome-loaded-fields"
);


if (loadedFieldsElement) {
    try {
        const parsed = JSON.parse(
            loadedFieldsElement.textContent || "[]"
        );

        if (Array.isArray(parsed)) {
            loadedFields = parsed;
        }
    } catch (error) {
        console.error(
            "Could not load welcome fields.",
            error
        );
    }
}


if (loadedFields.length > 0) {
    loadedFields.forEach((field) => {
        addWelcomeField(
            String(field.name || ""),
            String(field.value || ""),
            Boolean(field.inline)
        );
    });
}


window.addEventListener(
    "beforeunload",
    () => {
        localPreviewUrls.forEach((url) => {
            URL.revokeObjectURL(url);
        });
    }
);


updateWelcomePreview();
