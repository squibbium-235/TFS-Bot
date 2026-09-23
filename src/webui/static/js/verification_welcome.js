let welcomeFieldCount = 0;


function escapeHtml(value) {
    return String(value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
}


function getValue(id) {
    const element =
        document.getElementById(id);

    if (!element) {
        return "";
    }

    return element.value.trim();
}


function normaliseHexColour(value) {
    const cleaned =
        value
            .trim()
            .replace("#", "");

    if (
        /^[0-9a-fA-F]{6}$/
            .test(cleaned)
    ) {
        return (
            "#"
            + cleaned.toUpperCase()
        );
    }

    return null;
}


function addWelcomeField(
    name = "",
    value = "",
    inline = false
) {
    welcomeFieldCount += 1;

    const fieldId =
        welcomeFieldCount;

    const wrapper =
        document.createElement(
            "div"
        );

    wrapper.className =
        "field-card";

    wrapper.dataset.fieldCard =
        "true";

    wrapper.innerHTML = `
        <div class="field-card-header">
            <strong>Field ${fieldId}</strong>

            <button
                type="button"
                class="danger"
                onclick="removeWelcomeField(this)"
            >
                Remove
            </button>
        </div>

        <input
            type="hidden"
            name="field_id[]"
            value="${fieldId}"
        >

        <label>Name</label>

        <input
            name="field_${fieldId}_name"
            class="field-name"
            maxlength="256"
            value="${escapeHtml(name)}"
        >

        <label>Value</label>

        <textarea
            name="field_${fieldId}_value"
            class="field-value"
            maxlength="1024"
            rows="3"
        >${escapeHtml(value)}</textarea>

        <label class="checkbox-row">

            <input
                type="checkbox"
                name="field_${fieldId}_inline"
                class="field-inline"
                ${inline ? "checked" : ""}
            >

            Inline

        </label>
    `;

    document
        .getElementById(
            "fields"
        )
        .appendChild(
            wrapper
        );

    wrapper
        .querySelectorAll(
            "input, textarea"
        )
        .forEach(
            (element) => {
                element.addEventListener(
                    "input",
                    updateWelcomePreview
                );

                element.addEventListener(
                    "change",
                    updateWelcomePreview
                );
            }
        );

    updateWelcomePreview();
}


function removeWelcomeField(
    button
) {
    button
        .closest(
            "[data-field-card='true']"
        )
        .remove();

    updateWelcomePreview();
}


function setPreviewImage(
    id,
    url
) {
    const image =
        document.getElementById(
            id
        );

    const error =
        document.getElementById(
            id + "-error"
        );

    image.onload = null;
    image.onerror = null;

    image.style.display =
        "none";

    image.removeAttribute(
        "src"
    );

    if (error) {
        error.style.display =
            "none";
    }

    if (
        !url
        || url.includes("{")
    ) {
        return;
    }

    image.onload =
        function () {
            image.style.display =
                "block";
        };

    image.onerror =
        function () {
            if (error) {
                error.style.display =
                    "block";
            }
        };

    image.src = url;
}


function updateWelcomePreview() {
    const title =
        getValue("title")
        || "Welcome {user}!";

    const description =
        getValue("description")
        || "Welcome to {server}!";

    const colour =
        normaliseHexColour(
            getValue("colour")
        )
        || "#5865F2";

    const thumbnailUrl =
        getValue(
            "thumbnail_url"
        );

    const imageUrl =
        getValue(
            "image_url"
        );

    const authorName =
        getValue(
            "author_name"
        );

    const authorIconUrl =
        getValue(
            "author_icon_url"
        );

    const footer =
        getValue(
            "footer"
        );


    document.getElementById(
        "preview-title"
    ).textContent =
        title;


    document.getElementById(
        "preview-description"
    ).textContent =
        description;


    document.getElementById(
        "preview-footer"
    ).textContent =
        footer;


    document.getElementById(
        "preview-embed"
    ).style.borderLeftColor =
        colour;


    setPreviewImage(
        "preview-thumbnail",
        thumbnailUrl
    );

    setPreviewImage(
        "preview-image",
        imageUrl
    );


    const authorWrap =
        document.getElementById(
            "preview-author-wrap"
        );

    const authorText =
        document.getElementById(
            "preview-author"
        );

    const authorIcon =
        document.getElementById(
            "preview-author-icon"
        );


    if (
        authorName
        || authorIconUrl
    ) {
        authorWrap.style.display =
            "flex";

        authorText.textContent =
            authorName || "Author";

        if (
            authorIconUrl
            && !authorIconUrl.includes(
                "{"
            )
        ) {
            authorIcon.src =
                authorIconUrl;

            authorIcon.style.display =
                "inline-block";
        } else {
            authorIcon.style.display =
                "none";

            authorIcon.removeAttribute(
                "src"
            );
        }

    } else {
        authorWrap.style.display =
            "none";
    }


    const previewFields =
        document.getElementById(
            "preview-fields"
        );

    previewFields.innerHTML =
        "";


    document
        .querySelectorAll(
            "[data-field-card='true']"
        )
        .forEach(
            (card) => {
                const name =
                    card
                        .querySelector(
                            ".field-name"
                        )
                        .value
                        .trim();

                const value =
                    card
                        .querySelector(
                            ".field-value"
                        )
                        .value
                        .trim();

                const inline =
                    card
                        .querySelector(
                            ".field-inline"
                        )
                        .checked;

                if (
                    !name
                    || !value
                ) {
                    return;
                }

                const field =
                    document.createElement(
                        "div"
                    );

                field.className =
                    "embed-field"
                    + (
                        inline
                            ? " inline"
                            : ""
                    );

                field.innerHTML = `
                    <div class="embed-field-name"></div>
                    <div class="embed-field-value"></div>
                `;

                field
                    .querySelector(
                        ".embed-field-name"
                    )
                    .textContent =
                        name;

                field
                    .querySelector(
                        ".embed-field-value"
                    )
                    .textContent =
                        value;

                previewFields.appendChild(
                    field
                );
            }
        );
}


const colourInput =
    document.getElementById(
        "colour"
    );

const colourPicker =
    document.getElementById(
        "colour_picker"
    );


colourInput.addEventListener(
    "input",
    function () {
        const normalised =
            normaliseHexColour(
                colourInput.value
            );

        if (normalised) {
            colourPicker.value =
                normalised;
        }

        updateWelcomePreview();
    }
);


colourPicker.addEventListener(
    "input",
    function () {
        colourInput.value =
            colourPicker
                .value
                .toUpperCase();

        updateWelcomePreview();
    }
);


document
    .querySelectorAll(
        "#welcome-form input, "
        + "#welcome-form textarea, "
        + "#welcome-form select"
    )
    .forEach(
        (element) => {
            element.addEventListener(
                "input",
                updateWelcomePreview
            );

            element.addEventListener(
                "change",
                updateWelcomePreview
            );
        }
    );


let loadedFields = [];

const loadedFieldsElement =
    document.getElementById(
        "welcome-loaded-fields"
    );


if (loadedFieldsElement) {
    try {
        const parsed =
            JSON.parse(
                loadedFieldsElement.textContent
                || "[]"
            );

        if (
            Array.isArray(
                parsed
            )
        ) {
            loadedFields =
                parsed;
        }

    } catch (error) {
        console.error(
            "Could not load welcome fields.",
            error
        );
    }
}


if (
    loadedFields.length
    > 0
) {
    loadedFields.forEach(
        (field) => {
            addWelcomeField(
                String(
                    field.name
                    || ""
                ),
                String(
                    field.value
                    || ""
                ),
                Boolean(
                    field.inline
                )
            );
        }
    );
}


updateWelcomePreview();