document.addEventListener("DOMContentLoaded", () => {
    let lastFocusedPlaceholderTarget = null;

    document.querySelectorAll(".cc-placeholder-target").forEach((element) => {
        element.addEventListener("focus", () => {
            lastFocusedPlaceholderTarget = element;
        });
    });

    document.querySelectorAll(".cc-placeholder").forEach((button) => {
        button.addEventListener("click", async () => {
            const placeholder = button.dataset.placeholder || "";

            if (lastFocusedPlaceholderTarget) {
                const element = lastFocusedPlaceholderTarget;

                const start = element.selectionStart ?? element.value.length;
                const end = element.selectionEnd ?? start;

                element.value =
                    element.value.slice(0, start) +
                    placeholder +
                    element.value.slice(end);

                element.focus();

                element.selectionStart =
                    element.selectionEnd =
                    start + placeholder.length;

                element.dispatchEvent(
                    new Event("input", {
                        bubbles: true,
                    })
                );

                return;
            }

            try {
                await navigator.clipboard.writeText(placeholder);

                const original = button.textContent;

                button.textContent = "Copied";

                setTimeout(() => {
                    button.textContent = original;
                }, 800);
            } catch {
                // Clipboard access can be unavailable over plain HTTP.
            }
        });
    });


    document.querySelectorAll(".cc-action").forEach((actionForm) => {
        if (actionForm.dataset.actionType !== "send_embed") {
            return;
        }

        const fieldsContainer =
            actionForm.querySelector(".cc-fields");

        const addFieldButton =
            actionForm.querySelector(".cc-add-field");

        let nextFieldSlot = 0;

        fieldsContainer
            ?.querySelectorAll('input[name="field_slot[]"]')
            .forEach((input) => {
                const value = Number.parseInt(input.value, 10);

                if (!Number.isNaN(value)) {
                    nextFieldSlot = Math.max(
                        nextFieldSlot,
                        value + 1
                    );
                }
            });


        const bindRemoveButtons = () => {
            actionForm
                .querySelectorAll(".cc-remove-field")
                .forEach((button) => {
                    if (button.dataset.bound === "1") {
                        return;
                    }

                    button.dataset.bound = "1";

                    button.addEventListener("click", () => {
                        button.closest(".cc-field")?.remove();

                        updatePreview();
                    });
                });
        };


        addFieldButton?.addEventListener("click", () => {
            if (!fieldsContainer) {
                return;
            }

            const existingFields =
                fieldsContainer.querySelectorAll(".cc-field");

            if (existingFields.length >= 25) {
                alert("Discord embeds can have at most 25 fields.");

                return;
            }

            const slot = nextFieldSlot++;

            const field = document.createElement("div");

            field.className = "cc-field";

            field.innerHTML = `
                <input
                    type="hidden"
                    name="field_slot[]"
                    value="${slot}"
                >

                <div class="cc-field-header">
                    <strong>New Field</strong>

                    <button
                        type="button"
                        class="danger-button cc-remove-field"
                    >
                        Remove
                    </button>
                </div>

                <div class="cc-field-grid">

                    <div>
                        <label>Name</label>

                        <input
                            name="field_name_${slot}"
                        >
                    </div>

                    <div>
                        <label>Value</label>

                        <textarea
                            name="field_value_${slot}"
                            rows="2"
                        ></textarea>
                    </div>

                </div>

                <label class="cc-check">
                    <input
                        type="checkbox"
                        name="field_inline_${slot}"
                    >

                    Inline
                </label>
            `;

            fieldsContainer.appendChild(field);

            bindRemoveButtons();
            bindPreviewInputs();
            updatePreview();
        });


        const preview =
            actionForm.querySelector(".cc-preview-embed");

        const previewTitle =
            actionForm.querySelector(".cc-preview-title");

        const previewDescription =
            actionForm.querySelector(".cc-preview-description");

        const previewFields =
            actionForm.querySelector(".cc-preview-fields");


        const updatePreview = () => {
            if (!preview) {
                return;
            }

            const title =
                actionForm.querySelector(".cc-embed-title")?.value || "";

            const description =
                actionForm.querySelector(".cc-embed-description")?.value || "";

            const colour =
                actionForm.querySelector(".cc-embed-colour")?.value || "5865F2";


            preview.style.borderLeftColor =
                /^([0-9a-f]{6})$/i.test(colour)
                    ? `#${colour}`
                    : "#5865F2";


            if (previewTitle) {
                previewTitle.textContent = title;

                previewTitle.style.display =
                    title ? "" : "none";
            }


            if (previewDescription) {
                previewDescription.textContent = description;

                previewDescription.style.display =
                    description ? "" : "none";
            }


            if (previewFields) {
                previewFields.innerHTML = "";

                actionForm
                    .querySelectorAll(".cc-field")
                    .forEach((fieldElement) => {
                        const fieldName =
                            fieldElement.querySelector(
                                'input[name^="field_name_"]'
                            )?.value || "";

                        const fieldValue =
                            fieldElement.querySelector(
                                'textarea[name^="field_value_"]'
                            )?.value || "";

                        if (!fieldName && !fieldValue) {
                            return;
                        }

                        const fieldPreview =
                            document.createElement("div");

                        fieldPreview.className =
                            "cc-preview-field";

                        const strong =
                            document.createElement("strong");

                        strong.textContent = fieldName;

                        const valueElement =
                            document.createElement("div");

                        valueElement.textContent = fieldValue;

                        fieldPreview.appendChild(strong);
                        fieldPreview.appendChild(valueElement);

                        previewFields.appendChild(fieldPreview);
                    });
            }
        };


        const bindPreviewInputs = () => {
            actionForm
                .querySelectorAll(
                    ".cc-embed-title, " +
                    ".cc-embed-description, " +
                    ".cc-embed-colour, " +
                    '.cc-field input, ' +
                    '.cc-field textarea'
                )
                .forEach((element) => {
                    if (element.dataset.previewBound === "1") {
                        return;
                    }

                    element.dataset.previewBound = "1";

                    element.addEventListener(
                        "input",
                        updatePreview
                    );

                    element.addEventListener(
                        "change",
                        updatePreview
                    );
                });
        };


        bindRemoveButtons();
        bindPreviewInputs();
        updatePreview();
    });
});