document.addEventListener(
    "DOMContentLoaded",
    () => {
        const csrfMeta =
            document.querySelector(
                'meta[name="csrf-token"]'
            );

        const token =
            csrfMeta?.content ?? "";

        document
            .querySelectorAll("form")
            .forEach((form) => {
                const method = (
                    form.getAttribute(
                        "method"
                    )
                    || "get"
                ).toLowerCase();

                if (method !== "post") {
                    return;
                }

                if (
                    form.querySelector(
                        'input[name="_csrf_token"]'
                    )
                ) {
                    return;
                }

                const input =
                    document.createElement(
                        "input"
                    );

                input.type = "hidden";
                input.name = "_csrf_token";
                input.value = token;

                form.prepend(
                    input
                );
            });
    }
);