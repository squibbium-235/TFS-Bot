"""
Shared names for the built-in verification form.

FORM_KEY_VERIFICATION is the key used when a guild
has not chosen another form. The key and question
patterns are the same limits the form store enforces.
GENERIC_FORM_BUTTON_CUSTOM_ID is the button that
starts a published form which is not verification.
"""

FORM_KEY_VERIFICATION = "verification"
VERIFICATION_FORM_PATH = "data/forms/verification.json"

VALID_FORM_KEY_PATTERN_TEXT = r"^[a-z0-9_]{1,40}$"
VALID_QUESTION_KEY_PATTERN_TEXT = r"^[a-z0-9_]{1,80}$"

GENERIC_FORM_BUTTON_CUSTOM_ID = "form:start"