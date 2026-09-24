// Adds the session CSRF token to POST forms that do not already have one.
// The token is read from the csrf-token meta tag. GET forms are left
// alone. This does not set X-CSRF-Token; the server accepts that header
// as well, but these pages send the form field _csrf_token.

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