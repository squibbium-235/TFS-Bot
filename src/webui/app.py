from __future__ import annotations

import asyncio
import base64
import hmac
import json
import secrets
import sqlite3
import threading
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from collections.abc import Coroutine
from pathlib import Path
from typing import Any
from io import BytesIO

import discord
from flask import (
    Flask,
    redirect,
    render_template_string,
    request,
    send_from_directory,
    session,
    url_for,
    send_file,
)
from werkzeug.utils import secure_filename

from src.services.dm_template_store import (
    DEFAULT_DM_TEMPLATES,
    DM_TEMPLATE_LABELS,
    DM_TEMPLATE_ORDER,
)
from src.services.forms.constants import FORM_KEY_VERIFICATION, VERIFICATION_FORM_PATH
from src.services.backup_service import BackupError, BackupService
from src.commands.forms.form_runtime import GenericFormStartView
from src.commands.verification.verification import (
    VerifyView,
    cancel_all_pending_applications_for_guild,
    cancel_pending_application_by_user_id,
)
from src.services.permission_store import (
    LEVEL_ADMIN,
    LEVEL_OWNER,
    LEVEL_PUBLIC,
    LEVEL_STAFF,
    LEVEL_VALUES,
)
from src.utils.embed_builder import EmbedFactory


UPLOAD_DIR = Path("data/uploads/images")
ALLOWED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}


LOGIN_HTML = """
<!doctype html>
<html>
<head>
    <title>TFSBot Login</title>
    <style>
        body {
            margin: 0;
            font-family: Arial, sans-serif;
            background: #111318;
            color: #f2f3f5;
            display: grid;
            place-items: center;
            height: 100vh;
        }

        .card {
            background: #1e2129;
            padding: 28px;
            border-radius: 16px;
            width: 360px;
            box-shadow: 0 18px 50px rgba(0, 0, 0, 0.35);
        }

        input, button {
            width: 100%;
            box-sizing: border-box;
            padding: 12px;
            border-radius: 10px;
            border: 1px solid #3a3f4b;
            background: #151820;
            color: #f2f3f5;
            margin-top: 8px;
        }

        button {
            background: #5865f2;
            border: 0;
            cursor: pointer;
            font-weight: bold;
        }

        .discord-button {
            background: #5865f2;
        }

        .divider {
            display: flex;
            align-items: center;
            gap: 10px;
            color: #b5bac1;
            font-size: 13px;
            margin: 20px 0 12px;
        }

        .divider::before,
        .divider::after {
            content: "";
            flex: 1;
            height: 1px;
            background: #3a3f4b;
        }

        .error {
            color: #ff6b6b;
        }

        .hint {
            color: #b5bac1;
            font-size: 13px;
            line-height: 1.45;
        }
    </style>
</head>
<body>
    <div class="card">
        <h1>TFSBot Web UI</h1>

        {% if discord_login_enabled %}
            <form method="get" action="{{ url_for('discord_login_start') }}">
                <button type="submit" class="discord-button">Login with Discord</button>
            </form>

            <p class="hint">
                Access is granted only if your Discord account has an allowed server role.
            </p>
        {% endif %}

        {% if discord_login_enabled and password_login_enabled %}
            <div class="divider">or emergency login</div>
        {% endif %}

        {% if password_login_enabled %}
            <form method="post">
                <label>Username</label>
                <input type="text" name="username" autocomplete="username" {% if not discord_login_enabled %}autofocus{% endif %}>

                <label>Password</label>
                <input type="password" name="password" autocomplete="current-password">

                <button type="submit">Login</button>
            </form>
        {% endif %}

        {% if not discord_login_enabled and not password_login_enabled %}
            <p class="error">No WebUI login methods are configured.</p>
        {% endif %}

        {% if error %}
            <p class="error">{{ error }}</p>
        {% endif %}
    </div>
</body>
</html>
"""


EMBED_FORM_HTML = """
<!doctype html>
<html>
<head>
    <title>TFSBot Embed Builder</title>

    <style>
        :root {
            --bg: #111318;
            --panel: #1e2129;
            --panel-2: #252936;
            --text: #f2f3f5;
            --muted: #b5bac1;
            --border: #3a3f4b;
            --accent: #5865f2;
            --danger: #ed4245;
            --success: #57f287;
        }

        * {
            box-sizing: border-box;
        }

        body {
            margin: 0;
            font-family: Arial, sans-serif;
            background: var(--bg);
            color: var(--text);
        }

        header {
            padding: 20px 28px;
            border-bottom: 1px solid var(--border);
            background: #151820;
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 18px;
        }

        header h1 {
            margin: 0;
            font-size: 22px;
            flex: 0 0 auto;
        }

        header nav {
            display: flex;
            gap: 14px;
            align-items: center;
            justify-content: flex-end;
            flex-wrap: wrap;
        }

        header a {
            color: var(--muted);
            text-decoration: none;
        }

        main {
            max-width: 1320px;
            margin: 0 auto;
            padding: 24px;
        }

        .embed-builder-grid {
            display: grid;
            grid-template-columns: minmax(420px, 700px) minmax(360px, 1fr);
            gap: 24px;
            align-items: start;
        }

        .panel {
            background: var(--panel);
            border: 1px solid var(--border);
            border-radius: 18px;
            padding: 20px;
            box-shadow: 0 18px 50px rgba(0, 0, 0, 0.22);
            margin-bottom: 18px;
        }

        .page-intro {
            display: grid;
            gap: 10px;
        }

        .page-intro p {
            margin: 0;
        }

        .quick-actions {
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
            margin-top: 14px;
        }

        .button-link {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            border-radius: 10px;
            padding: 11px 14px;
            background: var(--panel-2);
            color: var(--text) !important;
            border: 1px solid var(--border);
            font-weight: bold;
            cursor: pointer;
            text-decoration: none;
            line-height: 1;
        }

        .button-link:hover {
            background: #303747;
        }

        .section-note {
            margin-top: 4px;
            margin-bottom: 14px;
        }

        .upload-details {
            background: var(--panel);
            border: 1px solid var(--border);
            border-radius: 18px;
            padding: 0;
            box-shadow: 0 18px 50px rgba(0, 0, 0, 0.22);
            margin-bottom: 18px;
            overflow: hidden;
        }

        .upload-details summary {
            cursor: pointer;
            padding: 18px 20px;
            font-weight: bold;
            color: var(--text);
            background: var(--panel);
        }

        .upload-details summary:hover {
            background: var(--panel-2);
        }

        .upload-details-inner {
            border-top: 1px solid var(--border);
            padding: 20px;
        }

        .form-section-title {
            margin-top: 22px;
            padding-top: 18px;
            border-top: 1px solid var(--border);
        }

        .form-section-title:first-of-type {
            margin-top: 0;
            padding-top: 0;
            border-top: 0;
        }

        .preview-heading {
            display: flex;
            justify-content: space-between;
            gap: 12px;
            align-items: flex-start;
        }

        .preview-heading p {
            margin: 4px 0 0;
        }

        .clear-button {
            background: var(--panel-2);
            color: var(--text);
            border: 1px solid var(--border);
        }

        .clear-button:hover {
            background: #303747;
        }

        h2 {
            margin-top: 0;
            font-size: 18px;
        }

        label {
            display: block;
            margin-top: 14px;
            margin-bottom: 6px;
            color: var(--muted);
            font-size: 14px;
        }

        input, textarea, select {
            width: 100%;
            border: 1px solid var(--border);
            border-radius: 10px;
            padding: 10px 12px;
            background: #151820;
            color: var(--text);
            font: inherit;
        }

        textarea {
            resize: vertical;
        }

        button {
            border: 0;
            border-radius: 10px;
            padding: 11px 14px;
            background: var(--accent);
            color: white;
            font-weight: bold;
            cursor: pointer;
        }

        button.secondary {
            background: var(--panel-2);
            color: var(--text);
            border: 1px solid var(--border);
        }

        button.danger {
            background: var(--danger);
        }

        .actions {
            display: flex;
            gap: 10px;
            margin-top: 16px;
            flex-wrap: wrap;
        }

        .field-card {
            background: var(--panel-2);
            border: 1px solid var(--border);
            border-radius: 14px;
            padding: 14px;
            margin-top: 12px;
        }

        .field-card-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        .field-card-header strong {
            color: var(--muted);
        }

        .checkbox-row {
            display: flex;
            align-items: center;
            gap: 8px;
            margin-top: 10px;
            color: var(--muted);
        }

        .checkbox-row input {
            width: auto;
        }

        .message {
            color: var(--success);
        }

        .error {
            color: #ff6b6b;
        }

        .hint {
            color: var(--muted);
            font-size: 13px;
        }

        .badge {
            border: 1px solid var(--border);
            background: #151820;
            color: var(--muted);
            border-radius: 999px;
            padding: 4px 8px;
            font-size: 12px;
            white-space: nowrap;
        }

        .colour-input-wrap {
            position: relative;
        }

        #colour {
            font-family: monospace;
            font-weight: bold;
            cursor: pointer;
        }

        #colour_picker {
            position: absolute;
            width: 1px;
            height: 1px;
            opacity: 0;
            pointer-events: none;
        }

        .preview-wrap {
            position: sticky;
            top: 24px;
        }

        .discord-preview {
            background: #313338;
            border-radius: 14px;
            padding: 16px;
            min-height: 300px;
        }

        .discord-message {
            display: flex;
            gap: 12px;
        }

        .avatar {
            width: 42px;
            height: 42px;
            border-radius: 50%;
            background: var(--accent);
            display: grid;
            place-items: center;
            font-weight: bold;
        }

        .message-body {
            flex: 1;
        }

        .bot-name {
            font-weight: bold;
            color: #f2f3f5;
        }

        .bot-tag {
            background: #5865f2;
            color: white;
            border-radius: 4px;
            padding: 1px 4px;
            font-size: 11px;
            margin-left: 6px;
        }

        .embed-preview {
            margin-top: 8px;
            background: #2b2d31;
            border-left: 4px solid #5865f2;
            border-radius: 4px;
            padding: 12px;
            width: 100%;
            max-width: 560px;
            overflow: hidden;
        }

        .embed-author {
            display: flex;
            align-items: center;
            gap: 6px;
            font-size: 13px;
            font-weight: bold;
            margin-bottom: 8px;
        }

        .embed-author img {
            width: 20px;
            height: 20px;
            border-radius: 50%;
            object-fit: cover;
        }

        .embed-title {
            color: #00a8fc;
            font-weight: bold;
            margin-bottom: 8px;
        }

        .embed-description {
            white-space: pre-wrap;
            color: #dbdee1;
            margin-bottom: 10px;
        }

        .embed-fields {
            display: block;
        }

        .embed-field {
            margin-bottom: 8px;
        }

        .embed-field.inline {
            display: inline-block;
            width: 30%;
            vertical-align: top;
            margin-right: 8px;
        }

        .embed-field-name {
            font-weight: bold;
            font-size: 13px;
        }

        .embed-field-value {
            white-space: pre-wrap;
            color: #dbdee1;
            font-size: 13px;
        }

        .embed-body-row {
            display: flex;
            align-items: flex-start;
            gap: 12px;
        }

        .embed-main-content {
            flex: 1;
            min-width: 0;
        }

        .embed-thumbnail-wrap {
            flex: 0 0 auto;
        }

        .embed-image,
        .embed-thumbnail {
            border-radius: 8px;
            background: #1e1f22;
            border: 1px solid rgba(255, 255, 255, 0.06);
        }

        .embed-image {
            display: block;
            width: 100%;
            max-height: 260px;
            object-fit: contain;
            margin-top: 10px;
        }

        .embed-thumbnail {
            display: block;
            width: 90px;
            height: 90px;
            object-fit: cover;
        }

        .embed-footer {
            margin-top: 10px;
            font-size: 12px;
            color: var(--muted);
        }

        .image-preview-error {
            display: none;
            color: #ff8587;
            font-size: 12px;
            margin-top: 6px;
        }

       @media (max-width: 980px) {
            .embed-builder-grid {
                grid-template-columns: 1fr;
            }

            .preview-wrap {
                position: static;
            }
        }
    </style>
</head>

<body>
    <header>
        <h1>TFSBot Embed Builder</h1>
        <nav>
            <a href="{{ url_for('index') }}" class="{{ 'active' if active_page == 'overview' else '' }}">Overview</a>
            {% if is_owner %}
                <a href="{{ url_for('embed_builder') }}" class="{{ 'active' if active_page == 'embed_builder' else '' }}">Embed Builder</a>
                <a href="{{ url_for('dm_templates') }}" class="{{ 'active' if active_page == 'dm_templates' else '' }}">DM Templates</a>
                <a href="{{ url_for('forms_page') }}" class="{{ 'active' if active_page == 'forms' else '' }}">Forms</a>
                <a href="{{ url_for('uploads_manager_page') }}" class="{{ 'active' if active_page == 'uploads' else '' }}">Uploads</a>
                <a href="{{ url_for('verification_page') }}" class="{{ 'active' if active_page == 'verification' else '' }}">Verification</a>
                <a href="{{ url_for('permissions_page') }}" class="{{ 'active' if active_page == 'permissions' else '' }}">Permissions</a>
                <a href="{{ url_for('backups_page') }}" class="{{ 'active' if active_page == 'backups' else '' }}">Backups</a>
            {% endif %}
            <span class="badge">{{ display_name }} · {{ webui_role|title }}</span>
            <a href="{{ url_for('logout') }}">Logout</a>
        </nav>
    </header>

    <main>
        <div class="panel page-intro">
            <h2>Embed Builder</h2>
            <p class="hint">
                Build and send Discord embeds from the WebUI. Upload images here if you want Discord-hosted attachments instead of external image links.
            </p>

            <div class="quick-actions">
                <a class="button-link" href="#embed-destination">Destination</a>
                <a class="button-link" href="#embed-content">Embed Content</a>
                <a class="button-link" href="#embed-images">Images</a>
                <a class="button-link" href="#embed-fields">Fields</a>
                <a class="button-link" href="#embed-preview">Preview</a>
            </div>
        </div>

        {% if message %}
            <p class="message">{{ message }}</p>
        {% endif %}

        {% if error %}
            <p class="error">{{ error }}</p>
        {% endif %}

        <details class="upload-details">
            <summary>Upload Image</summary>

            <div class="upload-details-inner">
                <form method="post" action="{{ url_for('upload_image') }}" enctype="multipart/form-data">
                    <label>Folder</label>
                    <select name="folder">
                        <option value="">Root</option>
                        {% for folder in upload_folders %}
                            <option value="{{ folder.path }}">{{ folder.label }}</option>
                        {% endfor %}
                    </select>

                    <label>Or new folder</label>
                    <input name="new_folder" placeholder="author-icons">

                    <label>Image file</label>
                    <input type="file" name="image" accept="image/png,image/jpeg,image/gif,image/webp" required>

                    <p class="hint">
                        Uploaded images can be selected below. When sent to Discord, they are attached to the message,
                        so they do not need Imgur or another image host, or you can, idc.
                    </p>

                    <button type="submit">Upload Image</button>
                </form>
            </div>
        </details>

        <div class="embed-builder-grid">
            <section>
                <div class="panel">
                    <form method="post" action="{{ url_for('send_embed') }}" id="embed-form">
                        <h2 id="embed-destination">Destination</h2>
                        <p class="hint section-note">
                            Choose where the embed should be sent. This sends immediately.
                        </p>

                    <label>Channel</label>
                    <select name="channel_id" required>
                        {% for channel in channels %}
                            <option value="{{ channel.id }}">{{ channel.label }}</option>
                        {% endfor %}
                    </select>

                    <h2 id="embed-content" class="form-section-title">Embed Content</h2>

                    <label>Title</label>
                    <input name="title" id="title" maxlength="256" required>

                    <label>Description</label>
                    <textarea name="description" id="description" maxlength="4000" rows="6"></textarea>

                    <label>Colour</label>
                    <div class="colour-input-wrap">
                        <input
                            type="text"
                            name="colour"
                            id="colour"
                            placeholder="#5865F2"
                            value="#5865F2"
                            autocomplete="off"
                        >

                        <input
                            type="color"
                            id="colour_picker"
                            value="#5865F2"
                            aria-label="Pick embed colour"
                        >
                    </div>

                    <h2 id="embed-images" class="form-section-title">Images</h2>

                    <label>Uploaded image</label>
                    <select name="image_upload_filename" id="image_upload_filename">
                        <option value="">No uploaded image</option>
                        {% for image in uploaded_images %}
                            <option value="{{ image.reference }}" data-url="{{ image.url }}">{{ image.label }}</option>
                        {% endfor %}
                    </select>

                    <label>Or external image URL</label>
                    <input name="image_url" id="image_url" placeholder="https://example.com/image.png">

                    <label>Uploaded thumbnail</label>
                    <select name="thumbnail_upload_filename" id="thumbnail_upload_filename">
                        <option value="">No uploaded thumbnail</option>
                        {% for image in uploaded_images %}
                            <option value="{{ image.reference }}" data-url="{{ image.url }}">{{ image.label }}</option>
                        {% endfor %}
                    </select>

                    <label>Or external thumbnail URL</label>
                    <input name="thumbnail_url" id="thumbnail_url" placeholder="https://example.com/thumb.png">

                    <label>Author name</label>
                    <input name="author_name" id="author_name" maxlength="256">

                    <label>Uploaded author icon</label>
                    <select name="author_icon_upload_filename" id="author_icon_upload_filename">
                        <option value="">No uploaded author icon</option>
                        {% for image in uploaded_images %}
                            <option value="{{ image.reference }}" data-url="{{ image.url }}">{{ image.label }}</option>
                        {% endfor %}
                    </select>

                    <label>Or external author icon URL</label>
                    <input name="author_icon_url" id="author_icon_url">

                    <label>Footer</label>
                    <input name="footer" id="footer" maxlength="2048" value="TFSBot">

                    <h2 id="embed-fields" class="form-section-title">Fields</h2>
                    <p class="hint section-note">
                        Add optional embed fields. Inline fields try to sit beside each other.
                    </p>

                    <div id="fields"></div>

                    <div class="actions">
                        <button type="button" class="secondary" onclick="addField()">Add Field</button>
                        <button type="button" class="clear-button" onclick="clearEmbedForm()">Clear Form</button>
                        <button type="submit">Send Embed to Channel</button>
                    </div>
                </form>
            </div>
        </section>

        <section class="preview-wrap" id="embed-preview">
            <div class="panel">
                <div class="preview-heading">
                    <div>
                        <h2>Live Preview</h2>
                        <p class="hint">
                            Approximate Discord preview :)
                        </p>
                    </div>
                </div>

                <div class="discord-preview">
                    <div class="discord-message">
                        <div class="avatar">T</div>

                        <div class="message-body">
                            <span class="bot-name">TFSBot</span>
                            <span class="bot-tag">BOT</span>

                            <div class="embed-preview" id="preview-embed">
                                <div class="embed-body-row">
                                    <div class="embed-main-content">
                                        <div class="embed-author" id="preview-author-wrap" style="display: none;">
                                            <img id="preview-author-icon" style="display: none;">
                                            <span id="preview-author"></span>
                                        </div>

                                        <div class="embed-title" id="preview-title">Embed title</div>
                                        <div class="embed-description" id="preview-description">Embed description will appear here.</div>

                                        <div class="embed-fields" id="preview-fields"></div>
                                    </div>

                                    <div class="embed-thumbnail-wrap">
                                        <img class="embed-thumbnail" id="preview-thumbnail" style="display: none;">
                                        <div class="image-preview-error" id="preview-thumbnail-error">Thumbnail could not be loaded in the browser preview.</div>
                                    </div>
                                </div>

                                <img class="embed-image" id="preview-image" style="display: none;">
                                <div class="image-preview-error" id="preview-image-error">Image could not be loaded in the browser preview.</div>

                                <div class="embed-footer" id="preview-footer">TFSBot</div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </section>

    </main>

    <script>
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
    </script>
</body>
</html>
"""


ADMIN_PAGE_HTML = """
<!doctype html>
<html>
<head>
    <title>TFSBot Admin</title>
    <style>
        :root {
            --bg: #0f1117;
            --header: #141822;
            --panel: #1b1f2a;
            --panel-2: #242936;
            --panel-3: #11151f;
            --text: #f2f3f5;
            --muted: #b5bac1;
            --muted-2: #8e95a3;
            --border: #363d4f;
            --border-soft: #2a3040;
            --accent: #5865f2;
            --accent-hover: #4752c4;
            --danger: #ed4245;
            --success: #57f287;
        }

        * { box-sizing: border-box; }

        body {
            margin: 0;
            font-family: Arial, sans-serif;
            background: var(--bg);
            color: var(--text);
        }

        header {
            padding: 18px 34px;
            border-bottom: 1px solid var(--border-soft);
            background: var(--header);
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 18px;
            position: sticky;
            top: 0;
            z-index: 10;
        }

        header h1 {
            margin: 0;
            font-size: 22px;
            letter-spacing: -0.02em;
            flex: 0 0 auto;
        }

        nav { display: flex; gap: 16px; align-items: center; justify-content: flex-end; flex-wrap: wrap; }
        nav a { color: var(--muted); text-decoration: none; font-size: 15px; }
        nav a:hover { color: var(--text); }
        nav a.active { color: var(--text); font-weight: 700; }

        main {
            max-width: 1120px;
            margin: 0 auto;
            padding: 28px 24px 60px;
        }

        h2 {
            margin: 0 0 10px;
            font-size: 24px;
            letter-spacing: -0.02em;
        }

        .panel {
            background: var(--panel);
            border: 1px solid var(--border);
            border-radius: 18px;
            padding: 22px;
            box-shadow: 0 18px 50px rgba(0, 0, 0, 0.22);
            margin-bottom: 18px;
        }

        label {
            display: block;
            margin-top: 16px;
            margin-bottom: 7px;
            color: var(--muted);
            font-size: 14px;
            font-weight: 700;
        }

        input, textarea, select {
            width: 100%;
            border: 1px solid var(--border);
            border-radius: 10px;
            padding: 11px 12px;
            background: var(--panel-3);
            color: var(--text);
            font: inherit;
            outline: none;
        }

        input:focus, textarea:focus, select:focus {
            border-color: var(--accent);
            box-shadow: 0 0 0 3px rgba(88, 101, 242, 0.18);
        }

        textarea { resize: vertical; min-height: 108px; line-height: 1.45; }

        button {
            border: 0;
            border-radius: 10px;
            padding: 11px 15px;
            background: var(--accent);
            color: white;
            font-weight: 800;
            cursor: pointer;
            font-size: 14px;
        }

        button:hover { background: var(--accent-hover); }

        .message {
            color: var(--success);
            background: rgba(87, 242, 135, 0.08);
            border: 1px solid rgba(87, 242, 135, 0.24);
            padding: 12px 14px;
            border-radius: 12px;
        }

        .error {
            color: #ff8587;
            background: rgba(237, 66, 69, 0.08);
            border: 1px solid rgba(237, 66, 69, 0.24);
            padding: 12px 14px;
            border-radius: 12px;
        }

        .warning-panel {
            border-color: rgba(255, 204, 102, 0.42);
            background: rgba(255, 204, 102, 0.04);
        }

        .warning-list {
            display: grid;
            gap: 8px;
            margin-top: 12px;
        }

        .warning-item {
            display: flex;
            justify-content: space-between;
            gap: 12px;
            align-items: center;
            background: var(--panel-2);
            border: 1px solid var(--border-soft);
            border-radius: 12px;
            padding: 10px 12px;
        }

        .warning-item strong {
            font-size: 14px;
        }

        .warning-item span {
            color: var(--muted);
            font-size: 13px;
            text-align: right;
        }

        .hint { color: var(--muted); font-size: 13px; line-height: 1.45; }

        .grid-2 {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 14px;
        }

        .template-card, .command-row {
            background: var(--panel-2);
            border: 1px solid var(--border);
            border-radius: 16px;
            padding: 18px;
            margin-top: 16px;
        }

        .template-card h3, .command-row h3 { margin: 0; font-size: 16px; }
        .template-card textarea { margin-top: 12px; }

        .card-header {
            display: flex;
            justify-content: space-between;
            gap: 16px;
            align-items: flex-start;
            margin-bottom: 8px;
        }

        .template-meta {
            margin: 6px 0 0;
            color: var(--muted-2);
            font-size: 13px;
        }

        .badge {
            border: 1px solid var(--border);
            background: var(--panel-3);
            color: var(--muted);
            border-radius: 999px;
            padding: 4px 8px;
            font-size: 12px;
            white-space: nowrap;
        }

        .badge.custom {
            color: var(--success);
            border-color: rgba(87, 242, 135, 0.28);
            background: rgba(87, 242, 135, 0.08);
        }

        .variable-list {
            display: flex;
            flex-wrap: wrap;
            gap: 6px;
            margin-top: 10px;
        }

        .default-details {
            margin-top: 10px;
            border-top: 1px solid var(--border-soft);
            padding-top: 10px;
        }

        .default-details summary { cursor: pointer; color: var(--muted); }

        .default-details pre {
            margin: 10px 0 0;
            white-space: pre-wrap;
            color: var(--muted);
            background: var(--panel-3);
            border: 1px solid var(--border-soft);
            border-radius: 10px;
            padding: 12px;
        }

        .action-panel {
            display: flex;
            justify-content: flex-start;
            align-items: center;
        }

        .command-row {
            display: grid;
            grid-template-columns: minmax(220px, 1fr) 220px;
            gap: 14px;
            align-items: center;
        }

        .setting-grid {
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 14px;
        }

        .wide-field { grid-column: 1 / -1; }

        .terms-box {
            min-height: 220px;
            font-family: Consolas, monospace;
            font-size: 13px;
        }

        .button-row {
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
            margin-top: 16px;
        }

        .secondary-button {
            background: var(--panel-2);
            border: 1px solid var(--border);
            color: var(--text);
        }

        .secondary-button:hover { background: #303747; }

        .danger-button { background: var(--danger); }
        .danger-button:hover { background: #c73538; }

        .danger-panel {
            border-color: rgba(237, 66, 69, 0.55);
        }

        .restore-warning {
            border-color: rgba(237, 66, 69, 0.65);
            background: rgba(237, 66, 69, 0.07);
        }

        .restore-warning strong {
            color: #ff8587;
        }

        .backup-steps {
            display: grid;
            gap: 10px;
            margin-top: 14px;
        }

        .backup-step {
            background: var(--panel-2);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 12px;
        }

        .backup-step strong {
            display: block;
            margin-bottom: 4px;
        }

        .stat-grid {
            display: grid;
            grid-template-columns: repeat(3, minmax(0, 1fr));
            gap: 12px;
            margin-top: 14px;
        }

        .stat-card {
            background: var(--panel-2);
            border: 1px solid var(--border);
            border-radius: 14px;
            padding: 14px;
        }

        .stat-card strong {
            display: block;
            margin-bottom: 4px;
        }

        code {
            background: var(--panel-3);
            border: 1px solid var(--border);
            border-radius: 6px;
            padding: 2px 5px;
            color: #d7dcff;
        }

        .overview-grid {
            display: grid;
            grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: 12px;
            margin-top: 14px;
        }

        .overview-card {
            background: var(--panel-2);
            border: 1px solid var(--border);
            border-radius: 14px;
            padding: 14px;
        }

        .overview-card strong {
            display: block;
            font-size: 24px;
            line-height: 1.1;
            margin-bottom: 6px;
        }

        .overview-card span {
            color: var(--muted);
            font-size: 13px;
        }

        .health-list {
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 10px;
            margin-top: 14px;
        }

        .health-item {
            background: var(--panel-2);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 12px;
        }

        .health-item small {
            display: block;
            color: var(--muted);
            margin-bottom: 5px;
            font-weight: 700;
        }

        .data-table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 14px;
            overflow: hidden;
            border-radius: 12px;
        }

        .data-table th,
        .data-table td {
            border-bottom: 1px solid var(--border-soft);
            padding: 10px 8px;
            text-align: left;
            vertical-align: top;
            font-size: 14px;
        }

        .data-table th {
            color: var(--muted);
            font-size: 12px;
            text-transform: uppercase;
            letter-spacing: 0.04em;
        }

        .data-table tr:last-child td {
            border-bottom: 0;
        }

        .pill {
            display: inline-block;
            border-radius: 999px;
            padding: 4px 8px;
            font-size: 12px;
            font-weight: 800;
            border: 1px solid var(--border);
            background: var(--panel-3);
            color: var(--muted);
        }

        .pill.good {
            color: var(--success);
            border-color: rgba(87, 242, 135, 0.28);
            background: rgba(87, 242, 135, 0.08);
        }

        .pill.warn {
            color: #ffcc66;
            border-color: rgba(255, 204, 102, 0.28);
            background: rgba(255, 204, 102, 0.08);
        }

        .pill.bad {
            color: #ff8587;
            border-color: rgba(237, 66, 69, 0.28);
            background: rgba(237, 66, 69, 0.08);
        }

        .muted-link {
            color: var(--muted);
        }

        .button-link {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            border-radius: 10px;
            padding: 11px 15px;
            background: var(--accent);
            color: white !important;
            font-weight: 800;
            cursor: pointer;
            font-size: 14px;
            text-decoration: none;
            line-height: 1;
        }

        .button-link:hover {
            background: var(--accent-hover);
            color: white !important;
        }

        .button-link.secondary {
            background: var(--panel-2);
            border: 1px solid var(--border);
            color: var(--text) !important;
        }

        .button-link.secondary:hover {
            background: #303747;
        }

        .page-intro {
            display: grid;
            gap: 10px;
        }

        .page-intro p {
            margin: 0;
        }

        .section-note {
            margin-top: 4px;
            margin-bottom: 14px;
        }

        .quick-actions {
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
            margin-top: 16px;
        }

        .inline-form {
            display: inline-flex;
        }

        .inline-form button {
            width: auto;
        }

        .question-card {
            background: var(--panel-2);
            border: 1px solid var(--border);
            border-radius: 16px;
            padding: 18px;
            margin-top: 14px;
        }

        .question-card-header {
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            gap: 12px;
            margin-bottom: 12px;
        }

        .question-card-header h3 {
            margin: 0;
            font-size: 17px;
        }

        .question-meta {
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            margin-top: 8px;
        }

        @media (max-width: 800px) {
            .grid-2, .setting-grid, .stat-grid, .command-row, .overview-grid, .health-list { grid-template-columns: 1fr; }
            header { align-items: flex-start; gap: 12px; flex-direction: column; padding: 18px 22px; }
            nav { flex-wrap: wrap; }
            main { padding: 20px 16px 50px; }
        }
    </style>
</head>
<body>
    <header>
        <h1>{{ title }}</h1>
        <nav>
            <a href="{{ url_for('index') }}" class="{{ 'active' if active_page == 'overview' else '' }}">Overview</a>
            {% if is_owner %}
                <a href="{{ url_for('embed_builder') }}" class="{{ 'active' if active_page == 'embed_builder' else '' }}">Embed Builder</a>
                <a href="{{ url_for('dm_templates') }}" class="{{ 'active' if active_page == 'dm_templates' else '' }}">DM Templates</a>
                <a href="{{ url_for('forms_page') }}" class="{{ 'active' if active_page == 'forms' else '' }}">Forms</a>
                <a href="{{ url_for('uploads_manager_page') }}" class="{{ 'active' if active_page == 'uploads' else '' }}">Uploads</a>
                <a href="{{ url_for('verification_page') }}" class="{{ 'active' if active_page == 'verification' else '' }}">Verification</a>
                <a href="{{ url_for('permissions_page') }}" class="{{ 'active' if active_page == 'permissions' else '' }}">Permissions</a>
                <a href="{{ url_for('backups_page') }}" class="{{ 'active' if active_page == 'backups' else '' }}">Backups</a>
            {% endif %}
            <span class="badge">{{ display_name }} · {{ webui_role|title }}</span>
            <a href="{{ url_for('logout') }}">Logout</a>
        </nav>
    </header>

    <main>
        {% if message %}<p class="message">{{ message }}</p>{% endif %}
        {% if error %}<p class="error">{{ error }}</p>{% endif %}

        {{ body|safe }}
    </main>
</body>
</html>
"""


OVERVIEW_BODY_HTML = """
<div class="panel">
    <h2>Overview</h2>
    <p class="hint">
        Quick state of the bot, verification queue, and setup. A dashboard if you will
    </p>

    <form method="get">
        <label>Server</label>
        <select name="guild_id" onchange="this.form.submit()">
            {% for guild in guilds %}
                <option value="{{ guild.id }}" {% if guild.id == selected_guild_id %}selected{% endif %}>{{ guild.name }}</option>
            {% endfor %}
        </select>
    </form>

    {% if overview %}
        <div class="overview-grid">
            <div class="overview-card">
                <strong>{{ overview.pending_count }}</strong>
                <span>Pending applications</span>
            </div>
            <div class="overview-card">
                <strong>{{ overview.questioning_count }}</strong>
                <span>Being questioned</span>
            </div>
            <div class="overview-card">
                <strong>{{ overview.today_total }}</strong>
                <span>Actioned today</span>
            </div>
            <div class="overview-card">
                <strong>{{ overview.total_count }}</strong>
                <span>Total applications</span>
            </div>
        </div>
    {% endif %}
</div>

{% if overview %}
{% if overview.warning_items %}
<div class="panel warning-panel">
    <h2>{{ overview.warning_count }} issue(s) need attention</h2>
    <p class="hint">
        These are the setup items most likely to stop verification or WebUI management from working properly.
    </p>

    <div class="warning-list">
        {% for item in overview.warning_items %}
            <div class="warning-item">
                <strong>{{ item.label }}</strong>
                <span>{{ item.value }}</span>
            </div>
        {% endfor %}
    </div>
</div>
{% endif %}

<div class="panel">
    <h2>Setup Health</h2>
    <div class="health-list">
        {% for item in overview.health_items %}
            <div class="health-item">
                <small>{{ item.label }}</small>
                <span class="pill {{ item.class }}">{{ item.value }}</span>
            </div>
        {% endfor %}
    </div>
</div>

<div class="panel">
    <h2>Verification Activity Today</h2>
    <div class="overview-grid">
        <div class="overview-card"><strong>{{ overview.today.approved }}</strong><span>Approved</span></div>
        <div class="overview-card"><strong>{{ overview.today.rejected }}</strong><span>Rejected</span></div>
        <div class="overview-card"><strong>{{ overview.today.kicked }}</strong><span>Kicked</span></div>
        <div class="overview-card"><strong>{{ overview.today.banned }}</strong><span>Banned</span></div>
    </div>
    <div class="overview-grid">
        <div class="overview-card"><strong>{{ overview.today.left }}</strong><span>Left before review</span></div>
        <div class="overview-card"><strong>{{ overview.status_counts.approved }}</strong><span>Total approved</span></div>
        <div class="overview-card"><strong>{{ overview.status_counts.rejected }}</strong><span>Total rejected</span></div>
        <div class="overview-card"><strong>{{ overview.status_counts.banned }}</strong><span>Total banned</span></div>
    </div>
</div>

<div class="panel">
    <h2>Pending Applications</h2>
    {% if overview.pending_applications %}
        <table class="data-table">
            <thead>
                <tr>
                    <th>User</th>
                    <th>State</th>
                    <th>Submitted</th>
                    <th>Links</th>
                </tr>
            </thead>
            <tbody>
                {% for application in overview.pending_applications %}
                    <tr>
                        <td>{{ application.user }}</td>
                        <td><span class="pill {{ application.state_class }}">{{ application.state }}</span></td>
                        <td>{{ application.submitted_at }}</td>
                        <td>
                            {% if application.review_url %}<a class="muted-link" href="{{ application.review_url }}" target="_blank">Review</a>{% endif %}
                            {% if application.thread_url %} {% if application.review_url %} · {% endif %}<a class="muted-link" href="{{ application.thread_url }}" target="_blank">Thread</a>{% endif %}
                            {% if not application.review_url and not application.thread_url %}<span class="hint">No links</span>{% endif %}
                        </td>
                    </tr>
                {% endfor %}
            </tbody>
        </table>
    {% else %}
        <p class="hint">No pending applications. Suspiciously peaceful.</p>
    {% endif %}
</div>

<div class="panel">
    <h2>Recent Outcomes</h2>
    {% if overview.recent_outcomes %}
        <table class="data-table">
            <thead>
                <tr>
                    <th>User</th>
                    <th>Status</th>
                    <th>When</th>
                    <th>Links</th>
                </tr>
            </thead>
            <tbody>
                {% for application in overview.recent_outcomes %}
                    <tr>
                        <td>{{ application.user }}</td>
                        <td><span class="pill {{ application.state_class }}">{{ application.state }}</span></td>
                        <td>{{ application.actioned_at }}</td>
                        <td>
                            {% if application.log_url %}<a class="muted-link" href="{{ application.log_url }}" target="_blank">Log</a>{% endif %}
                            {% if application.thread_url %} {% if application.log_url %} · {% endif %}<a class="muted-link" href="{{ application.thread_url }}" target="_blank">Thread</a>{% endif %}
                            {% if not application.log_url and not application.thread_url %}<span class="hint">No links</span>{% endif %}
                        </td>
                    </tr>
                {% endfor %}
            </tbody>
        </table>
    {% else %}
        <p class="hint">No recent outcomes yet.</p>
    {% endif %}
</div>
{% endif %}
"""


DM_TEMPLATES_BODY_HTML = """
<div class="panel page-intro">
    <h2>DM Templates</h2>
    <p class="hint">
        These messages are sent to users during verification actions. Edit the wording here, then save at the bottom.
        Available variables:
    </p>

    <div class="variable-list">
        <code>{user}</code>
        <code>{user_name}</code>
        <code>{user_id}</code>
        <code>{server_name}</code>
        <code>{moderator}</code>
        <code>{moderator_name}</code>
        <code>{moderator_id}</code>
        <code>{application_id}</code>
        <code>{reason}</code>
        <code>{reason_block}</code>
    </div>

    <form method="get" action="{{ url_for('dm_templates') }}">
        <label>Server</label>
        <select name="guild_id" onchange="this.form.submit()">
            {% for guild in guilds %}
                <option value="{{ guild.id }}" {{ 'selected' if guild.id == selected_guild_id else '' }}>{{ guild.name }}</option>
            {% endfor %}
        </select>
    </form>
</div>

{% if selected_guild_id %}
<form method="post" action="{{ url_for('dm_templates') }}">
    <input type="hidden" name="guild_id" value="{{ selected_guild_id }}">

    <div class="panel">
        <h2>Quick Actions</h2>
        <p class="hint section-note">
            Jump to the template group you want, because scrolling through text boxes is not a personality trait.
        </p>

        <div class="quick-actions">
            <a class="button-link secondary" href="#dm-success">Successful Outcomes</a>
            <a class="button-link secondary" href="#dm-rejections">Rejected Outcomes</a>
            <a class="button-link secondary" href="#dm-conversation">Conversation</a>
        </div>
    </div>

    <div class="panel" id="dm-success">
        <h2>Successful Outcomes</h2>
        <p class="hint section-note">
            Sent when an application is approved.
        </p>

        {% for template in templates %}
            {% if template.key in ['approved'] %}
                <div class="template-card">
                    <div class="card-header">
                        <div>
                            <h3>{{ template.label }}</h3>
                            <p class="template-meta">Key: <code>{{ template.key }}</code></p>
                        </div>
                    </div>

                    <textarea name="template_{{ template.key }}" rows="5">{{ template.text }}</textarea>

                    <details class="default-details">
                        <summary>Show default text</summary>
                        <pre>{{ template.default }}</pre>
                    </details>
                </div>
            {% endif %}
        {% endfor %}
    </div>

    <div class="panel" id="dm-rejections">
        <h2>Rejected Outcomes</h2>
        <p class="hint section-note">
            Sent when an application is denied, kicked, or banned.
        </p>

        {% for template in templates %}
            {% if template.key in ['denied', 'rejected', 'kicked', 'banned'] %}
                <div class="template-card">
                    <div class="card-header">
                        <div>
                            <h3>{{ template.label }}</h3>
                            <p class="template-meta">Key: <code>{{ template.key }}</code></p>
                        </div>
                    </div>

                    <textarea name="template_{{ template.key }}" rows="5">{{ template.text }}</textarea>

                    <details class="default-details">
                        <summary>Show default text</summary>
                        <pre>{{ template.default }}</pre>
                    </details>
                </div>
            {% endif %}
        {% endfor %}
    </div>

    <div class="panel" id="dm-conversation">
        <h2>Conversation</h2>
        <p class="hint section-note">
            Sent when staff need to ask the user a question during verification.
        </p>

        {% for template in templates %}
            {% if template.key in ['questioning', 'question'] %}
                <div class="template-card">
                    <div class="card-header">
                        <div>
                            <h3>{{ template.label }}</h3>
                            <p class="template-meta">Key: <code>{{ template.key }}</code></p>
                        </div>
                    </div>

                    <textarea name="template_{{ template.key }}" rows="5">{{ template.text }}</textarea>

                    <details class="default-details">
                        <summary>Show default text</summary>
                        <pre>{{ template.default }}</pre>
                    </details>
                </div>
            {% endif %}
        {% endfor %}
    </div>

    <div class="panel">
        <h2>Other Templates</h2>
        <p class="hint section-note">
            Any template keys not recognised by the grouped layout appear here, because hiding unknown config would be a bit dum.
        </p>

        {% for template in templates %}
            {% if template.key not in ['approved', 'denied', 'rejected', 'kicked', 'banned', 'questioning', 'question'] %}
                <div class="template-card">
                    <div class="card-header">
                        <div>
                            <h3>{{ template.label }}</h3>
                            <p class="template-meta">Key: <code>{{ template.key }}</code></p>
                        </div>
                    </div>

                    <textarea name="template_{{ template.key }}" rows="5">{{ template.text }}</textarea>

                    <details class="default-details">
                        <summary>Show default text</summary>
                        <pre>{{ template.default }}</pre>
                    </details>
                </div>
            {% endif %}
        {% endfor %}
    </div>

    <div class="panel action-panel">
        <button type="submit">Save DM Templates</button>
    </div>
</form>
{% else %}
<div class="panel"><p>No servers available.</p></div>
{% endif %}
"""


BACKUPS_BODY_HTML = """
<div class="panel page-intro">
    <h2>Encrypted Backups</h2>
    <p class="hint">
        Create or restore an encrypted <code>.tfsbackup</code> file containing the bot database and uploads.
        The password is not stored, because that would be a bit braindead.
    </p>

    <div class="health-list">
        <div class="health-item">
            <small>Database</small>
            <span>{{ database_path }}</span>
        </div>

        <div class="health-item">
            <small>Database Size</small>
            <span>{{ database_size }}</span>
        </div>

        <div class="health-item">
            <small>Uploads Folder</small>
            <span>{{ uploads_state }}</span>
        </div>

        <div class="health-item">
            <small>Backup Extension</small>
            <span><code>.tfsbackup</code></span>
        </div>
    </div>

    <div class="quick-actions">
        <a class="button-link secondary" href="#create-backup">Create Backup</a>
        <a class="button-link secondary" href="#restore-backup">Restore Backup</a>
        <a class="button-link secondary" href="#backup-contents">Backup Contents</a>
    </div>
</div>

{% if restore_completed %}
<div class="panel restore-warning">
    <h2>Restart Required</h2>
    <p class="hint">
        <strong>Backup restored successfully. Restart the bot now.</strong>
        Do not keep using the WebUI until the bot has restarted, because the database has been replaced underneath the running process.
        That is useful, but also deeply cursed.
    </p>
</div>
{% endif %}


<div class="panel" id="backup-contents">
    <h2>What This Backup Contains</h2>

    <table class="data-table">
        <thead>
            <tr>
                <th>Path</th>
                <th>Included</th>
                <th>Purpose</th>
            </tr>
        </thead>
        <tbody>
            <tr>
                <td><code>data/tfsbot.sqlite3</code></td>
                <td><span class="pill good">Yes</span></td>
                <td>Main bot database: applications, forms, permissions, settings, templates.</td>
            </tr>
            <tr>
                <td><code>data/uploads/</code></td>
                <td><span class="pill good">Yes, if it exists</span></td>
                <td>Uploaded WebUI images and other stored files.</td>
            </tr>
            <tr>
                <td><code>.env</code></td>
                <td><span class="pill warn">Optional</span></td>
                <td>Bot token and runtime config. Sensitive, obviously!</td>
            </tr>
        </tbody>
    </table>
</div>


<div class="panel" id="create-backup">
    <h2>Create Backup</h2>
    <p class="hint section-note">
        Creates an encrypted backup containing the SQLite database and uploads folder. Save the file somewhere safe and keep the password somewhere safer.
    </p>

    <form method="post">
        <input type="hidden" name="action" value="create_backup">

        <label>Backup Password</label>
        <input
            type="password"
            name="password"
            autocomplete="new-password"
            required
            minlength="10"
            placeholder="Use something long and not rubbish"
        >

        <label>Confirm Backup Password</label>
        <input
            type="password"
            name="confirm_password"
            autocomplete="new-password"
            required
            minlength="10"
        >

        <label>
            <input
                type="checkbox"
                name="include_env"
                value="1"
                style="width: auto; margin-right: 8px;"
            >
            Include <code>.env</code> file
        </label>

        <p class="hint">
            Including <code>.env</code> means the backup may contain the Discord bot token.
            ONLY do this IF the backup password is strong and you understand that LOSING the password means LOSING access to the backup.
        </p>

        <div class="button-row">
            <button type="submit">Create Encrypted Backup</button>
        </div>
    </form>
</div>

<div class="panel danger-panel" id="restore-backup">
    <h2>Restore Backup</h2>

    <p class="hint section-note">
        Restoring replaces the current database with the uploaded backup.
        The current database and uploads are copied to <code>data/restore_safety/</code> first, because not testing the lifeboat before using that badass looking slide is generally a bad idea.
    </p>

    <div class="backup-steps">
        <div class="backup-step">
            <strong>Before restoring</strong>
            Make sure this is the backup you actually want. The password must match the backup file.
        </div>

        <div class="backup-step">
            <strong>During restore</strong>
            The WebUI will replace <code>data/tfsbot.sqlite3</code> and optionally restore uploads and <code>.env</code>.
        </div>

        <div class="backup-step">
            <strong>After restoring</strong>
            Restart the bot immediately. Do not keep using the WebUI until the restart is done.
        </div>
    </div>

    <form method="post" enctype="multipart/form-data">
        <input type="hidden" name="action" value="restore_backup">

        <label>Backup File</label>
        <input
            type="file"
            name="backup_file"
            accept=".tfsbackup"
            required
        >

        <label>Backup Password</label>
        <input
            type="password"
            name="restore_password"
            autocomplete="current-password"
            required
        >

        <label>
            <input
                type="checkbox"
                name="restore_uploads"
                value="1"
                checked
                style="width: auto; margin-right: 8px;"
            >
            Restore <code>data/uploads/</code>
        </label>

        <label>
            <input
                type="checkbox"
                name="restore_env"
                value="1"
                style="width: auto; margin-right: 8px;"
            >
            Restore <code>.env</code> if the backup contains it
        </label>

        <label>Confirmation</label>
        <input
            type="text"
            name="restore_confirm"
            placeholder="Type RESTORE"
            required
        >

        <p class="hint">
            After restoring, restart the bot so every loaded cache and connection uses the restored database.
        </p>

        <div class="button-row">
            <button type="submit" class="danger-button">Restore Backup</button>
        </div>
    </form>
</div>
"""


UPLOADS_MANAGER_BODY_HTML = """
<div class="panel page-intro">
    <h2>Uploads</h2>
    <p class="hint">
        Manage uploaded images used by the Embed Builder. Folders keep author icons, thumbnails, and random server images from being mixed into one big stew.

    <div class="quick-actions">
        <a class="button-link secondary" href="#upload-file">Upload File</a>
        <a class="button-link secondary" href="#create-folder">Create Folder</a>
        <a class="button-link secondary" href="#uploaded-files">Uploaded Files</a>
    </div>
</div>

<div class="panel" id="upload-file">
    <h2>Upload File</h2>

    <form method="post" action="{{ url_for('uploads_manager_page') }}" enctype="multipart/form-data">
        <input type="hidden" name="action" value="upload_file">

        <label>Folder</label>
        <select name="folder">
            <option value="">Root</option>
            {% for folder in folders %}
                <option value="{{ folder.path }}" {{ 'selected' if folder.path == selected_folder else '' }}>{{ folder.label }}</option>
            {% endfor %}
        </select>

        <label>Or new folder</label>
        <input name="new_folder" placeholder="author-icons">

        <label>Image file</label>
        <input type="file" name="image" accept="image/png,image/jpeg,image/gif,image/webp" required>

        <div class="button-row">
            <button type="submit">Upload Image</button>
        </div>
    </form>
</div>

<div class="panel" id="create-folder">
    <h2>Create Folder</h2>

    <form method="post" action="{{ url_for('uploads_manager_page') }}">
        <input type="hidden" name="action" value="create_folder">

        <label>Folder name</label>
        <input name="folder" placeholder="author-icons" required>

        <p class="hint">
            Use simple names like <code>author-icons</code>, <code>thumbnails</code>, or <code>events</code>.
        </p>

        <div class="button-row">
            <button type="submit">Create Folder</button>
        </div>
    </form>
</div>

<div class="panel" id="uploaded-files">
    <h2>Uploaded Files</h2>

    {% if uploaded_images %}
        <table class="data-table">
            <thead>
                <tr>
                    <th>Preview</th>
                    <th>File</th>
                    <th>Folder</th>
                    <th>Size</th>
                    <th>Modified</th>
                    <th>Delete</th>
                </tr>
            </thead>
            <tbody>
                {% for image in uploaded_images %}
                    <tr>
                        <td>
                            <img src="{{ image.url }}" style="width: 54px; height: 54px; object-fit: cover; border-radius: 8px; border: 1px solid var(--border);">
                        </td>
                        <td><code>{{ image.filename }}</code></td>
                        <td>{{ image.folder_label }}</td>
                        <td>{{ image.size }}</td>
                        <td>{{ image.modified }}</td>
                        <td>
                            <form method="post" action="{{ url_for('uploads_manager_page') }}">
                                <input type="hidden" name="action" value="delete_file">
                                <input type="hidden" name="file_reference" value="{{ image.reference }}">
                                <button type="submit" class="danger-button">Delete</button>
                            </form>
                        </td>
                    </tr>
                {% endfor %}
            </tbody>
        </table>
    {% else %}
        <p class="hint">No uploaded images yet. Suspiciously clean.</p>
    {% endif %}
</div>

<div class="panel danger-panel">
    <h2>Delete Empty Folder</h2>
    <p class="hint">
        Only empty folders can be deleted.
    </p>

    <form method="post" action="{{ url_for('uploads_manager_page') }}">
        <input type="hidden" name="action" value="delete_folder">

        <label>Folder</label>
        <select name="folder" required>
            {% for folder in folders %}
                <option value="{{ folder.path }}">{{ folder.label }}</option>
            {% endfor %}
        </select>

        <label>Confirmation</label>
        <input name="confirm" placeholder="Type DELETE">

        <div class="button-row">
            <button type="submit" class="danger-button">Delete Empty Folder</button>
        </div>
    </form>
</div>
"""


FORMS_BODY_HTML = """
<div class="panel page-intro">
    <h2>Forms</h2>
    <p class="hint">
        Create and edit Discord modal forms from here. Changing the verification form affects newly opened forms; repost the verification panel after changing it.
    </p>

    <form method="get" action="{{ url_for('forms_page') }}">
        <div class="setting-grid">
            <div>
                <label>Server</label>
                <select name="guild_id" onchange="this.form.submit()">
                    {% for guild in guilds %}
                        <option value="{{ guild.id }}" {{ 'selected' if guild.id == selected_guild_id else '' }}>{{ guild.name }}</option>
                    {% endfor %}
                </select>
            </div>

            {% if selected_guild_id %}
                <div>
                    <label>Form</label>
                    <select name="form_key" onchange="this.form.submit()">
                        {% for form in forms %}
                            <option value="{{ form.key }}" {{ 'selected' if form.key == selected_form_key else '' }}>{{ form.key }} - {{ form.title }}</option>
                        {% endfor %}
                    </select>
                </div>
            {% endif %}
        </div>
    </form>
</div>

{% if selected_form %}
<div class="panel">
    <h2>Selected Form</h2>

    <div class="stat-grid">
        <div class="stat-card">
            <strong>Form Key</strong>
            <code>{{ selected_form_key }}</code>
        </div>

        <div class="stat-card">
            <strong>Title</strong>
            {{ selected_form.title }}
        </div>

        <div class="stat-card">
            <strong>Questions</strong>
            {{ questions|length }} question(s), {{ modal_pages }} modal page(s)
        </div>

        <div class="stat-card">
            <strong>Verification Form</strong>
            <span class="pill {{ 'good' if selected_form_key == verification_form_key else 'warn' }}">
                {{ 'Yes' if selected_form_key == verification_form_key else 'No' }}
            </span>
        </div>
    </div>

    <div class="quick-actions">
        <a class="button-link secondary" href="{{ url_for('forms_viewer_page', guild_id=selected_guild_id, form_key=selected_form_key) }}">Preview Form</a>

        <form method="post" action="{{ url_for('forms_page') }}" class="inline-form">
            <input type="hidden" name="action" value="set_verification_form">
            <input type="hidden" name="guild_id" value="{{ selected_guild_id }}">
            <input type="hidden" name="form_key" value="{{ selected_form_key }}">
            <button type="submit" class="secondary-button">Set as Verification Form</button>
        </form>

        <a class="button-link secondary" href="#publish-form-panel">Publish Form Panel</a>
        <a class="button-link secondary" href="#create-form-panel">Create New Form</a>
    </div>
</div>

<div class="panel">
    <h2>Edit Selected Form</h2>

    <form method="post" action="{{ url_for('forms_page') }}">
        <input type="hidden" name="action" value="save_form">
        <input type="hidden" name="guild_id" value="{{ selected_guild_id }}">
        <input type="hidden" name="form_key" value="{{ selected_form_key }}">

        <div class="setting-grid">
            <div>
                <label>Form key</label>
                <input value="{{ selected_form_key }}" disabled>
            </div>

            <div>
                <label>Question count</label>
                <input value="{{ questions|length }} question(s), {{ modal_pages }} modal page(s)" disabled>
            </div>

            <div>
                <label>Title</label>
                <input name="form_title" value="{{ selected_form.title }}" maxlength="45" required>
            </div>

            <div>
                <label>Custom ID prefix</label>
                <input name="custom_id_prefix" value="{{ selected_form.custom_id_prefix }}" maxlength="60" required>
            </div>
        </div>

        <div class="button-row">
            <button type="submit">Save Form</button>
            <a class="button-link secondary" href="{{ url_for('forms_viewer_page', guild_id=selected_guild_id, form_key=selected_form_key) }}">Preview Form</a>
        </div>
    </form>
</div>

<div class="panel">
    <h2>Verification Form</h2>
    <p class="hint">
        Current verification form: <code>{{ verification_form_key }}</code>.
        The verification panel will use whichever form is selected here. Existing posted panels do not magically rewrite themselves.
    </p>

    <form method="post" action="{{ url_for('forms_page') }}">
        <input type="hidden" name="action" value="set_verification_form">
        <input type="hidden" name="guild_id" value="{{ selected_guild_id }}">
        <input type="hidden" name="form_key" value="{{ selected_form_key }}">

        <div class="button-row">
            <button type="submit">Use This Form For Verification</button>
        </div>
    </form>

    {% if selected_form_key == 'verification' %}
        <form method="post" action="{{ url_for('forms_page') }}">
            <input type="hidden" name="action" value="reset_verification_form">
            <input type="hidden" name="guild_id" value="{{ selected_guild_id }}">
            <input type="hidden" name="form_key" value="{{ selected_form_key }}">

            <label>Reset confirmation</label>
            <input name="reset_confirm" placeholder="Type RESET">

            <div class="button-row">
                <button type="submit" class="danger-button">Reset Built-In Verification Form</button>
            </div>
        </form>
    {% endif %}
</div>

<div class="panel">
    <h2>Add Question</h2>
    <form method="post" action="{{ url_for('forms_page') }}">
        <input type="hidden" name="action" value="add_question">
        <input type="hidden" name="guild_id" value="{{ selected_guild_id }}">
        <input type="hidden" name="form_key" value="{{ selected_form_key }}">

        <div class="setting-grid">
            <div>
                <label>Question key</label>
                <input name="question_key" placeholder="age" maxlength="80" required>
            </div>

            <div>
                <label>Style</label>
                <select name="question_style">
                    <option value="short">Short answer</option>
                    <option value="paragraph">Paragraph</option>
                </select>
            </div>

            <div class="wide-field">
                <label>Question label</label>
                <input name="question_label" maxlength="45" required>
            </div>

            <div class="wide-field">
                <label>Placeholder</label>
                <input name="question_placeholder" maxlength="100">
            </div>

            <div>
                <label>Minimum length</label>
                <input type="number" name="question_min_length" min="0">
            </div>

            <div>
                <label>Maximum length</label>
                <input type="number" name="question_max_length" min="1" max="4000">
            </div>

            <div class="wide-field">
                <label>
                    <input type="checkbox" name="question_required" checked style="width: auto; margin-right: 8px;">
                    Required
                </label>
            </div>
        </div>

        <div class="button-row">
            <button type="submit">Add Question</button>
        </div>
    </form>
</div>

<div class="panel">
    <h2>Questions</h2>

    <p class="hint section-note">
        Edit existing questions here. Use the order field to move questions around. Discord shows up to 5 questions per modal page.
    </p>

    {% if questions %}
        <form method="post" action="{{ url_for('forms_page') }}">
            <input type="hidden" name="action" value="save_questions">
            <input type="hidden" name="guild_id" value="{{ selected_guild_id }}">
            <input type="hidden" name="form_key" value="{{ selected_form_key }}">

            <table class="data-table">
                <thead>
                    <tr>
                        <th>Order</th>
                        <th>Key</th>
                        <th>Question</th>
                        <th>Style</th>
                        <th>Required</th>
                        <th>Lengths</th>
                    </tr>
                </thead>
                <tbody>
                    {% for question in questions %}
                        <tr>
                            <td style="width: 90px;">
                                <input type="hidden" name="question_key[]" value="{{ question.question_key }}">
                                <input type="number" name="sort_order_{{ question.question_key }}" min="1" value="{{ question.sort_order }}">
                            </td>
                            <td><code>{{ question.question_key }}</code></td>
                            <td>
                                <input name="label_{{ question.question_key }}" value="{{ question.label }}" maxlength="45" required>
                                <label>Placeholder</label>
                                <input name="placeholder_{{ question.question_key }}" value="{{ question.placeholder or '' }}" maxlength="100">
                            </td>
                            <td>
                                <select name="style_{{ question.question_key }}">
                                    <option value="short" {{ 'selected' if question.style == 'short' else '' }}>Short</option>
                                    <option value="paragraph" {{ 'selected' if question.style == 'paragraph' else '' }}>Paragraph</option>
                                </select>
                            </td>
                            <td>
                                <input type="checkbox" name="required_{{ question.question_key }}" {{ 'checked' if question.required else '' }} style="width: auto;">
                            </td>
                            <td>
                                <input type="number" name="min_length_{{ question.question_key }}" min="0" value="{{ question.min_length if question.min_length is not none else '' }}" placeholder="Min">
                                <input type="number" name="max_length_{{ question.question_key }}" min="1" max="4000" value="{{ question.max_length if question.max_length is not none else '' }}" placeholder="Max" style="margin-top: 8px;">
                            </td>
                        </tr>
                    {% endfor %}
                </tbody>
            </table>

            <div class="button-row">
                <button type="submit">Save Question Changes</button>
            </div>
        </form>
    {% else %}
        <p class="hint">This form has no questions yet. Peaceful, but not very useful.</p>
    {% endif %}
</div>

{% if questions %}
<div class="panel danger-panel">
    <h2>Delete Question</h2>
    <form method="post" action="{{ url_for('forms_page') }}">
        <input type="hidden" name="action" value="delete_question">
        <input type="hidden" name="guild_id" value="{{ selected_guild_id }}">
        <input type="hidden" name="form_key" value="{{ selected_form_key }}">

        <label>Question</label>
        <select name="delete_question_key">
            {% for question in questions %}
                <option value="{{ question.question_key }}">{{ question.question_key }} - {{ question.label }}</option>
            {% endfor %}
        </select>

        <label>Confirmation</label>
        <input name="delete_question_confirm" placeholder="Type DELETE">

        <div class="button-row">
            <button type="submit" class="danger-button">Delete Question</button>
        </div>
    </form>
</div>
{% endif %}

<div class="panel" id="publish-form-panel">
    <h2>Publish Form Panel</h2>
    <p class="hint">
        This posts a general form button panel. Verification panels are still posted from the Verification page.
    </p>

    <form method="post" action="{{ url_for('forms_page') }}">
        <input type="hidden" name="action" value="publish_form">
        <input type="hidden" name="guild_id" value="{{ selected_guild_id }}">
        <input type="hidden" name="form_key" value="{{ selected_form_key }}">

        <label>Channel</label>
        <select name="publish_channel_id" required>
            {% for channel in text_channels %}
                <option value="{{ channel.id }}">#{{ channel.name }}</option>
            {% endfor %}
        </select>

        <label>Panel title</label>
        <input name="publish_title" value="{{ selected_form.title }}" required>

        <label>Panel description</label>
        <textarea name="publish_description" rows="4" required>Click the button below to complete this form.</textarea>

        <div class="button-row">
            <button type="submit">Publish Form Panel</button>
        </div>
    </form>
</div>

{% if selected_form_key != 'verification' %}
<div class="panel danger-panel">
    <h2>Delete Form</h2>
    <p class="hint">Deleting a form removes its questions and published panel registrations. Submissions may remain in history. Computers love half-memories.</p>

    <form method="post" action="{{ url_for('forms_page') }}">
        <input type="hidden" name="action" value="delete_form">
        <input type="hidden" name="guild_id" value="{{ selected_guild_id }}">
        <input type="hidden" name="form_key" value="{{ selected_form_key }}">

        <label>Confirmation</label>
        <input name="delete_form_confirm" placeholder="Type DELETE">

        <div class="button-row">
            <button type="submit" class="danger-button">Delete Form</button>
        </div>
    </form>
</div>
{% endif %}
{% elif selected_guild_id %}
<div class="panel"><p class="hint">No form selected yet.</p></div>
{% else %}
<div class="panel"><p>No servers available.</p></div>
{% endif %}

{% if selected_guild_id %}
<div class="panel">
    <h2>Create New Form</h2>
    <form method="post" action="{{ url_for('forms_page') }}">
        <input type="hidden" name="action" value="create_form">
        <input type="hidden" name="guild_id" value="{{ selected_guild_id }}">

        <div class="setting-grid">
            <div>
                <label>Form key</label>
                <input name="new_form_key" placeholder="staff_app" maxlength="40" required>
                <p class="hint">Lowercase letters, numbers, and underscores only.</p>
            </div>

            <div>
                <label>Title</label>
                <input name="new_form_title" placeholder="Staff Application" maxlength="45" required>
            </div>

        </div>

        <div class="button-row">
            <button type="submit">Create Form</button>
        </div>
    </form>
</div>
{% endif %}
"""

FORM_VIEWER_BODY_HTML = """
<div class="panel">
    <h2>Form Preview</h2>
    <p class="hint">
        Read-only view of the selected form. This does not edit, publish, duplicate, disable, export, or do any other surprise nonsense.
    </p>

    <div class="health-list">
        <div class="health-item">
            <small>Form</small>
            <span><code>{{ form_key }}</code></span>
        </div>

        <div class="health-item">
            <small>Title</small>
            <span>{{ form_title }}</span>
        </div>

        <div class="health-item">
            <small>Custom ID Prefix</small>
            <span><code>{{ custom_id_prefix }}</code></span>
        </div>

        <div class="health-item">
            <small>Questions</small>
            <span>{{ question_count }} question(s), {{ page_count }} modal page(s)</span>
        </div>
    </div>

    <div class="button-row">
        <a class="button-link secondary" href="{{ url_for('forms_page', guild_id=selected_guild_id, form_key=form_key) }}">Back to Forms</a>
    </div>
</div>

{% if pages %}
    {% for page in pages %}
        <div class="panel">
            <h2>Modal Page {{ page.number }}</h2>
            <p class="hint">
                Discord modals can contain up to 5 questions.
            </p>

            <table class="data-table">
                <thead>
                    <tr>
                        <th>#</th>
                        <th>Key</th>
                        <th>Question</th>
                        <th>Style</th>
                        <th>Required</th>
                        <th>Limits</th>
                    </tr>
                </thead>
                <tbody>
                    {% for question in page.questions %}
                        <tr>
                            <td>{{ question.number }}</td>
                            <td><code>{{ question.key }}</code></td>
                            <td>
                                <strong>{{ question.label }}</strong>
                                {% if question.placeholder %}
                                    <br><span class="hint">Placeholder: {{ question.placeholder }}</span>
                                {% endif %}
                            </td>
                            <td>{{ question.style }}</td>
                            <td><span class="pill {{ 'good' if question.required else 'warn' }}">{{ 'Yes' if question.required else 'No' }}</span></td>
                            <td>{{ question.limits }}</td>
                        </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
    {% endfor %}
{% else %}
    <div class="panel">
        <p class="hint">This form has no questions yet.</p>
    </div>
{% endif %}
"""

ACCESS_DENIED_BODY_HTML = """
<div class="panel">
    <h2>Access Denied</h2>
    <p class="hint">
        Your Discord login is valid, but your WebUI role is <code>{{ webui_role }}</code>.
        This page is owner-only. Bureaucracy, but at least it is Discord bureaucracy.
    </p>
</div>
"""


VERIFICATION_BODY_HTML = """
<div class="panel page-intro">
    <h2>Verification</h2>
    <p class="hint">
        Manage the verification panel, review channels, approval roles, invite tracking, and application automod from here.
        Slash commands can still do the same things, but this is cooler.
    </p>

    <form method="get" action="{{ url_for('verification_page') }}">
        <label>Server</label>
        <select name="guild_id" onchange="this.form.submit()">
            {% for guild in guilds %}
                <option value="{{ guild.id }}" {{ 'selected' if guild.id == selected_guild_id else '' }}>{{ guild.name }}</option>
            {% endfor %}
        </select>
    </form>
</div>

{% if selected_guild_id %}
<form method="post" action="{{ url_for('verification_page') }}">
    <input type="hidden" name="guild_id" value="{{ selected_guild_id }}">

    <div class="panel">
        <h2>Quick Actions</h2>
        <p class="hint section-note">
            Jump to the main verification setup sections. No, this does not make Discord permissions less annoying, sadly.
        </p>

        <div class="quick-actions">
            <a class="button-link secondary" href="#verification-panel-setup">Panel Setup</a>
            <a class="button-link secondary" href="#review-log-channels">Review + Logs</a>
            <a class="button-link secondary" href="#approval-roles">Approval Roles</a>
            <a class="button-link secondary" href="#verification-automod">Automod</a>
            <a class="button-link secondary" href="#invite-tracking">Invite Tracking</a>
            <a class="button-link secondary" href="#application-maintenance">Application Maintenance</a>
        </div>
    </div>

    <div class="panel" id="verification-panel-setup">
        <h2>Verification Panel Setup</h2>
        <p class="hint section-note">
            Choose which form the verification panel should open, then optionally post or repost the panel to a channel.
            Existing posted panels do not update themselves, because Discord messages are not psychic.
        </p>

        <div class="setting-grid">
            <div>
                <label>Verification form</label>
                <select name="verification_form_key">
                    {% for form in forms %}
                        <option value="{{ form.key }}" {{ 'selected' if form.key == settings.verification_form_key else '' }}>{{ form.key }} - {{ form.title }}</option>
                    {% endfor %}
                </select>
            </div>

            <div>
                <label>Post/repost verification panel to</label>
                <select name="panel_channel_id">
                    <option value="">Do not post panel</option>
                    {% for channel in text_channels %}
                        <option value="{{ channel.id }}">#{{ channel.name }}</option>
                    {% endfor %}
                </select>
            </div>
        </div>

        <div class="button-row">
            <button type="submit" name="action" value="save_verification">Save Verification Settings</button>
            <button type="submit" name="action" value="save_and_post_panel" class="secondary-button">Save and Post Panel</button>
        </div>
    </div>

    <div class="panel" id="review-log-channels">
        <h2>Review + Log Channels</h2>
        <p class="hint section-note">
            Review applications go to the review channel. Final outcomes go to the log channel.
        </p>

        <div class="setting-grid">
            <div>
                <label>Review channel</label>
                <select name="review_channel_id">
                    <option value="">Not set</option>
                    {% for channel in text_channels %}
                        <option value="{{ channel.id }}" {{ 'selected' if channel.id == settings.review_channel_id else '' }}>#{{ channel.name }}</option>
                    {% endfor %}
                </select>
            </div>

            <div>
                <label>Log channel</label>
                <select name="log_channel_id">
                    <option value="">Not set</option>
                    {% for channel in text_channels %}
                        <option value="{{ channel.id }}" {{ 'selected' if channel.id == settings.log_channel_id else '' }}>#{{ channel.name }}</option>
                    {% endfor %}
                </select>
            </div>
        </div>

        <div class="button-row">
            <button type="submit" name="action" value="save_verification">Save Channel Settings</button>
        </div>
    </div>

    <div class="panel" id="approval-roles">
        <h2>Approval Roles</h2>
        <p class="hint section-note">
            On approval, the bot can give one role and remove one role. The bot's Discord role must be above both roles,
            because Discord loves hierarchy more than sense.
        </p>

        <div class="setting-grid">
            <div>
                <label>Role to give on approval</label>
                <select name="approved_add_role_id">
                    <option value="">Not set</option>
                    {% for role in roles %}
                        <option value="{{ role.id }}" {{ 'selected' if role.id == settings.approved_add_role_id else '' }}>{{ role.name }}</option>
                    {% endfor %}
                </select>
            </div>

            <div>
                <label>Role to remove on approval</label>
                <select name="approved_remove_role_id">
                    <option value="">Not set</option>
                    {% for role in roles %}
                        <option value="{{ role.id }}" {{ 'selected' if role.id == settings.approved_remove_role_id else '' }}>{{ role.name }}</option>
                    {% endfor %}
                </select>
            </div>
        </div>

        <div class="stat-grid">
            <div class="stat-card">
                <strong>When approved</strong>
                User can receive the configured approval role.
            </div>

            <div class="stat-card">
                <strong>Role removal</strong>
                User can lose the configured pre-verification role.
            </div>

            <div class="stat-card">
                <strong>Health check</strong>
                Overview shows if the bot role is too low.
            </div>
        </div>

        <div class="button-row">
            <button type="submit" name="action" value="save_verification">Save Approval Roles</button>
        </div>
    </div>

    <div class="panel" id="verification-automod">
        <h2>Verification Automod</h2>
        <p class="hint section-note">
            If enabled, applications containing any blocked term are automatically logged and banned.
            Keep one term per line. Terms are stored in SQLite and matched case-insensitively.
        </p>

        <label class="checkbox-row">
            <input type="checkbox" name="automod_enabled" {{ 'checked' if settings.automod_enabled else '' }}>
            Enable automatic ban for blocked application terms
        </label>

        <label>Blocked terms</label>
        <textarea name="automod_terms" class="terms-box" placeholder="one term per line">{{ automod_terms_text }}</textarea>

        <details class="default-details">
            <summary>Default automod list</summary>
            {% if default_terms %}
                <pre>{{ default_terms_text }}</pre>
            {% else %}
                <pre>No built-in default terms are bundled. Add one term per line to data/default_automod_terms.txt, then use “Add Default Terms”.</pre>
            {% endif %}
        </details>

        <div class="button-row">
            <button type="submit" name="action" value="save_verification">Save Automod Terms</button>
            <button type="submit" name="action" value="add_default_terms" class="secondary-button">Add Default Terms</button>
            <button type="submit" name="action" value="clear_automod_terms" class="danger-button">Clear Automod Terms</button>
        </div>
    </div>

    <div class="panel" id="invite-tracking">
        <h2>Invite Tracking</h2>
        <p class="hint section-note">
            Invite tracking runs automatically when a member joins. Refreshing the cache is useful after restarting the bot or creating/deleting invites.
        </p>

        <div class="stat-grid">
            <div class="stat-card">
                <strong>Status</strong>
                {{ invite_tracking_status }}
            </div>

            <div class="stat-card">
                <strong>Permission needed</strong>
                Manage Server
            </div>

            <div class="stat-card">
                <strong>Shown on apps</strong>
                Invite code and inviter
            </div>
        </div>

        <div class="button-row">
            <button type="submit" name="action" value="refresh_invites" class="secondary-button">Refresh Invite Cache</button>
        </div>
    </div>

    <div class="panel danger-panel" id="application-maintenance">
        <h2>Application Maintenance</h2>
        <p class="hint section-note">
            Cancel/reset stuck active applications. This marks them as cancelled, logs it, deletes the review message if possible,
            and locks/archives any questioning thread. It does not delete application history.
        </p>

        <div class="setting-grid">
            <div>
                <label>Cancel by User ID</label>
                <input name="cancel_user_id" placeholder="123456789012345678">
            </div>

            <div class="wide-field">
                <label>Cancellation reason</label>
                <input name="cancel_reason" placeholder="Optional reason for the cancellation log">
            </div>

            <div class="wide-field">
                <label>Confirmation</label>
                <input name="cancel_confirm" placeholder="Type CANCEL">
            </div>
        </div>

        <div class="button-row">
            <button type="submit" name="action" value="cancel_by_user" class="danger-button">Cancel by User ID</button>
            <button type="submit" name="action" value="cancel_all_pending" class="danger-button">Cancel All Pending</button>
        </div>
    </div>
</form>
{% else %}
<div class="panel"><p>No servers available.</p></div>
{% endif %}
"""


def create_webui(bot: discord.Client) -> Flask:
    app = Flask(__name__)

    secret_parts = [
        f"{credential.username}:{credential.password}"
        for credential in bot.config.webui_credentials
    ]

    discord_client_secret = getattr(
        bot.config,
        "discord_oauth_client_secret",
        "",
    )

    if discord_client_secret:
        secret_parts.append(discord_client_secret)

    app.secret_key = "|".join(secret_parts) or "tfsbot-dev-secret"

    app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    def is_logged_in() -> bool:
        return session.get("logged_in") is True

    def is_discord_login_enabled() -> bool:
        return bool(getattr(bot.config, "webui_discord_auth_enabled", False))

    def is_password_login_enabled() -> bool:
        return bool(
            getattr(bot.config, "webui_password_login_enabled", True)
            and bot.config.webui_credentials
        )

    def render_login_page(error: str | None = None) -> str:
        return render_template_string(
            LOGIN_HTML,
            error=error,
            discord_login_enabled=is_discord_login_enabled(),
            password_login_enabled=is_password_login_enabled(),
        )

    def get_discord_authorisation_url(state: str) -> str:
        query = urllib.parse.urlencode(
            {
                "client_id": str(bot.config.discord_oauth_client_id),
                "redirect_uri": bot.config.discord_oauth_redirect_uri,
                "response_type": "code",
                "scope": "identify guilds.members.read",
                "state": state,
            }
        )

        return f"https://discord.com/oauth2/authorize?{query}"

    def discord_api_request(
        url: str,
        method: str = "GET",
        data: dict[str, str] | None = None,
        access_token: str | None = None,
    ) -> dict[str, Any]:
        body: bytes | None = None
        headers: dict[str, str] = {
            "Accept": "application/json",
            "User-Agent": "TFSBot WebUI",
        }

        if data is not None:
            body = urllib.parse.urlencode(data).encode("utf-8")
            headers["Content-Type"] = "application/x-www-form-urlencoded"

        if access_token is not None:
            headers["Authorization"] = f"Bearer {access_token}"

        request_object = urllib.request.Request(
            url=url,
            data=body,
            headers=headers,
            method=method,
        )

        try:
            with urllib.request.urlopen(request_object, timeout=15) as response:
                return json.loads(response.read().decode("utf-8"))

        except urllib.error.HTTPError as error:
            try:
                error_body = error.read().decode("utf-8")
            except Exception:
                error_body = ""

            raise RuntimeError(
                f"Discord API request failed: HTTP {error.code} {error_body}"
            ) from error

        except urllib.error.URLError as error:
            raise RuntimeError(f"Discord API request failed: {error}") from error

    def exchange_discord_code_for_token(code: str) -> str:
        token_data = discord_api_request(
            url="https://discord.com/api/oauth2/token",
            method="POST",
            data={
                "client_id": str(bot.config.discord_oauth_client_id),
                "client_secret": bot.config.discord_oauth_client_secret,
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": bot.config.discord_oauth_redirect_uri,
            },
        )

        access_token = token_data.get("access_token")

        if not isinstance(access_token, str) or not access_token:
            raise RuntimeError("Discord did not return an access token.")

        return access_token

    def fetch_discord_user(access_token: str) -> dict[str, Any]:
        return discord_api_request(
            url="https://discord.com/api/users/@me",
            access_token=access_token,
        )

    def fetch_discord_member(access_token: str) -> dict[str, Any]:
        guild_id = bot.config.webui_discord_guild_id

        if guild_id is None:
            raise RuntimeError("WEBUI_DISCORD_GUILD_ID is not configured.")

        return discord_api_request(
            url=f"https://discord.com/api/users/@me/guilds/{guild_id}/member",
            access_token=access_token,
        )

    def get_webui_access_database_path() -> Path:
        application_store = getattr(bot, "application_store", None)

        if application_store is not None:
            raw_path = getattr(application_store, "database_path", None)

            if raw_path is not None:
                return Path(raw_path)

        return Path(getattr(bot.config, "application_db_path", "data/tfsbot.sqlite3"))

    def ensure_webui_access_tables() -> None:
        database_path = get_webui_access_database_path()
        database_path.parent.mkdir(parents=True, exist_ok=True)

        with sqlite3.connect(database_path) as database:
            database.execute(
                """
                CREATE TABLE IF NOT EXISTS webui_access_roles (
                    guild_id INTEGER NOT NULL,
                    access_level TEXT NOT NULL,
                    role_id INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (guild_id, access_level, role_id)
                )
                """
            )

    def get_stored_webui_access_role_ids(
        guild_id: int,
        access_level: str,
    ) -> tuple[int, ...]:
        ensure_webui_access_tables()

        with sqlite3.connect(get_webui_access_database_path()) as database:
            rows = database.execute(
                """
                SELECT role_id
                FROM webui_access_roles
                WHERE guild_id = ?
                AND access_level = ?
                ORDER BY role_id ASC
                """,
                (guild_id, access_level),
            ).fetchall()

        return tuple(int(row[0]) for row in rows)

    def set_stored_webui_access_role_ids(
        guild_id: int,
        access_level: str,
        role_ids: list[int],
    ) -> None:
        ensure_webui_access_tables()

        cleaned_role_ids = sorted(set(role_ids))
        now = datetime.now(timezone.utc).isoformat()

        with sqlite3.connect(get_webui_access_database_path()) as database:
            database.execute(
                """
                DELETE FROM webui_access_roles
                WHERE guild_id = ?
                AND access_level = ?
                """,
                (guild_id, access_level),
            )

            database.executemany(
                """
                INSERT INTO webui_access_roles (
                    guild_id, access_level, role_id, created_at
                )
                VALUES (?, ?, ?, ?)
                """,
                [
                    (guild_id, access_level, role_id, now)
                    for role_id in cleaned_role_ids
                ],
            )

    def get_env_webui_owner_role_ids() -> tuple[int, ...]:
        owner_role_ids = tuple(
            getattr(bot.config, "webui_discord_owner_role_ids", ())
        )

        if owner_role_ids:
            return owner_role_ids

        return tuple(
            getattr(bot.config, "webui_discord_allowed_role_ids", ())
        )

    def get_env_webui_viewer_role_ids() -> tuple[int, ...]:
        return tuple(
            getattr(bot.config, "webui_discord_viewer_role_ids", ())
        )

    def get_effective_webui_access_role_ids(
        guild_id: int,
        access_level: str,
    ) -> tuple[int, ...]:
        try:
            stored_role_ids = get_stored_webui_access_role_ids(
                guild_id=guild_id,
                access_level=access_level,
            )
        except sqlite3.Error:
            stored_role_ids = ()

        if stored_role_ids:
            return stored_role_ids

        if access_level == "owner":
            return get_env_webui_owner_role_ids()

        if access_level == "viewer":
            return get_env_webui_viewer_role_ids()

        return ()

    def get_effective_webui_access_source(
        guild_id: int,
        access_level: str,
    ) -> str:
        try:
            stored_role_ids = get_stored_webui_access_role_ids(
                guild_id=guild_id,
                access_level=access_level,
            )
        except sqlite3.Error:
            stored_role_ids = ()

        if stored_role_ids:
            return "SQLite"

        if access_level == "owner" and get_env_webui_owner_role_ids():
            return ".env fallback"

        if access_level == "viewer" and get_env_webui_viewer_role_ids():
            return ".env fallback"

        return "Not set"

    def parse_role_ids_from_form(field_name: str) -> list[int]:
        role_ids: list[int] = []

        for raw_role_id in request.form.getlist(field_name):
            raw_role_id = raw_role_id.strip()

            if not raw_role_id:
                continue

            role_ids.append(int(raw_role_id))

        return sorted(set(role_ids))

    def build_webui_access_context(guild: discord.Guild | None) -> dict[str, Any]:
        if guild is None:
            return {
                "owner_role_ids": [],
                "viewer_role_ids": [],
                "owner_source": "Not set",
                "viewer_source": "Not set",
                "discord_auth_status": "Disabled",
                "discord_auth_class": "warn",
                "password_status": "Disabled",
                "password_class": "warn",
                "owner_count": 0,
                "viewer_count": 0,
            }

        owner_role_ids = get_effective_webui_access_role_ids(
            guild_id=guild.id,
            access_level="owner",
        )
        viewer_role_ids = get_effective_webui_access_role_ids(
            guild_id=guild.id,
            access_level="viewer",
        )

        return {
            "owner_role_ids": [str(role_id) for role_id in owner_role_ids],
            "viewer_role_ids": [str(role_id) for role_id in viewer_role_ids],
            "owner_source": get_effective_webui_access_source(guild.id, "owner"),
            "viewer_source": get_effective_webui_access_source(guild.id, "viewer"),
            "discord_auth_status": "Enabled" if is_discord_login_enabled() else "Disabled",
            "discord_auth_class": "good" if is_discord_login_enabled() else "warn",
            "password_status": "Enabled" if is_password_login_enabled() else "Disabled",
            "password_class": "good" if is_password_login_enabled() else "warn",
            "owner_count": len(owner_role_ids),
            "viewer_count": len(viewer_role_ids),
        }

    def get_matching_discord_webui_role(member_data: dict[str, Any]) -> str | None:
        guild_id = bot.config.webui_discord_guild_id

        if guild_id is None:
            return None

        member_role_ids = {
            str(role_id)
            for role_id in member_data.get("roles", [])
        }

        owner_role_ids = {
            str(role_id)
            for role_id in get_effective_webui_access_role_ids(
                guild_id=guild_id,
                access_level="owner",
            )
        }

        viewer_role_ids = {
            str(role_id)
            for role_id in get_effective_webui_access_role_ids(
                guild_id=guild_id,
                access_level="viewer",
            )
        }

        if owner_role_ids.intersection(member_role_ids):
            return "owner"

        if viewer_role_ids.intersection(member_role_ids):
            return "viewer"

        return None

    def validate_uploaded_image_filename(filename: str) -> str:
        safe_name = secure_filename(filename)

        if not safe_name:
            raise ValueError("Invalid filename.")

        extension = Path(safe_name).suffix.lower()

        if extension not in ALLOWED_IMAGE_EXTENSIONS:
            raise ValueError(
                "Unsupported image type. Use PNG, JPG, JPEG, GIF, or WEBP."
            )

        return safe_name


    def validate_upload_folder(folder: str | None) -> str:
        folder = (folder or "").strip().replace("\\", "/")

        if not folder:
            return ""

        parts: list[str] = []

        for raw_part in folder.split("/"):
            raw_part = raw_part.strip()

            if not raw_part:
                continue

            safe_part = secure_filename(raw_part)

            if not safe_part:
                raise ValueError("Invalid folder name.")

            if safe_part in {".", ".."}:
                raise ValueError("Invalid folder name.")

            parts.append(safe_part)

        if not parts:
            return ""

        return "/".join(parts)


    def get_upload_folder_path(folder: str | None) -> Path:
        safe_folder = validate_upload_folder(folder)
        folder_path = UPLOAD_DIR / safe_folder if safe_folder else UPLOAD_DIR

        resolved_upload_root = UPLOAD_DIR.resolve()
        resolved_folder_path = folder_path.resolve()

        if resolved_upload_root not in [resolved_folder_path, *resolved_folder_path.parents]:
            raise ValueError("Invalid upload folder.")

        return folder_path


    def validate_uploaded_image_reference(reference: str) -> str:
        reference = reference.strip().replace("\\", "/")

        if not reference:
            raise ValueError("Invalid uploaded image reference.")

        folder = validate_upload_folder(str(Path(reference).parent))
        filename = validate_uploaded_image_filename(Path(reference).name)

        if folder in {".", ""}:
            return filename

        return f"{folder}/{filename}"


    def get_uploaded_image_path(reference: str) -> Path:
        safe_reference = validate_uploaded_image_reference(reference)
        return UPLOAD_DIR / safe_reference


    def get_uploaded_image_preview_url(path: Path) -> str:
        mime_types = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".gif": "image/gif",
            ".webp": "image/webp",
        }

        mime_type = mime_types.get(path.suffix.lower())

        if mime_type is None:
            raise ValueError(f"Unsupported preview image type: {path.suffix}")

        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        return f"data:{mime_type};base64,{encoded}"


    def format_upload_size(size_bytes: int) -> str:
        if size_bytes < 1024:
            return f"{size_bytes} B"

        if size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"

        return f"{size_bytes / (1024 * 1024):.1f} MB"


    def get_attachment_filename_for_reference(reference: str) -> str:
        safe_reference = validate_uploaded_image_reference(reference)
        path = Path(safe_reference)

        if str(path.parent) in {".", ""}:
            return path.name

        folder_prefix = "__".join(path.parent.parts)
        return f"{folder_prefix}__{path.name}"


    def list_upload_folders() -> list[dict[str, str]]:
        folders: list[dict[str, str]] = []

        if not UPLOAD_DIR.exists():
            return folders

        for path in sorted(UPLOAD_DIR.rglob("*"), key=lambda item: item.as_posix().lower()):
            if not path.is_dir():
                continue

            relative_path = path.relative_to(UPLOAD_DIR).as_posix()

            if not relative_path or relative_path == ".":
                continue

            folders.append(
                {
                    "path": relative_path,
                    "label": relative_path,
                }
            )

        return folders


    def list_uploaded_images() -> list[dict[str, str]]:
        images: list[dict[str, str]] = []

        if not UPLOAD_DIR.exists():
            return images

        image_paths = [
            path
            for path in UPLOAD_DIR.rglob("*")
            if path.is_file()
            and path.suffix.lower() in ALLOWED_IMAGE_EXTENSIONS
        ]

        image_paths.sort(key=lambda item: item.stat().st_mtime, reverse=True)

        for path in image_paths:
            relative_path = path.relative_to(UPLOAD_DIR)
            reference = relative_path.as_posix()
            folder = relative_path.parent.as_posix()

            if folder == ".":
                folder = ""

            stat = path.stat()

            images.append(
                {
                    "reference": reference,
                    "filename": path.name,
                    "label": reference,
                    "folder": folder,
                    "folder_label": folder or "Root",
                    "url": get_uploaded_image_preview_url(path),
                    "size": format_upload_size(stat.st_size),
                    "modified": datetime.fromtimestamp(
                        stat.st_mtime,
                        timezone.utc,
                    ).strftime("%Y-%m-%d %H:%M UTC"),
                }
            )

        return images


    def get_available_channels() -> list[dict[str, str]]:
        channels: list[dict[str, str]] = []

        for guild in bot.guilds:
            member = guild.me

            if member is None:
                continue

            for channel in guild.text_channels:
                permissions = channel.permissions_for(member)

                if not permissions.view_channel or not permissions.send_messages:
                    continue

                channels.append(
                    {
                        "id": str(channel.id),
                        "label": f"{guild.name} / #{channel.name}",
                    }
                )

        return channels

    def build_selected_attachment_files(
        image_upload_filename: str | None,
        thumbnail_upload_filename: str | None,
        author_icon_upload_filename: str | None = None,
    ) -> tuple[str | None, str | None, str | None, list[discord.File]]:
        files: list[discord.File] = []
        attached_references: set[str] = set()

        image_url: str | None = None
        thumbnail_url: str | None = None
        author_icon_url: str | None = None

        for selected_reference, target in [
            (image_upload_filename, "image"),
            (thumbnail_upload_filename, "thumbnail"),
            (author_icon_upload_filename, "author_icon"),
        ]:
            if not selected_reference:
                continue

            safe_reference = validate_uploaded_image_reference(selected_reference)
            path = get_uploaded_image_path(safe_reference)

            if not path.exists():
                raise FileNotFoundError(f"Uploaded image not found: {selected_reference}")

            attachment_filename = get_attachment_filename_for_reference(safe_reference)

            if safe_reference not in attached_references:
                files.append(discord.File(path, filename=attachment_filename))
                attached_references.add(safe_reference)

            attachment_url = f"attachment://{attachment_filename}"

            if target == "image":
                image_url = attachment_url
            elif target == "thumbnail":
                thumbnail_url = attachment_url
            else:
                author_icon_url = attachment_url

        return image_url, thumbnail_url, author_icon_url, files

    async def send_embeds_to_channel(
        channel_id: int,
        embeds: list[discord.Embed],
        files: list[discord.File],
    ) -> None:
        channel = bot.get_channel(channel_id)

        if channel is None:
            channel = await bot.fetch_channel(channel_id)

        if not isinstance(channel, discord.TextChannel):
            raise RuntimeError("Selected channel is not a text channel.")

        await channel.send(
            embeds=embeds,
            files=files if files else None,
        )

    def run_coro_from_flask(coro: Coroutine[Any, Any, Any]) -> Any:
        future = asyncio.run_coroutine_threadsafe(coro, bot.loop)
        return future.result(timeout=15)


    def get_available_guilds() -> list[dict[str, str]]:
        return [
            {
                "id": str(guild.id),
                "name": guild.name,
            }
            for guild in sorted(bot.guilds, key=lambda item: item.name.lower())
        ]

    def get_selected_guild(guild_id_text: str | None) -> discord.Guild | None:
        if guild_id_text:
            try:
                guild_id = int(guild_id_text)
            except ValueError:
                guild_id = 0

            guild = bot.get_guild(guild_id)

            if guild is not None:
                return guild

        return bot.guilds[0] if bot.guilds else None

    def render_admin_page(
        title: str,
        active_page: str,
        body_template: str,
        message: str | None = None,
        error: str | None = None,
        **context: Any,
    ) -> str:
        body = render_template_string(body_template, **context)

        return render_template_string(
            ADMIN_PAGE_HTML,
            title=title,
            active_page=active_page,
            body=body,
            message=message,
            error=error,
            is_owner=is_webui_owner(),
            webui_role=current_webui_role(),
            display_name=get_session_display_name(),
        )

    def render_embed_builder_page(
        message: str | None = None,
        error: str | None = None,
    ) -> str:
        return render_template_string(
            EMBED_FORM_HTML,
            channels=get_available_channels(),
            uploaded_images=list_uploaded_images(),
            upload_folders=list_upload_folders(),
            message=message,
            error=error,
            active_page="embed_builder",
            is_owner=is_webui_owner(),
            webui_role=current_webui_role(),
            display_name=get_session_display_name(),
        )

    def current_webui_role() -> str:
        role = str(session.get("webui_role") or "").lower().strip()

        if role in {"owner", "viewer"}:
            return role

        if session.get("logged_in") is True and session.get("auth_method") == "password":
            return "owner"

        return "viewer"

    def is_webui_owner() -> bool:
        return current_webui_role() == "owner"

    def get_session_display_name() -> str:
        return str(
            session.get("display_name")
            or session.get("discord_username")
            or session.get("username")
            or "WebUI user"
        )

    def render_owner_required_page() -> str:
        return render_admin_page(
            title="Access Denied",
            active_page="overview",
            body_template=ACCESS_DENIED_BODY_HTML,
            webui_role=current_webui_role(),
            error="You need the owner WebUI role to use that page.",
        )

    def require_owner_page() -> str | None:
        if not is_logged_in():
            return redirect(url_for("login"))

        if not is_webui_owner():
            return render_owner_required_page()

        return None

    def get_template_store():
        template_store = getattr(bot, "dm_template_store", None)

        if template_store is None:
            raise RuntimeError("DM template store is not available.")

        return template_store

    def get_permission_store():
        permission_store = getattr(bot, "permission_store", None)

        if permission_store is None:
            raise RuntimeError("Permission store is not available.")

        return permission_store


    def get_guild_settings_store():
        settings_store = getattr(bot, "guild_settings", None)

        if settings_store is None:
            raise RuntimeError("Guild settings store is not available.")

        return settings_store

    def get_form_store():
        form_store = getattr(bot, "form_store", None)

        if form_store is None:
            raise RuntimeError("Form store is not available.")

        return form_store

    def get_invite_tracker_store():
        invite_tracker = getattr(bot, "invite_tracker", None)

        if invite_tracker is None:
            raise RuntimeError("Invite tracker is not available.")

        return invite_tracker

    def get_guild_roles(guild: discord.Guild) -> list[dict[str, str]]:
        roles = [role for role in guild.roles if not role.is_default()]
        roles.sort(key=lambda item: item.position, reverse=True)

        return [
            {
                "id": str(role.id),
                "name": role.name,
            }
            for role in roles
        ]


    def get_guild_text_channels(guild: discord.Guild) -> list[dict[str, str]]:
        channels = list(guild.text_channels)
        channels.sort(key=lambda item: (item.category.name if item.category else "", item.position, item.name.lower()))

        return [
            {
                "id": str(channel.id),
                "name": channel.name,
            }
            for channel in channels
        ]

    def get_current_verification_settings(guild: discord.Guild) -> dict[str, str | bool]:
        settings_store = get_guild_settings_store()

        return {
            "review_channel_id": str(settings_store.get_review_channel_id(guild.id) or ""),
            "log_channel_id": str(settings_store.get_application_log_channel_id(guild.id) or ""),
            "verification_form_key": settings_store.get_verification_form_key(guild.id) or FORM_KEY_VERIFICATION,
            "approved_add_role_id": str(settings_store.get_approved_add_role_id(guild.id) or ""),
            "approved_remove_role_id": str(settings_store.get_approved_remove_role_id(guild.id) or ""),
            "automod_enabled": settings_store.is_automod_enabled(guild.id),
        }

    def parse_terms_from_text(raw_text: str) -> list[str]:
        terms: list[str] = []

        for raw_line in raw_text.splitlines():
            stripped = raw_line.strip()

            if not stripped or stripped.startswith("#"):
                continue

            terms.append(stripped)

        return terms

    def parse_optional_int(raw_value: str | None) -> int | None:
        if raw_value is None:
            return None

        stripped = raw_value.strip()

        if not stripped:
            return None

        return int(stripped)

    def clean_form_key(raw_value: str) -> str:
        return raw_value.lower().strip()

    async def get_guild_forms(guild: discord.Guild) -> list[dict[str, str]]:
        form_store = get_form_store()
        stored_forms = await form_store.list_forms(guild.id)

        forms = [
            {
                "key": form.form_key,
                "title": form.title,
            }
            for form in stored_forms
        ]

        if not any(form["key"] == FORM_KEY_VERIFICATION for form in forms):
            forms.insert(0, {"key": FORM_KEY_VERIFICATION, "title": "Verification"})

        return forms

    async def post_verification_panel_from_webui(
        guild: discord.Guild,
        channel_id: int,
        form_key: str,
    ) -> None:
        channel = guild.get_channel(channel_id)

        if channel is None:
            fetched_channel = await bot.fetch_channel(channel_id)
        else:
            fetched_channel = channel

        if not isinstance(fetched_channel, discord.TextChannel):
            raise RuntimeError("Selected panel channel is not a text channel.")

        form_store = get_form_store()
        form_config = await form_store.get_form_config(
            guild_id=guild.id,
            form_key=form_key,
            fallback_json_path=VERIFICATION_FORM_PATH,
        )

        embed = discord.Embed(
            title=f"{guild.name} Verification",
            description=(
                "Welcome!\n\n"
                f"Please complete the **{discord.utils.escape_markdown(form_config.title)}** form "
                "to apply for access to the server.\n\n"
                "Click the button below to begin."
            ),
            colour=discord.Colour.blurple(),
        )

        if guild.icon is not None:
            embed.set_thumbnail(url=guild.icon.url)

        embed.set_footer(text="TFSBot Verification")

        await fetched_channel.send(
            embed=embed,
            view=VerifyView(),
        )

    def make_safe_command_key(command_key: str) -> str:
        return (
            command_key
            .replace(".", "__dot__")
            .replace("-", "__dash__")
            .replace(" ", "__space__")
        )

    def get_level_choices() -> list[dict[str, str]]:
        return [
            {"value": LEVEL_PUBLIC, "label": "Public"},
            {"value": LEVEL_STAFF, "label": "Staff"},
            {"value": LEVEL_ADMIN, "label": "Admin"},
            {"value": LEVEL_OWNER, "label": "Owner"},
        ]

    def format_file_size(size_bytes: int) -> str:
        if size_bytes < 1024:
            return f"{size_bytes} B"

        size = float(size_bytes)

        for suffix in ["KB", "MB", "GB", "TB"]:
            size /= 1024

            if size < 1024:
                return f"{size:.1f} {suffix}"

        return f"{size:.1f} PB"

    def get_database_path() -> Path | None:
        application_store = getattr(bot, "application_store", None)

        if application_store is None:
            return None

        raw_path = getattr(application_store, "database_path", None)

        if raw_path is None:
            return None

        return Path(raw_path)

    def format_datetime_text(value: str | None) -> str:
        if not value:
            return "Unknown"

        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            return value

        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)

        localish = parsed.astimezone()
        return localish.strftime("%d %b %Y %H:%M")

    def make_message_url(
        guild_id: int,
        channel_id: int | None,
        message_id: int | None,
    ) -> str | None:
        if channel_id is None or message_id is None:
            return None

        return f"https://discord.com/channels/{guild_id}/{channel_id}/{message_id}"

    def make_thread_url(
        guild_id: int,
        thread_id: int | None,
    ) -> str | None:
        if thread_id is None:
            return None

        return f"https://discord.com/channels/{guild_id}/{thread_id}"

    def get_user_display(user_id: int) -> str:
        user = bot.get_user(user_id)

        if user is not None:
            return f"{user} ({user_id})"

        return str(user_id)

    def get_channel_label(guild: discord.Guild, channel_id: int | None) -> str:
        if channel_id is None:
            return "Not set"

        channel = guild.get_channel(channel_id)

        if channel is None:
            return f"Unknown channel {channel_id}"

        return f"#{channel.name}"

    def get_role_label(guild: discord.Guild, role_id: int | None) -> str:
        if role_id is None:
            return "Not set"

        role = guild.get_role(role_id)

        if role is None:
            return f"Unknown role {role_id}"

        return role.name

    def get_status_class(status: str) -> str:
        cleaned = status.lower().strip()

        if cleaned in {"approved", "ready", "enabled", "set", "ok"}:
            return "good"

        if cleaned in {"pending", "questioning", "starting", "not set", "unknown"}:
            return "warn"

        if cleaned in {"rejected", "denied", "kicked", "banned", "left", "disabled", "missing"}:
            return "bad"

        return ""

    def display_status(status: str, questioning_thread_id: int | None = None) -> str:
        cleaned = status.lower().strip()

        if cleaned == "pending" and questioning_thread_id is not None:
            return "Questioning"

        return {
            "pending": "Pending",
            "approved": "Approved",
            "rejected": "Rejected",
            "denied": "Rejected",
            "kicked": "Kicked",
            "banned": "Banned",
            "left": "Left",
            "cancelled": "Cancelled",
        }.get(cleaned, status.title())

    def count_applications_for_overview(guild: discord.Guild) -> dict[str, Any]:
        database_path = get_database_path()

        empty_today = {
            "approved": 0,
            "rejected": 0,
            "kicked": 0,
            "banned": 0,
            "left": 0,
        }

        empty_counts = {
            "pending": 0,
            "approved": 0,
            "rejected": 0,
            "kicked": 0,
            "banned": 0,
            "left": 0,
            "cancelled": 0,
        }

        if database_path is None or not database_path.exists():
            return {
                "status_counts": empty_counts,
                "today": empty_today,
                "today_total": 0,
                "total_count": 0,
                "pending_count": 0,
                "questioning_count": 0,
                "pending_applications": [],
                "recent_outcomes": [],
            }

        today_key = datetime.now(timezone.utc).date().isoformat()

        try:
            with sqlite3.connect(database_path) as database:
                database.row_factory = sqlite3.Row

                status_rows = database.execute(
                    """
                    SELECT status, COUNT(*) AS total
                    FROM applications
                    WHERE guild_id = ?
                    GROUP BY status
                    """,
                    (guild.id,),
                ).fetchall()

                today_rows = database.execute(
                    """
                    SELECT status, COUNT(*) AS total
                    FROM applications
                    WHERE guild_id = ?
                    AND actioned_at IS NOT NULL
                    AND substr(actioned_at, 1, 10) = ?
                    GROUP BY status
                    """,
                    (guild.id, today_key),
                ).fetchall()

                total_row = database.execute(
                    """
                    SELECT COUNT(*) AS total
                    FROM applications
                    WHERE guild_id = ?
                    """,
                    (guild.id,),
                ).fetchone()

                questioning_row = database.execute(
                    """
                    SELECT COUNT(*) AS total
                    FROM applications
                    WHERE guild_id = ?
                    AND status = 'pending'
                    AND questioning_thread_id IS NOT NULL
                    """,
                    (guild.id,),
                ).fetchone()

                pending_rows = database.execute(
                    """
                    SELECT id, user_id, status, submitted_at, review_channel_id,
                           review_message_id, questioning_thread_id
                    FROM applications
                    WHERE guild_id = ?
                    AND status = 'pending'
                    ORDER BY submitted_at ASC
                    LIMIT 10
                    """,
                    (guild.id,),
                ).fetchall()

                outcome_rows = database.execute(
                    """
                    SELECT id, user_id, status, actioned_at, updated_at,
                           log_channel_id, log_message_id, questioning_thread_id
                    FROM applications
                    WHERE guild_id = ?
                    AND status != 'pending'
                    ORDER BY COALESCE(actioned_at, updated_at) DESC
                    LIMIT 10
                    """,
                    (guild.id,),
                ).fetchall()

        except sqlite3.Error:
            return {
                "status_counts": empty_counts,
                "today": empty_today,
                "today_total": 0,
                "total_count": 0,
                "pending_count": 0,
                "questioning_count": 0,
                "pending_applications": [],
                "recent_outcomes": [],
            }

        status_counts = dict(empty_counts)

        for row in status_rows:
            key = str(row["status"]).lower()
            if key == "denied":
                key = "rejected"
            status_counts[key] = int(row["total"])

        today = dict(empty_today)

        for row in today_rows:
            key = str(row["status"]).lower()
            if key == "denied":
                key = "rejected"
            if key in today:
                today[key] = int(row["total"])

        pending_applications = []

        for row in pending_rows:
            state = display_status(str(row["status"]), row["questioning_thread_id"])
            pending_applications.append(
                {
                    "id": row["id"],
                    "user": get_user_display(int(row["user_id"])),
                    "state": state,
                    "state_class": get_status_class(state),
                    "submitted_at": format_datetime_text(row["submitted_at"]),
                    "review_url": make_message_url(guild.id, row["review_channel_id"], row["review_message_id"]),
                    "thread_url": make_thread_url(guild.id, row["questioning_thread_id"]),
                }
            )

        recent_outcomes = []

        for row in outcome_rows:
            state = display_status(str(row["status"]), row["questioning_thread_id"])
            recent_outcomes.append(
                {
                    "id": row["id"],
                    "user": get_user_display(int(row["user_id"])),
                    "state": state,
                    "state_class": get_status_class(state),
                    "actioned_at": format_datetime_text(row["actioned_at"] or row["updated_at"]),
                    "log_url": make_message_url(guild.id, row["log_channel_id"], row["log_message_id"]),
                    "thread_url": make_thread_url(guild.id, row["questioning_thread_id"]),
                }
            )

        return {
            "status_counts": status_counts,
            "today": today,
            "today_total": sum(today.values()),
            "total_count": int(total_row["total"] if total_row else 0),
            "pending_count": status_counts.get("pending", 0),
            "questioning_count": int(questioning_row["total"] if questioning_row else 0),
            "pending_applications": pending_applications,
            "recent_outcomes": recent_outcomes,
        }

    def build_overview_context(guild: discord.Guild) -> dict[str, Any]:
        settings_store = get_guild_settings_store()
        app_stats = count_applications_for_overview(guild)

        review_channel_id = settings_store.get_review_channel_id(guild.id)
        log_channel_id = settings_store.get_application_log_channel_id(guild.id)
        add_role_id = settings_store.get_approved_add_role_id(guild.id)
        remove_role_id = settings_store.get_approved_remove_role_id(guild.id)
        automod_enabled = settings_store.is_automod_enabled(guild.id)
        automod_terms = settings_store.list_automod_terms(guild.id)
        verification_form_key = settings_store.get_verification_form_key(guild.id) or FORM_KEY_VERIFICATION
        database_path = get_database_path()
        database_size = database_path.stat().st_size if database_path and database_path.exists() else 0

        invite_ready = bool(getattr(bot, "invite_tracker_ready", False))

        health_items = [
            {
                "label": "Bot",
                "value": f"Online as {bot.user}" if bot.user else "Starting",
                "class": "good" if bot.user else "warn",
            },
            {
                "label": "Review channel",
                "value": get_channel_label(guild, review_channel_id),
                "class": "good" if review_channel_id else "warn",
            },
            {
                "label": "Log channel",
                "value": get_channel_label(guild, log_channel_id),
                "class": "good" if log_channel_id else "warn",
            },
            {
                "label": "Verification form",
                "value": verification_form_key,
                "class": "good" if verification_form_key else "warn",
            },
            {
                "label": "Give role on approval",
                "value": get_role_label(guild, add_role_id),
                "class": "good" if add_role_id else "warn",
            },
            {
                "label": "Remove role on approval",
                "value": get_role_label(guild, remove_role_id),
                "class": "good" if remove_role_id else "warn",
            },
            {
                "label": "Automod",
                "value": f"Enabled ({len(automod_terms)} terms)" if automod_enabled else f"Disabled ({len(automod_terms)} terms)",
                "class": "good" if automod_enabled else "warn",
            },
            {
                "label": "Invite tracking",
                "value": "Ready" if invite_ready else "Not synced",
                "class": "good" if invite_ready else "warn",
            },
            {
                "label": "Database",
                "value": format_file_size(database_size),
                "class": "good" if database_size else "warn",
            },
            {
                "label": "Server members",
                "value": str(guild.member_count or "Unknown"),
                "class": "",
            },
        ]

        ignored_warning_labels = {
            "Automod",
            "Server members",
        }

        warning_items = [
            item
            for item in health_items
            if item.get("class") in {"bad", "warn"}
            and item.get("label") not in ignored_warning_labels
        ]

        app_stats["health_items"] = health_items
        app_stats["warning_items"] = warning_items
        app_stats["warning_count"] = len(warning_items)

        return app_stats

    @app.route("/uploads/<path:filename>")
    def uploaded_image(filename: str):
        if not is_logged_in():
            return redirect(url_for("login"))

        return send_from_directory(UPLOAD_DIR, filename)

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "GET":
            return render_login_page(error=None)

        if not is_password_login_enabled():
            return render_login_page(error="Emergency username/password login is disabled.")

        username = request.form.get("username", "")
        password = request.form.get("password", "")

        login_ok = any(
            hmac.compare_digest(username, credential.username)
            and hmac.compare_digest(password, credential.password)
            for credential in bot.config.webui_credentials
        )

        if not login_ok:
            return render_login_page(error="Incorrect username or password.")

        session.clear()
        session["logged_in"] = True
        session["auth_method"] = "password"
        session["username"] = username
        session["display_name"] = username
        session["webui_role"] = "owner"

        return redirect(url_for("index"))

    @app.route("/auth/discord/start")
    def discord_login_start():
        if not is_discord_login_enabled():
            return render_login_page(error="Discord login is not enabled.")

        state = secrets.token_urlsafe(32)
        session["discord_oauth_state"] = state

        return redirect(get_discord_authorisation_url(state=state))

    @app.route("/auth/discord/callback")
    def discord_login_callback():
        if not is_discord_login_enabled():
            return render_login_page(error="Discord login is not enabled.")

        oauth_error = request.args.get("error")

        if oauth_error:
            return render_login_page(error=f"Discord login failed: {oauth_error}")

        code = request.args.get("code", "")
        state = request.args.get("state", "")
        expected_state = session.pop("discord_oauth_state", "")

        if not code:
            return render_login_page(error="Discord did not return an authorisation code.")

        if not hmac.compare_digest(state, expected_state):
            return render_login_page(error="Discord login state mismatch. Try again.")

        try:
            access_token = exchange_discord_code_for_token(code=code)
            user_data = fetch_discord_user(access_token=access_token)
            member_data = fetch_discord_member(access_token=access_token)

            webui_role = get_matching_discord_webui_role(member_data)

            if webui_role is None:
                return render_login_page(
                    error="Your Discord account does not have an allowed WebUI role."
                )

            username = str(user_data.get("username") or "Discord user")
            global_name = str(user_data.get("global_name") or "").strip()
            user_id = str(user_data.get("id") or "")

            display_name = global_name or username

            session.clear()
            session["logged_in"] = True
            session["auth_method"] = "discord"
            session["discord_user_id"] = user_id
            session["discord_username"] = username
            session["display_name"] = display_name
            session["webui_role"] = webui_role

            return redirect(url_for("index"))

        except Exception as error:
            return render_login_page(error=str(error))

    @app.route("/logout")
    def logout():
        session.clear()
        return redirect(url_for("login"))

    @app.route("/")
    def index():
        if not is_logged_in():
            return redirect(url_for("login"))

        selected_guild = get_selected_guild(request.args.get("guild_id"))

        overview = None
        error = None

        try:
            if selected_guild is not None:
                overview = build_overview_context(selected_guild)

        except Exception as caught_error:
            error = str(caught_error)

        return render_admin_page(
            title="TFSBot Overview",
            active_page="overview",
            body_template=OVERVIEW_BODY_HTML,
            guilds=get_available_guilds(),
            selected_guild_id=str(selected_guild.id) if selected_guild else None,
            overview=overview,
            error=error,
        )
    

    @app.route("/backups", methods=["GET", "POST"])
    def backups_page():
        owner_error = require_owner_page()

        if owner_error is not None:
            return owner_error

        message: str | None = None
        error: str | None = None
        restore_completed = False

        database_path = get_database_path() or Path("data/tfsbot.sqlite3")
        uploads_path = Path("data/uploads")

        if request.method == "POST":
            try:
                action = request.form.get("action", "")

                backup_service = BackupService(
                    project_root=Path("."),
                    database_path=database_path,
                )

                if action == "create_backup":
                    password = request.form.get("password", "")
                    confirm_password = request.form.get("confirm_password", "")

                    if password != confirm_password:
                        raise RuntimeError("Backup passwords do not match.")

                    include_env = request.form.get("include_env") == "1"

                    backup = backup_service.create_encrypted_backup(
                        password=password,
                        include_env=include_env,
                    )

                    return send_file(
                        BytesIO(backup.data),
                        as_attachment=True,
                        download_name=backup.filename,
                        mimetype="application/octet-stream",
                    )

                if action == "restore_backup":
                    restore_confirm = request.form.get("restore_confirm", "").strip()

                    if restore_confirm != "RESTORE":
                        raise RuntimeError("Type RESTORE to confirm backup restoration.")

                    uploaded_file = request.files.get("backup_file")

                    if uploaded_file is None or uploaded_file.filename == "":
                        raise RuntimeError("No backup file was uploaded.")

                    if not uploaded_file.filename.endswith(".tfsbackup"):
                        raise RuntimeError("Backup file must use the .tfsbackup extension.")

                    restore_password = request.form.get("restore_password", "")

                    restore_result = backup_service.restore_encrypted_backup(
                        encrypted_data=uploaded_file.read(),
                        password=restore_password,
                        restore_uploads=request.form.get("restore_uploads") == "1",
                        restore_env=request.form.get("restore_env") == "1",
                    )

                    restored_bits: list[str] = []

                    if restore_result.restored_database:
                        restored_bits.append("database")

                    if restore_result.restored_uploads:
                        restored_bits.append("uploads")

                    if restore_result.restored_env:
                        restored_bits.append(".env")

                    restored_text = ", ".join(restored_bits) or "nothing"

                    restore_completed = True

                    message = (
                        f"Restored {restored_text}. "
                        f"Safety copy created at {restore_result.safety_backup_directory}. "
                        "Restart the bot now. Do not keep using the WebUI until the bot has restarted."
                    )

                else:
                    raise RuntimeError("Unknown backup action.")

            except BackupError as caught_error:
                error = str(caught_error)

            except Exception as caught_error:
                error = str(caught_error)

        database_size = (
            format_file_size(database_path.stat().st_size)
            if database_path.exists()
            else "Missing"
        )

        uploads_state = "Present" if uploads_path.exists() else "Not created yet"

        return render_admin_page(
            title="TFSBot Backups",
            active_page="backups",
            body_template=BACKUPS_BODY_HTML,
            database_path=str(database_path),
            database_size=database_size,
            uploads_state=uploads_state,
            restore_completed=restore_completed,
            message=message,
            error=error,
        )


    @app.route("/uploads-manager", methods=["GET", "POST"])
    def uploads_manager_page():
        owner_error = require_owner_page()

        if owner_error is not None:
            return owner_error

        message: str | None = None
        error: str | None = None
        selected_folder = ""

        try:
            if request.method == "POST":
                action = request.form.get("action", "")

                if action == "create_folder":
                    folder = validate_upload_folder(request.form.get("folder"))
                    folder_path = get_upload_folder_path(folder)
                    folder_path.mkdir(parents=True, exist_ok=True)
                    message = f"Created folder {folder}."

                elif action == "upload_file":
                    uploaded_file = request.files.get("image")

                    if uploaded_file is None or not uploaded_file.filename:
                        raise ValueError("No image selected.")

                    folder = request.form.get("new_folder") or request.form.get("folder") or ""
                    selected_folder = validate_upload_folder(folder)
                    folder_path = get_upload_folder_path(selected_folder)
                    folder_path.mkdir(parents=True, exist_ok=True)

                    safe_name = validate_uploaded_image_filename(uploaded_file.filename)
                    destination = folder_path / safe_name

                    if destination.exists():
                        stem = destination.stem
                        suffix = destination.suffix
                        counter = 1

                        while destination.exists():
                            destination = folder_path / f"{stem}_{counter}{suffix}"
                            counter += 1

                    uploaded_file.save(destination)
                    message = f"Uploaded {destination.relative_to(UPLOAD_DIR).as_posix()}."

                elif action == "delete_file":
                    reference = validate_uploaded_image_reference(
                        request.form.get("file_reference", "")
                    )
                    path = get_uploaded_image_path(reference)

                    if not path.exists():
                        raise FileNotFoundError(f"Uploaded image not found: {reference}")

                    path.unlink()
                    message = f"Deleted {reference}."

                elif action == "delete_folder":
                    confirm = request.form.get("confirm", "").strip()

                    if confirm != "DELETE":
                        raise RuntimeError("Type DELETE to confirm folder deletion.")

                    folder = validate_upload_folder(request.form.get("folder"))
                    folder_path = get_upload_folder_path(folder)

                    if folder_path == UPLOAD_DIR:
                        raise RuntimeError("Cannot delete the root uploads folder.")

                    if not folder_path.exists():
                        raise FileNotFoundError(f"Folder not found: {folder}")

                    if any(folder_path.iterdir()):
                        raise RuntimeError("Folder is not empty.")

                    folder_path.rmdir()
                    message = f"Deleted folder {folder}."

                else:
                    raise RuntimeError("Unknown uploads action.")

        except Exception as caught_error:
            error = str(caught_error)

        return render_admin_page(
            title="TFSBot Uploads",
            active_page="uploads",
            body_template=UPLOADS_MANAGER_BODY_HTML,
            folders=list_upload_folders(),
            uploaded_images=list_uploaded_images(),
            selected_folder=selected_folder,
            message=message,
            error=error,
        )


    @app.route("/embed-builder")
    def embed_builder():
        owner_error = require_owner_page()

        if owner_error is not None:
            return owner_error

        return render_embed_builder_page(
            message=None,
            error=None,
        )


    @app.route("/dm-templates", methods=["GET", "POST"])
    def dm_templates():
        owner_error = require_owner_page()

        if owner_error is not None:
            return owner_error

        message: str | None = None
        error: str | None = None

        selected_guild = get_selected_guild(
            request.form.get("guild_id") if request.method == "POST" else request.args.get("guild_id")
        )

        try:
            template_store = get_template_store()

            if request.method == "POST":
                if selected_guild is None:
                    raise RuntimeError("No server selected.")

                for template_key in DM_TEMPLATE_ORDER:
                    template_text = request.form.get(f"template_{template_key}", "").strip()

                    if template_text == DEFAULT_DM_TEMPLATES[template_key]:
                        run_coro_from_flask(
                            template_store.reset_template(
                                guild_id=selected_guild.id,
                                template_key=template_key,
                            )
                        )
                    else:
                        run_coro_from_flask(
                            template_store.set_template(
                                guild_id=selected_guild.id,
                                template_key=template_key,
                                template_text=template_text,
                            )
                        )

                message = "DM templates saved."

            templates = []

            if selected_guild is not None:
                stored_templates = run_coro_from_flask(
                    template_store.get_all_templates(selected_guild.id)
                )

                for stored_template in stored_templates:
                    templates.append(
                        {
                            "key": stored_template.template_key,
                            "label": DM_TEMPLATE_LABELS[stored_template.template_key],
                            "text": stored_template.template_text,
                            "default": DEFAULT_DM_TEMPLATES[stored_template.template_key],
                            "is_custom": stored_template.is_custom,
                        }
                    )

            return render_admin_page(
                title="TFSBot DM Templates",
                active_page="dm_templates",
                body_template=DM_TEMPLATES_BODY_HTML,
                guilds=get_available_guilds(),
                selected_guild_id=str(selected_guild.id) if selected_guild else None,
                templates=templates,
                message=message,
                error=error,
            )

        except Exception as caught_error:
            error = str(caught_error)

            return render_admin_page(
                title="TFSBot DM Templates",
                active_page="dm_templates",
                body_template=DM_TEMPLATES_BODY_HTML,
                guilds=get_available_guilds(),
                selected_guild_id=str(selected_guild.id) if selected_guild else None,
                templates=[],
                message=message,
                error=error,
            )

    @app.route("/forms", methods=["GET", "POST"])
    def forms_page():
        owner_error = require_owner_page()

        if owner_error is not None:
            return owner_error

        message: str | None = None
        error: str | None = None

        selected_guild = get_selected_guild(
            request.form.get("guild_id") if request.method == "POST" else request.args.get("guild_id")
        )

        selected_form_key = clean_form_key(
            request.form.get("form_key") if request.method == "POST" else request.args.get("form_key", "")
        )

        try:
            form_store = get_form_store()
            settings_store = get_guild_settings_store()

            if request.method == "POST":
                if selected_guild is None:
                    raise RuntimeError("No server selected.")

                action = request.form.get("action", "")

                if action == "create_form":
                    new_form_key = clean_form_key(request.form.get("new_form_key", ""))
                    new_title = request.form.get("new_form_title", "").strip()
                    new_prefix = request.form.get("new_custom_id_prefix", "").strip() or None

                    run_coro_from_flask(
                        form_store.create_form(
                            guild_id=selected_guild.id,
                            form_key=new_form_key,
                            title=new_title,
                            custom_id_prefix=new_prefix,
                        )
                    )

                    selected_form_key = new_form_key
                    message = f"Created form `{new_form_key}`."

                elif action == "save_form":
                    if not selected_form_key:
                        raise RuntimeError("No form selected.")

                    updated = run_coro_from_flask(
                        form_store.update_form(
                            guild_id=selected_guild.id,
                            form_key=selected_form_key,
                            title=request.form.get("form_title", ""),
                            custom_id_prefix=request.form.get("custom_id_prefix", ""),
                        )
                    )

                    if not updated:
                        raise RuntimeError("Form was not found.")

                    message = f"Saved form `{selected_form_key}`."

                elif action == "set_verification_form":
                    if not selected_form_key:
                        raise RuntimeError("No form selected.")

                    run_coro_from_flask(
                        form_store.get_form_config(
                            guild_id=selected_guild.id,
                            form_key=selected_form_key,
                            fallback_json_path=VERIFICATION_FORM_PATH,
                        )
                    )

                    settings_store.set_verification_form_key(
                        selected_guild.id,
                        selected_form_key,
                    )

                    message = f"Verification form changed to `{selected_form_key}`. Repost the verification panel if needed."

                elif action == "reset_verification_form":
                    if request.form.get("reset_confirm", "").strip() != "RESET":
                        raise RuntimeError("Type RESET to reset the built-in verification form.")

                    run_coro_from_flask(
                        form_store.reset_verification_form_from_json(
                            guild_id=selected_guild.id,
                            json_path=VERIFICATION_FORM_PATH,
                        )
                    )

                    selected_form_key = FORM_KEY_VERIFICATION
                    message = "Built-in verification form reset."

                elif action == "add_question":
                    if not selected_form_key:
                        raise RuntimeError("No form selected.")

                    run_coro_from_flask(
                        form_store.add_question(
                            guild_id=selected_guild.id,
                            form_key=selected_form_key,
                            question_key=clean_form_key(request.form.get("question_key", "")),
                            label=request.form.get("question_label", "").strip(),
                            style=request.form.get("question_style", "paragraph"),
                            required=request.form.get("question_required") == "on",
                            placeholder=request.form.get("question_placeholder", "").strip() or None,
                            min_length=parse_optional_int(request.form.get("question_min_length")),
                            max_length=parse_optional_int(request.form.get("question_max_length")),
                            fallback_json_path=VERIFICATION_FORM_PATH,
                        )
                    )

                    message = "Question added."

                elif action == "save_questions":
                    if not selected_form_key:
                        raise RuntimeError("No form selected.")

                    ordered_keys: list[tuple[int, str]] = []

                    for question_key in request.form.getlist("question_key[]"):
                        question_key = clean_form_key(question_key)

                        run_coro_from_flask(
                            form_store.update_question(
                                guild_id=selected_guild.id,
                                form_key=selected_form_key,
                                question_key=question_key,
                                label=request.form.get(f"label_{question_key}", "").strip(),
                                style=request.form.get(f"style_{question_key}", "paragraph"),
                                required=request.form.get(f"required_{question_key}") == "on",
                                placeholder=request.form.get(f"placeholder_{question_key}", "").strip() or None,
                                min_length=parse_optional_int(request.form.get(f"min_length_{question_key}")),
                                max_length=parse_optional_int(request.form.get(f"max_length_{question_key}")),
                                clear_placeholder=True,
                                clear_lengths=True,
                                fallback_json_path=VERIFICATION_FORM_PATH,
                            )
                        )

                        ordered_keys.append(
                            (
                                parse_optional_int(request.form.get(f"sort_order_{question_key}")) or 9999,
                                question_key,
                            )
                        )

                    run_coro_from_flask(
                        form_store.set_question_order(
                            guild_id=selected_guild.id,
                            form_key=selected_form_key,
                            question_keys=[
                                question_key
                                for _, question_key in sorted(ordered_keys)
                            ],
                        )
                    )

                    message = "Question changes saved."

                elif action == "delete_question":
                    if request.form.get("delete_question_confirm", "").strip() != "DELETE":
                        raise RuntimeError("Type DELETE to delete the question.")

                    question_key = clean_form_key(request.form.get("delete_question_key", ""))

                    deleted = run_coro_from_flask(
                        form_store.delete_question(
                            guild_id=selected_guild.id,
                            form_key=selected_form_key,
                            question_key=question_key,
                            fallback_json_path=VERIFICATION_FORM_PATH,
                        )
                    )

                    if not deleted:
                        raise RuntimeError("Question was not found.")

                    message = f"Deleted question `{question_key}`."

                elif action == "publish_form":
                    if not selected_form_key:
                        raise RuntimeError("No form selected.")

                    channel_id = int(request.form.get("publish_channel_id", "0"))
                    channel = selected_guild.get_channel(channel_id)

                    if channel is None:
                        channel = run_coro_from_flask(bot.fetch_channel(channel_id))

                    if not isinstance(channel, discord.TextChannel):
                        raise RuntimeError("Selected channel is not a text channel.")

                    form_config = run_coro_from_flask(
                        form_store.get_form_config(
                            guild_id=selected_guild.id,
                            form_key=selected_form_key,
                            fallback_json_path=VERIFICATION_FORM_PATH,
                        )
                    )

                    if not form_config.questions:
                        raise RuntimeError("Add at least one question before publishing this form.")

                    publish_title = request.form.get("publish_title", "").strip()
                    publish_description = request.form.get("publish_description", "").strip()

                    if not publish_title or not publish_description:
                        raise RuntimeError("Publish title and description are required.")

                    embed = discord.Embed(
                        title=publish_title,
                        description=publish_description,
                        colour=discord.Colour.blurple(),
                    )

                    if selected_guild.icon is not None:
                        embed.set_thumbnail(url=selected_guild.icon.url)

                    embed.set_footer(text=f"Form: {form_config.title}")

                    message_object = run_coro_from_flask(
                        channel.send(
                            embed=embed,
                            view=GenericFormStartView(),
                        )
                    )

                    run_coro_from_flask(
                        form_store.save_published_form(
                            guild_id=selected_guild.id,
                            form_key=selected_form_key,
                            channel_id=channel.id,
                            message_id=message_object.id,
                            title=publish_title,
                            description=publish_description,
                        )
                    )

                    message = f"Published form `{selected_form_key}` in #{channel.name}."

                elif action == "delete_form":
                    if request.form.get("delete_form_confirm", "").strip() != "DELETE":
                        raise RuntimeError("Type DELETE to delete the form.")

                    verification_form_key = settings_store.get_verification_form_key(selected_guild.id) or FORM_KEY_VERIFICATION

                    if selected_form_key == verification_form_key:
                        raise RuntimeError("Choose another verification form before deleting this one.")

                    deleted = run_coro_from_flask(
                        form_store.delete_form(
                            guild_id=selected_guild.id,
                            form_key=selected_form_key,
                        )
                    )

                    if not deleted:
                        raise RuntimeError("Form was not found.")

                    message = f"Deleted form `{selected_form_key}`."
                    selected_form_key = ""

                else:
                    raise RuntimeError("Unknown forms action.")

            forms: list[dict[str, str]] = []
            text_channels: list[dict[str, str]] = []
            selected_form = None
            questions = []
            verification_form_key = FORM_KEY_VERIFICATION
            modal_pages = 0

            if selected_guild is not None:
                text_channels = get_guild_text_channels(selected_guild)
                forms = run_coro_from_flask(get_guild_forms(selected_guild))
                verification_form_key = settings_store.get_verification_form_key(selected_guild.id) or FORM_KEY_VERIFICATION

                if not selected_form_key:
                    selected_form_key = verification_form_key

                if forms and not any(form["key"] == selected_form_key for form in forms):
                    selected_form_key = forms[0]["key"]

                if selected_form_key:
                    selected_form = run_coro_from_flask(
                        form_store.get_form_config(
                            guild_id=selected_guild.id,
                            form_key=selected_form_key,
                            fallback_json_path=VERIFICATION_FORM_PATH,
                        )
                    )

                    questions = run_coro_from_flask(
                        form_store.list_questions(
                            guild_id=selected_guild.id,
                            form_key=selected_form_key,
                            fallback_json_path=VERIFICATION_FORM_PATH,
                        )
                    )

                    modal_pages = len(selected_form.pages()) if selected_form is not None else 0

                    forms = run_coro_from_flask(get_guild_forms(selected_guild))

            return render_admin_page(
                title="TFSBot Forms",
                active_page="forms",
                body_template=FORMS_BODY_HTML,
                guilds=get_available_guilds(),
                selected_guild_id=str(selected_guild.id) if selected_guild else None,
                forms=forms,
                selected_form_key=selected_form_key,
                selected_form=selected_form,
                questions=questions,
                text_channels=text_channels,
                verification_form_key=verification_form_key,
                modal_pages=modal_pages,
                message=message,
                error=error,
            )

        except Exception as caught_error:
            error = str(caught_error)

            return render_admin_page(
                title="TFSBot Forms",
                active_page="forms",
                body_template=FORMS_BODY_HTML,
                guilds=get_available_guilds(),
                selected_guild_id=str(selected_guild.id) if selected_guild else None,
                forms=[],
                selected_form_key=selected_form_key,
                selected_form=None,
                questions=[],
                text_channels=[],
                verification_form_key=FORM_KEY_VERIFICATION,
                modal_pages=0,
                message=message,
                error=error,
            )

    @app.route("/forms/view", methods=["GET"])
    def forms_viewer_page():
        owner_error = require_owner_page()

        if owner_error is not None:
            return owner_error

        selected_guild = get_selected_guild(request.args.get("guild_id"))
        selected_form_key = clean_form_key(request.args.get("form_key", ""))
        error: str | None = None

        try:
            if selected_guild is None:
                raise RuntimeError("No server selected.")

            if not selected_form_key:
                raise RuntimeError("No form selected.")

            form_store = get_form_store()
            form_config = run_coro_from_flask(
                form_store.get_form_config(
                    guild_id=selected_guild.id,
                    form_key=selected_form_key,
                    fallback_json_path=VERIFICATION_FORM_PATH,
                )
            )

            pages: list[dict[str, Any]] = []

            for page_index, page_questions in enumerate(form_config.pages(), start=1):
                page_rows: list[dict[str, Any]] = []

                for question_index, question in enumerate(page_questions, start=1):
                    min_text = str(question.min_length) if question.min_length is not None else "No min"
                    max_text = str(question.max_length) if question.max_length is not None else "No max"

                    page_rows.append(
                        {
                            "number": question_index,
                            "key": question.key,
                            "label": question.label,
                            "style": "Short answer" if question.style == discord.TextStyle.short else "Paragraph",
                            "required": question.required,
                            "placeholder": question.placeholder,
                            "limits": f"{min_text} / {max_text}",
                        }
                    )

                pages.append(
                    {
                        "number": page_index,
                        "questions": page_rows,
                    }
                )

            return render_admin_page(
                title="TFSBot Form Viewer",
                active_page="forms",
                body_template=FORM_VIEWER_BODY_HTML,
                selected_guild_id=str(selected_guild.id),
                form_key=selected_form_key,
                form_title=form_config.title,
                custom_id_prefix=form_config.custom_id_prefix,
                question_count=len(form_config.questions),
                page_count=len(pages),
                pages=pages,
                message=None,
                error=None,
            )

        except Exception as caught_error:
            error = str(caught_error)

            return render_admin_page(
                title="TFSBot Form Viewer",
                active_page="forms",
                body_template=FORM_VIEWER_BODY_HTML,
                selected_guild_id=str(selected_guild.id) if selected_guild else "",
                form_key=selected_form_key,
                form_title="Unknown",
                custom_id_prefix="Unknown",
                question_count=0,
                page_count=0,
                pages=[],
                message=None,
                error=error,
            )


    @app.route("/verification", methods=["GET", "POST"])
    def verification_page():
        owner_error = require_owner_page()

        if owner_error is not None:
            return owner_error

        message: str | None = None
        error: str | None = None

        selected_guild = get_selected_guild(
            request.form.get("guild_id") if request.method == "POST" else request.args.get("guild_id")
        )

        try:
            settings_store = get_guild_settings_store()

            if request.method == "POST":
                if selected_guild is None:
                    raise RuntimeError("No server selected.")

                action = request.form.get("action", "save_verification")

                if action in {"cancel_by_user", "cancel_all_pending"}:
                    if bot.user is None:
                        raise RuntimeError("Bot user is not available yet.")

                    if request.form.get("cancel_confirm", "").strip() != "CANCEL":
                        raise RuntimeError("Type CANCEL in the confirmation field to cancel applications.")

                    cancellation_reason = request.form.get("cancel_reason", "").strip()

                    if not cancellation_reason:
                        cancellation_reason = "Manually cancelled from the WebUI."

                    if action == "cancel_by_user":
                        user_id_text = request.form.get("cancel_user_id", "").strip()

                        if not user_id_text:
                            raise RuntimeError("Enter a user ID to cancel by user.")

                        try:
                            user_id = int(user_id_text)
                        except ValueError as error:
                            raise RuntimeError("User ID must be a number.") from error

                        result = run_coro_from_flask(
                            cancel_pending_application_by_user_id(
                                client=bot,
                                guild_id=selected_guild.id,
                                user_id=user_id,
                                moderator=bot.user,
                                reason=cancellation_reason,
                            )
                        )

                    else:
                        result = run_coro_from_flask(
                            cancel_all_pending_applications_for_guild(
                                client=bot,
                                guild_id=selected_guild.id,
                                moderator=bot.user,
                                reason=cancellation_reason,
                            )
                        )

                    message = result.detail

                elif action == "refresh_invites":
                    refreshed = run_coro_from_flask(
                        get_invite_tracker_store().sync_guild_invites(selected_guild)
                    )

                    message = "Invite cache refreshed." if refreshed else "Could not refresh invites. Check the bot has Manage Server."

                else:
                    review_channel_id = request.form.get("review_channel_id", "").strip()
                    log_channel_id = request.form.get("log_channel_id", "").strip()
                    verification_form_key = request.form.get("verification_form_key", FORM_KEY_VERIFICATION).strip() or FORM_KEY_VERIFICATION
                    approved_add_role_id = request.form.get("approved_add_role_id", "").strip()
                    approved_remove_role_id = request.form.get("approved_remove_role_id", "").strip()

                    if review_channel_id:
                        settings_store.set_review_channel_id(selected_guild.id, int(review_channel_id))

                    if log_channel_id:
                        settings_store.set_application_log_channel_id(selected_guild.id, int(log_channel_id))

                    settings_store.set_verification_form_key(selected_guild.id, verification_form_key)

                    if approved_add_role_id:
                        settings_store.set_approved_add_role_id(selected_guild.id, int(approved_add_role_id))
                    else:
                        settings_store.clear_approved_add_role_id(selected_guild.id)

                    if approved_remove_role_id:
                        settings_store.set_approved_remove_role_id(selected_guild.id, int(approved_remove_role_id))
                    else:
                        settings_store.clear_approved_remove_role_id(selected_guild.id)

                    settings_store.set_automod_enabled(
                        selected_guild.id,
                        request.form.get("automod_enabled") == "on",
                    )

                    if action == "clear_automod_terms":
                        settings_store.clear_automod_terms(selected_guild.id)
                        message = "Verification settings saved and automod terms cleared."

                    else:
                        terms = parse_terms_from_text(request.form.get("automod_terms", ""))
                        settings_store.set_automod_terms(selected_guild.id, terms)

                        if action == "add_default_terms":
                            added_count = settings_store.add_default_automod_terms(selected_guild.id)
                            message = f"Verification settings saved. Added {added_count} default automod term(s)."
                        else:
                            message = "Verification settings saved."

                    if action == "save_and_post_panel":
                        panel_channel_id = request.form.get("panel_channel_id", "").strip()

                        if not panel_channel_id:
                            raise RuntimeError("Choose a panel channel before posting the verification panel.")

                        run_coro_from_flask(
                            post_verification_panel_from_webui(
                                guild=selected_guild,
                                channel_id=int(panel_channel_id),
                                form_key=verification_form_key,
                            )
                        )

                        message = "Verification settings saved and panel posted."

            roles: list[dict[str, str]] = []
            text_channels: list[dict[str, str]] = []
            forms: list[dict[str, str]] = []
            settings: dict[str, str | bool] = {}
            automod_terms_text = ""
            default_terms: list[str] = []

            if selected_guild is not None:
                roles = get_guild_roles(selected_guild)
                text_channels = get_guild_text_channels(selected_guild)
                forms = run_coro_from_flask(get_guild_forms(selected_guild))
                settings = get_current_verification_settings(selected_guild)
                automod_terms_text = "\n".join(settings_store.list_automod_terms(selected_guild.id))
                default_terms = settings_store.get_default_automod_terms()

            invite_tracking_status = "Ready" if getattr(bot, "invite_tracker_ready", False) else "Starting / not synced yet"

            return render_admin_page(
                title="TFSBot Verification",
                active_page="verification",
                body_template=VERIFICATION_BODY_HTML,
                guilds=get_available_guilds(),
                selected_guild_id=str(selected_guild.id) if selected_guild else None,
                roles=roles,
                text_channels=text_channels,
                forms=forms,
                settings=settings,
                automod_terms_text=automod_terms_text,
                default_terms=default_terms,
                default_terms_text="\n".join(default_terms),
                invite_tracking_status=invite_tracking_status,
                message=message,
                error=error,
            )

        except Exception as caught_error:
            error = str(caught_error)

            return render_admin_page(
                title="TFSBot Verification",
                active_page="verification",
                body_template=VERIFICATION_BODY_HTML,
                guilds=get_available_guilds(),
                selected_guild_id=str(selected_guild.id) if selected_guild else None,
                roles=[],
                text_channels=[],
                forms=[],
                settings={},
                automod_terms_text="",
                default_terms=[],
                default_terms_text="",
                invite_tracking_status="Unknown",
                message=message,
                error=error,
            )

    @app.route("/permissions", methods=["GET", "POST"])
    def permissions_page():
        owner_error = require_owner_page()

        if owner_error is not None:
            return owner_error

        message: str | None = None
        error: str | None = None

        selected_guild = get_selected_guild(
            request.form.get("guild_id") if request.method == "POST" else request.args.get("guild_id")
        )

        try:
            permission_store = get_permission_store()

            if request.method == "POST":
                if selected_guild is None:
                    raise RuntimeError("No server selected.")

                webui_owner_role_ids = parse_role_ids_from_form("webui_owner_role_ids")
                webui_viewer_role_ids = parse_role_ids_from_form("webui_viewer_role_ids")

                if not webui_owner_role_ids and not get_env_webui_owner_role_ids():
                    raise RuntimeError(
                        "Choose at least one WebUI owner role, or set WEBUI_DISCORD_OWNER_ROLE_IDS in .env before clearing this."
                    )

                set_stored_webui_access_role_ids(
                    guild_id=selected_guild.id,
                    access_level="owner",
                    role_ids=webui_owner_role_ids,
                )
                set_stored_webui_access_role_ids(
                    guild_id=selected_guild.id,
                    access_level="viewer",
                    role_ids=webui_viewer_role_ids,
                )

                for level in [LEVEL_STAFF, LEVEL_ADMIN, LEVEL_OWNER]:
                    role_id_text = request.form.get(f"role_{level}", "").strip()

                    if role_id_text:
                        run_coro_from_flask(
                            permission_store.set_role(
                                guild_id=selected_guild.id,
                                level=level,
                                role_id=int(role_id_text),
                            )
                        )
                    else:
                        run_coro_from_flask(
                            permission_store.clear_role(
                                guild_id=selected_guild.id,
                                level=level,
                            )
                        )

                for command_key in request.form.getlist("command_key[]"):
                    safe_key = make_safe_command_key(command_key)
                    level = request.form.get(f"command_level_{safe_key}", LEVEL_PUBLIC)

                    run_coro_from_flask(
                        permission_store.set_command_level(
                            guild_id=selected_guild.id,
                            command_key=command_key,
                            level=level,
                        )
                    )

                message = "Permissions and WebUI access saved."

            role_settings = []
            commands = []
            roles = []

            if selected_guild is not None:
                roles = get_guild_roles(selected_guild)
                role_ids = run_coro_from_flask(permission_store.get_role_ids(selected_guild.id))

                role_settings = [
                    {"level": LEVEL_STAFF, "label": "Staff role", "role_id": str(role_ids.get(LEVEL_STAFF) or "")},
                    {"level": LEVEL_ADMIN, "label": "Admin role", "role_id": str(role_ids.get(LEVEL_ADMIN) or "")},
                    {"level": LEVEL_OWNER, "label": "Owner role", "role_id": str(role_ids.get(LEVEL_OWNER) or "")},
                ]

                command_levels = run_coro_from_flask(
                    permission_store.get_all_command_levels(selected_guild.id)
                )

                commands = [
                    {
                        "key": command_key,
                        "safe_key": make_safe_command_key(command_key),
                        "level": level,
                    }
                    for command_key, level in sorted(command_levels.items())
                ]

            return render_admin_page(
                title="TFSBot Permissions",
                active_page="permissions",
                body_template=PERMISSIONS_BODY_HTML,
                guilds=get_available_guilds(),
                selected_guild_id=str(selected_guild.id) if selected_guild else None,
                roles=roles,
                role_settings=role_settings,
                commands=commands,
                levels=get_level_choices(),
                webui_access=build_webui_access_context(selected_guild),
                message=message,
                error=error,
            )

        except Exception as caught_error:
            error = str(caught_error)

            return render_admin_page(
                title="TFSBot Permissions",
                active_page="permissions",
                body_template=PERMISSIONS_BODY_HTML,
                guilds=get_available_guilds(),
                selected_guild_id=str(selected_guild.id) if selected_guild else None,
                roles=[],
                role_settings=[],
                commands=[],
                levels=get_level_choices(),
                webui_access=build_webui_access_context(selected_guild),
                message=message,
                error=error,
            )

    @app.route("/upload", methods=["POST"])
    def upload_image():
        owner_error = require_owner_page()

        if owner_error is not None:
            return owner_error

        try:
            uploaded_file = request.files.get("image")

            if uploaded_file is None or not uploaded_file.filename:
                raise ValueError("No image selected.")

            folder = request.form.get("new_folder") or request.form.get("folder") or ""
            folder_path = get_upload_folder_path(folder)
            folder_path.mkdir(parents=True, exist_ok=True)

            safe_name = validate_uploaded_image_filename(uploaded_file.filename)
            destination = folder_path / safe_name

            if destination.exists():
                stem = destination.stem
                suffix = destination.suffix
                counter = 1

                while destination.exists():
                    destination = folder_path / f"{stem}_{counter}{suffix}"
                    counter += 1

            uploaded_file.save(destination)

            return render_embed_builder_page(
                message=f"Uploaded {destination.relative_to(UPLOAD_DIR).as_posix()}.",
                error=None,
            )

        except Exception as error:
            return render_embed_builder_page(
                message=None,
                error=str(error),
            )

    @app.route("/send", methods=["POST"])
    def send_embed():
        owner_error = require_owner_page()

        if owner_error is not None:
            return owner_error

        try:
            channel_id = int(request.form["channel_id"])

            field_ids = request.form.getlist("field_id[]")

            fields: list[tuple[str, str, bool]] = []

            for field_id in field_ids:
                name = request.form.get(f"field_{field_id}_name", "")
                value = request.form.get(f"field_{field_id}_value", "")
                inline = request.form.get(f"field_{field_id}_inline") == "on"

                if name.strip() and value.strip():
                    fields.append((name, value, inline))

            image_attachment_url, thumbnail_attachment_url, author_icon_attachment_url, files = build_selected_attachment_files(
                image_upload_filename=request.form.get("image_upload_filename") or None,
                thumbnail_upload_filename=request.form.get("thumbnail_upload_filename") or None,
                author_icon_upload_filename=request.form.get("author_icon_upload_filename") or None,
            )

            image_url = image_attachment_url or request.form.get("image_url") or None
            thumbnail_url = thumbnail_attachment_url or request.form.get("thumbnail_url") or None
            author_icon_url = author_icon_attachment_url or request.form.get("author_icon_url") or None

            embeds = EmbedFactory.from_web_form_embeds(
                title=request.form.get("title", ""),
                description=request.form.get("description") or None,
                hex_colour=request.form.get("colour") or None,
                image_url=image_url,
                thumbnail_url=thumbnail_url,
                author_name=request.form.get("author_name") or None,
                author_icon_url=author_icon_url,
                footer=request.form.get("footer") or None,
                fields=fields,
            )

            run_coro_from_flask(
                send_embeds_to_channel(
                    channel_id=channel_id,
                    embeds=embeds,
                    files=files,
                )
            )

            return render_embed_builder_page(
                message=f"Embed sent. Used {len(embeds)} embed(s).",
                error=None,
            )

        except Exception as error:
            return render_embed_builder_page(
                message=None,
                error=str(error),
            )

    return app


def start_webui(bot: discord.Client) -> None:
    if not bot.config.webui_enabled:
        return

    app = create_webui(bot)

    thread = threading.Thread(
        target=lambda: app.run(
            host=bot.config.webui_host,
            port=bot.config.webui_port,
            debug=False,
            use_reloader=False,
        ),
        daemon=True,
    )

    thread.start()