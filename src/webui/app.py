from __future__ import annotations

import hmac
import json
import secrets
import sqlite3
import threading
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

import discord
from flask import (
    Flask,
    redirect,
    render_template,
    render_template_string,
    request,
    session,
    url_for,
)

from src.webui.context import (
    WebUIContext,
)
from src.webui.helpers import (
    WEBUI_CONTEXT_KEY,
)

from src.webui.routes import (
    register_blueprints,
)

from src.utils.embed_builder import EmbedFactory
from src.webui.custom_commands import register_custom_command_webui


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
            <a href="{{ url_for('overview.index') }}" class="{{ 'active' if active_page == 'overview' else '' }}">Overview</a>
            {% if is_owner %}
                <a href="{{ url_for('embed_builder') }}" class="{{ 'active' if active_page == 'embed_builder' else '' }}">Embed Builder</a>
                <a href="{{ url_for('custom_commands_page') }}" class="{{ 'active' if active_page == 'custom_commands' else '' }}">Custom Commands</a>
                <a href="{{ url_for('dm_templates.index') }}" class="{{ 'active' if active_page == 'dm_templates' else '' }}">DM Templates</a>
                <a href="{{ url_for('forms.index') }}" class="{{ 'active' if active_page == 'forms' else '' }}">Forms</a>
                <a href="{{ url_for('uploads.index') }}" class="{{ 'active' if active_page == 'uploads' else '' }}">Uploads</a>
                <a href="{{ url_for('verification.index') }}" class="{{ 'active' if active_page == 'verification' else '' }}">Verification</a>
                <a href="{{ url_for('permissions.index') }}" class="{{ 'active' if active_page == 'permissions' else '' }}">Permissions</a>
                <a href="{{ url_for('backups.index') }}" class="{{ 'active' if active_page == 'backups' else '' }}">Backups</a>
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
                        Add optional embed fields. Inline fields try to sit beside each other, assuming Discord feels cooperative.
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
                            Approximate Discord preview. Final spacing may still vary, because Discord enjoys little surprises.
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

def create_webui(bot: discord.Client) -> Flask:
    app = Flask(__name__)
    
    web_context = WebUIContext(
        bot
    )

    app.extensions[
        WEBUI_CONTEXT_KEY
    ] = web_context

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

    is_logged_in = (
        web_context.is_logged_in
    )

    is_discord_login_enabled = (
        web_context
        .access
        .discord_login_enabled
    )

    is_password_login_enabled = (
        web_context
        .access
        .password_login_enabled
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
        
    run_coro_from_flask = (
        web_context.run_coro
    )

    get_available_guilds = (
        web_context.available_guilds
    )

    get_selected_guild = (
        web_context.selected_guild
    )

    def render_admin_page(
        title: str,
        active_page: str,
        body_template: str,
        message: str | None = None,
        error: str | None = None,
        **context: Any,
    ) -> str:
        body = render_template_string(
            body_template,
            **context,
        )

        return render_template(
            "base.html",
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
            upload_folders=(
                web_context
                .uploads
                .list_folders()
            ),
            message=message,
            error=error,
            active_page="embed_builder",
            is_owner=is_webui_owner(),
            webui_role=current_webui_role(),
            display_name=get_session_display_name(),
        )

    current_webui_role = (
        web_context.current_role
    )

    is_webui_owner = (
        web_context.is_owner
    )

    get_session_display_name = (
        web_context.display_name
    )

    def render_owner_required_page() -> str:
        return render_template(
            "access_denied.html",
            **web_context.template_context(
                title="Access Denied",
                active_page="overview",
                message=None,
                error=(
                    "You need the owner WebUI role "
                    "to use that page."
                ),
            ),
        )

    def require_owner_page() -> str | None:
        if not is_logged_in():
            return redirect(url_for("login"))

        if not is_webui_owner():
            return render_owner_required_page()

        return None

    get_invite_tracker_store = (
        web_context.invite_tracker_store
    )

    get_guild_roles = (
        web_context.guild_roles
    )

    list_uploaded_images = (
        web_context
        .uploads
        .list_images
    )
    
    def build_selected_attachment_files(
        image_upload_filename: (
            str | None
        ),
        thumbnail_upload_filename: (
            str | None
        ),
        author_icon_upload_filename: (
            str | None
        ) = None,
    ) -> tuple[
        str | None,
        str | None,
        str | None,
        list[discord.File],
    ]:
        return (
            web_context
            .uploads
            .build_attachment_files(
                image_reference=(
                    image_upload_filename
                ),
                thumbnail_reference=(
                    thumbnail_upload_filename
                ),
                author_icon_reference=(
                    author_icon_upload_filename
                ),
            )
        )

    close_discord_files = (
        web_context
        .uploads
        .close_files
    )

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

        return redirect(url_for("overview.index"))

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

            webui_role = (
                web_context
                .access
                .matching_discord_role(
                    member_data
                )
            )

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

            return redirect(url_for("overview.index"))

        except Exception as error:
            return render_login_page(error=str(error))

    @app.route("/logout")
    def logout():
        session.clear()
        return redirect(url_for("login"))


    @app.route("/embed-builder")
    def embed_builder():
        owner_error = require_owner_page()

        if owner_error is not None:
            return owner_error

        return render_embed_builder_page(
            message=None,
            error=None,
        )

    @app.route(
        "/upload",
        methods=["POST"],
    )
    def upload_image():
        owner_error = (
            require_owner_page()
        )

        if owner_error is not None:
            return owner_error

        try:
            folder = (
                request.form.get(
                    "new_folder"
                )
                or request.form.get(
                    "folder"
                )
                or ""
            )

            reference = (
                web_context
                .uploads
                .save_upload(
                    request.files.get(
                        "image"
                    ),
                    folder,
                )
            )

            return (
                render_embed_builder_page(
                    message=(
                        f"Uploaded "
                        f"{reference}."
                    ),
                    error=None,
                )
            )

        except Exception as error:
            return (
                render_embed_builder_page(
                    message=None,
                    error=str(
                        error
                    ),
                )
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
            
    register_custom_command_webui(
        app=app,
        bot=bot,
        require_owner_page=require_owner_page,
        get_selected_guild=get_selected_guild,
        get_available_guilds=get_available_guilds,
        get_guild_roles=get_guild_roles,
        render_admin_page=render_admin_page,
        run_coro_from_flask=run_coro_from_flask,
    )
    
    register_blueprints(
        app
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