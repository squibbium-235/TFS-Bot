from __future__ import annotations

import asyncio
import hmac
import sqlite3
import threading
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
from src.commands.verification.verification import VerifyView
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
            width: 340px;
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

        .error {
            color: #ff6b6b;
        }
    </style>
</head>
<body>
    <div class="card">
        <h1>TFSBot Web UI</h1>

        <form method="post">
            <label>Username</label>
            <input type="text" name="username" autocomplete="username" autofocus>

            <label>Password</label>
            <input type="password" name="password" autocomplete="current-password">

            <button type="submit">Login</button>
        </form>

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
        }

        header h1 {
            margin: 0;
            font-size: 22px;
        }

        header nav {
            display: flex;
            gap: 14px;
            align-items: center;
        }

        header a {
            color: var(--muted);
            text-decoration: none;
        }

        main {
            display: grid;
            grid-template-columns: minmax(420px, 700px) minmax(360px, 1fr);
            gap: 24px;
            padding: 24px;
        }

        .panel {
            background: var(--panel);
            border: 1px solid var(--border);
            border-radius: 18px;
            padding: 20px;
            box-shadow: 0 18px 50px rgba(0, 0, 0, 0.22);
            margin-bottom: 18px;
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

        .embed-image,
        .embed-thumbnail {
            max-width: 100%;
            border-radius: 8px;
            margin-top: 10px;
        }

        .embed-thumbnail {
            max-width: 90px;
            float: right;
            margin-left: 10px;
        }

        .embed-footer {
            margin-top: 10px;
            font-size: 12px;
            color: var(--muted);
        }

        @media (max-width: 980px) {
            main {
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
            <a href="{{ url_for('embed_builder') }}" class="{{ 'active' if active_page == 'embed_builder' else '' }}">Embed Builder</a>
            <a href="{{ url_for('dm_templates') }}" class="{{ 'active' if active_page == 'dm_templates' else '' }}">DM Templates</a>
            <a href="{{ url_for('verification_page') }}" class="{{ 'active' if active_page == 'verification' else '' }}">Verification</a>
            <a href="{{ url_for('permissions_page') }}" class="{{ 'active' if active_page == 'permissions' else '' }}">Permissions</a>
            <a href="{{ url_for('backups_page') }}" class="{{ 'active' if active_page == 'backups' else '' }}">Backups</a>
            <a href="{{ url_for('logout') }}">Logout</a>
        </nav>
    </header>

    <main>
        <section>
            <div class="panel">
                {% if message %}
                    <p class="message">{{ message }}</p>
                {% endif %}

                {% if error %}
                    <p class="error">{{ error }}</p>
                {% endif %}

                <h2>Upload Image</h2>

                <form method="post" action="{{ url_for('upload_image') }}" enctype="multipart/form-data">
                    <label>Image file</label>
                    <input type="file" name="image" accept="image/png,image/jpeg,image/gif,image/webp" required>

                    <p class="hint">
                        Uploaded images can be selected below. When sent to Discord, they are attached to the message,
                        so they do not need Imgur or another image host.
                    </p>

                    <button type="submit">Upload Image</button>
                </form>
            </div>

            <div class="panel">
                <form method="post" action="{{ url_for('send_embed') }}" id="embed-form">
                    <h2>Destination</h2>

                    <label>Channel</label>
                    <select name="channel_id" required>
                        {% for channel in channels %}
                            <option value="{{ channel.id }}">{{ channel.label }}</option>
                        {% endfor %}
                    </select>

                    <h2>Embed</h2>

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

                    <label>Uploaded image</label>
                    <select name="image_upload_filename" id="image_upload_filename">
                        <option value="">No uploaded image</option>
                        {% for image in uploaded_images %}
                            <option value="{{ image.filename }}" data-url="{{ image.url }}">{{ image.filename }}</option>
                        {% endfor %}
                    </select>

                    <label>Or external image URL</label>
                    <input name="image_url" id="image_url" placeholder="https://example.com/image.png">

                    <label>Uploaded thumbnail</label>
                    <select name="thumbnail_upload_filename" id="thumbnail_upload_filename">
                        <option value="">No uploaded thumbnail</option>
                        {% for image in uploaded_images %}
                            <option value="{{ image.filename }}" data-url="{{ image.url }}">{{ image.filename }}</option>
                        {% endfor %}
                    </select>

                    <label>Or external thumbnail URL</label>
                    <input name="thumbnail_url" id="thumbnail_url" placeholder="https://example.com/thumb.png">

                    <label>Author name</label>
                    <input name="author_name" id="author_name" maxlength="256">

                    <label>Author icon URL</label>
                    <input name="author_icon_url" id="author_icon_url">

                    <label>Footer</label>
                    <input name="footer" id="footer" maxlength="2048" value="TFSBot">

                    <h2>Fields</h2>

                    <div id="fields"></div>

                    <div class="actions">
                        <button type="button" class="secondary" onclick="addField()">Add field</button>
                        <button type="submit">Send Embed</button>
                    </div>
                </form>
            </div>
        </section>

        <section class="preview-wrap">
            <div class="panel">
                <h2>Preview</h2>

                <div class="discord-preview">
                    <div class="discord-message">
                        <div class="avatar">T</div>

                        <div class="message-body">
                            <span class="bot-name">TFSBot</span>
                            <span class="bot-tag">BOT</span>

                            <div class="embed-preview" id="preview-embed">
                                <img class="embed-thumbnail" id="preview-thumbnail" style="display: none;">

                                <div class="embed-author" id="preview-author-wrap" style="display: none;">
                                    <img id="preview-author-icon" style="display: none;">
                                    <span id="preview-author"></span>
                                </div>

                                <div class="embed-title" id="preview-title">Embed title</div>
                                <div class="embed-description" id="preview-description">Embed description will appear here.</div>

                                <div class="embed-fields" id="preview-fields"></div>

                                <img class="embed-image" id="preview-image" style="display: none;">

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

            if (!url) {
                image.style.display = "none";
                image.removeAttribute("src");
                return;
            }

            image.src = url;
            image.style.display = "block";
        }

        function updatePreview() {
            const title = getValue("title") || "Embed title";
            const description = getValue("description") || "Embed description will appear here.";
            const colour = normaliseHexColour(getValue("colour")) || "#5865F2";
            const imageUrl = getImagePreviewUrl("image_upload_filename", "image_url");
            const thumbnailUrl = getImagePreviewUrl("thumbnail_upload_filename", "thumbnail_url");
            const authorName = getValue("author_name");
            const authorIconUrl = getValue("author_icon_url");
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

            if (authorName) {
                authorWrap.style.display = "flex";
                author.textContent = authorName;

                if (authorIconUrl) {
                    authorIcon.src = authorIconUrl;
                    authorIcon.style.display = "inline-block";
                } else {
                    authorIcon.style.display = "none";
                    authorIcon.removeAttribute("src");
                }
            } else {
                authorWrap.style.display = "none";
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
            position: sticky;
            top: 0;
            z-index: 10;
        }

        header h1 {
            margin: 0;
            font-size: 22px;
            letter-spacing: -0.02em;
        }

        nav { display: flex; gap: 16px; align-items: center; }
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

        .stat-card strong { display: block; margin-bottom: 4px; }

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

        .data-table th, .data-table td {
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

        .data-table tr:last-child td { border-bottom: 0; }

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

        .muted-link { color: var(--muted); }

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
            <a href="{{ url_for('embed_builder') }}" class="{{ 'active' if active_page == 'embed_builder' else '' }}">Embed Builder</a>
            <a href="{{ url_for('dm_templates') }}" class="{{ 'active' if active_page == 'dm_templates' else '' }}">DM Templates</a>
            <a href="{{ url_for('verification_page') }}" class="{{ 'active' if active_page == 'verification' else '' }}">Verification</a>
            <a href="{{ url_for('permissions_page') }}" class="{{ 'active' if active_page == 'permissions' else '' }}">Permissions</a>
            <a href="{{ url_for('backups_page') }}" class="{{ 'active' if active_page == 'backups' else '' }}">Backups</a>
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
        Quick state of the bot, verification queue, and setup. A dashboard, because apparently staring at logs is not a personality.
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
    <h2>Today</h2>
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
<div class="panel">
    <h2>DM Templates</h2>
    <p class="hint">
        These messages are sent to users during verification actions. Available variables:
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

    {% for template in templates %}
        <div class="template-card">
            <div class="card-header">
                <div>
                    <h3>{{ template.label }}</h3>
                    <p class="template-meta">Key: <code>{{ template.key }}</code></p>
                </div>
                {% if template.is_custom %}
                    <span class="badge custom">Custom</span>
                {% else %}
                    <span class="badge">Default</span>
                {% endif %}
            </div>

            <textarea name="template_{{ template.key }}" rows="5">{{ template.text }}</textarea>

            <details class="default-details">
                <summary>Show default text</summary>
                <pre>{{ template.default }}</pre>
            </details>
        </div>
    {% endfor %}

    <div class="panel action-panel">
        <button type="submit">Save DM Templates</button>
    </div>
</form>
{% else %}
<div class="panel"><p>No servers available.</p></div>
{% endif %}
"""


PERMISSIONS_BODY_HTML = """
<div class="panel">
    <h2>Permissions</h2>
    <p class="hint">
        This mirrors the <code>/permissions</code> commands. The WebUI is just a less painful control panel,
        because apparently slash commands were not invented for tables.
    </p>

    <form method="get" action="{{ url_for('permissions_page') }}">
        <label>Server</label>
        <select name="guild_id" onchange="this.form.submit()">
            {% for guild in guilds %}
                <option value="{{ guild.id }}" {{ 'selected' if guild.id == selected_guild_id else '' }}>{{ guild.name }}</option>
            {% endfor %}
        </select>
    </form>
</div>

{% if selected_guild_id %}
<form method="post" action="{{ url_for('permissions_page') }}">
    <input type="hidden" name="guild_id" value="{{ selected_guild_id }}">

    <div class="panel">
        <h2>Permission Roles</h2>

        <div class="grid-2">
            {% for role_setting in role_settings %}
                <div>
                    <label>{{ role_setting.label }}</label>
                    <select name="role_{{ role_setting.level }}">
                        <option value="">Not set</option>
                        {% for role in roles %}
                            <option value="{{ role.id }}" {{ 'selected' if role.id == role_setting.role_id else '' }}>{{ role.name }}</option>
                        {% endfor %}
                    </select>
                </div>
            {% endfor %}
        </div>
    </div>

    <div class="panel">
        <h2>Command Levels</h2>

        {% for command in commands %}
            <div class="command-row">
                <div>
                    <h3><code>{{ command.key }}</code></h3>
                </div>

                <div>
                    <input type="hidden" name="command_key[]" value="{{ command.key }}">
                    <select name="command_level_{{ command.safe_key }}">
                        {% for level in levels %}
                            <option value="{{ level.value }}" {{ 'selected' if level.value == command.level else '' }}>{{ level.label }}</option>
                        {% endfor %}
                    </select>
                </div>
            </div>
        {% endfor %}
    </div>

    <div class="panel">
        <button type="submit">Save Permissions</button>
    </div>
</form>
{% else %}
<div class="panel"><p>No servers available.</p></div>
{% endif %}
"""


BACKUPS_BODY_HTML = """
<div class="panel">
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
</div>

<div class="panel">
    <h2>Create Backup</h2>

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

<div class="panel danger-panel">
    <h2>Restore Backup</h2>

    <p class="hint">
        Restoring replaces the current database with the uploaded backup.
        The current database and uploads are copied to <code>data/restore_safety/</code> first, deleting the lifeboat before using the slide is generally frowned upon.
    </p>

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

<div class="panel">
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
"""


VERIFICATION_BODY_HTML = """
<div class="panel">
    <h2>Verification</h2>
    <p class="hint">
        Manage verification channels, approval roles, invite tracking, and application automod from here.
        Slash commands can still do the same things, because apparently every admin panel needs two doors.
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
        <h2>Channels and Panel</h2>

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
            <button type="submit" name="action" value="refresh_invites" class="secondary-button">Refresh Invite Cache</button>
        </div>
    </div>

    <div class="panel">
        <h2>Approval Roles</h2>
        <p class="hint">On approval, the bot can give one role and remove one role. The bot's Discord role must be above both roles, because Discord loves hierarchy more than sense.</p>

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
    </div>

    <div class="panel">
        <h2>Verification Automod</h2>
        <p class="hint">
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

    <div class="panel">
        <h2>Invite Tracking</h2>
        <p class="hint">Invite tracking runs automatically on member join. Refreshing the cache is useful after restarting the bot or creating/deleting invites.</p>
        <div class="stat-grid">
            <div class="stat-card"><strong>Status</strong>{{ invite_tracking_status }}</div>
            <div class="stat-card"><strong>Permission needed</strong>Manage Server</div>
            <div class="stat-card"><strong>Shown on apps</strong>Invite code and inviter</div>
        </div>
    </div>
</form>
{% else %}
<div class="panel"><p>No servers available.</p></div>
{% endif %}
"""


def create_webui(bot: discord.Client) -> Flask:
    app = Flask(__name__)

    secret_source = "|".join(
        f"{credential.username}:{credential.password}"
        for credential in bot.config.webui_credentials
    )
    app.secret_key = secret_source or "tfsbot-dev-secret"

    app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    def is_logged_in() -> bool:
        return session.get("logged_in") is True

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

    def get_uploaded_image_path(filename: str) -> Path:
        safe_name = validate_uploaded_image_filename(filename)
        return UPLOAD_DIR / safe_name

    def list_uploaded_images() -> list[dict[str, str]]:
        images: list[dict[str, str]] = []

        for path in sorted(
            UPLOAD_DIR.iterdir(),
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        ):
            if not path.is_file():
                continue

            if path.suffix.lower() not in ALLOWED_IMAGE_EXTENSIONS:
                continue

            images.append(
                {
                    "filename": path.name,
                    "url": url_for("uploaded_image", filename=path.name),
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
    ) -> tuple[str | None, str | None, list[discord.File]]:
        files: list[discord.File] = []
        attached_filenames: set[str] = set()

        image_url: str | None = None
        thumbnail_url: str | None = None

        for selected_filename, target in [
            (image_upload_filename, "image"),
            (thumbnail_upload_filename, "thumbnail"),
        ]:
            if not selected_filename:
                continue

            path = get_uploaded_image_path(selected_filename)

            if not path.exists():
                raise FileNotFoundError(f"Uploaded image not found: {selected_filename}")

            filename = path.name

            if filename not in attached_filenames:
                files.append(discord.File(path, filename=filename))
                attached_filenames.add(filename)

            attachment_url = f"attachment://{filename}"

            if target == "image":
                image_url = attachment_url
            else:
                thumbnail_url = attachment_url

        return image_url, thumbnail_url, files

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
        )

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

    def make_health_item(
        label: str,
        value: str,
        status_class: str,
    ) -> dict[str, str]:
        return {
            "label": label,
            "value": value,
            "class": status_class,
        }


    def get_bot_member(guild: discord.Guild) -> discord.Member | None:
        if bot.user is None:
            return None

        member = guild.me

        if member is not None:
            return member

        return guild.get_member(bot.user.id)


    def get_guild_permission_health_item(
        guild: discord.Guild,
        label: str,
        permission_name: str,
        friendly_name: str,
    ) -> dict[str, str]:
        member = get_bot_member(guild)

        if member is None:
            return make_health_item(
                label=label,
                value="Bot member unavailable",
                status_class="warn",
            )

        has_permission = bool(
            getattr(member.guild_permissions, permission_name, False)
        )

        if has_permission:
            return make_health_item(
                label=label,
                value="OK",
                status_class="good",
            )

        return make_health_item(
            label=label,
            value=f"Missing {friendly_name}",
            status_class="bad",
        )


    def get_role_hierarchy_health_item(
        guild: discord.Guild,
        label: str,
        role_id: int | None,
    ) -> dict[str, str]:
        if role_id is None:
            return make_health_item(
                label=label,
                value="Not set",
                status_class="warn",
            )

        role = guild.get_role(role_id)

        if role is None:
            return make_health_item(
                label=label,
                value=f"Unknown role {role_id}",
                status_class="bad",
            )

        member = get_bot_member(guild)

        if member is None:
            return make_health_item(
                label=label,
                value="Bot member unavailable",
                status_class="warn",
            )

        if not member.guild_permissions.manage_roles:
            return make_health_item(
                label=label,
                value="Missing Manage Roles",
                status_class="bad",
            )

        if role >= member.top_role:
            return make_health_item(
                label=label,
                value=f"Bot role too low for {role.name}",
                status_class="bad",
            )

        return make_health_item(
            label=label,
            value=f"OK - {role.name}",
            status_class="good",
        )


    def get_channel_permission_health_item(
        guild: discord.Guild,
        label: str,
        channel_id: int | None,
        required_permissions: dict[str, str],
        optional_permissions: dict[str, str] | None = None,
    ) -> dict[str, str]:
        optional_permissions = optional_permissions or {}

        if channel_id is None:
            return make_health_item(
                label=label,
                value="Not set",
                status_class="warn",
            )

        channel = guild.get_channel(channel_id)

        if not isinstance(channel, discord.TextChannel):
            return make_health_item(
                label=label,
                value=f"Missing channel {channel_id}",
                status_class="bad",
            )

        member = get_bot_member(guild)

        if member is None:
            return make_health_item(
                label=label,
                value="Bot member unavailable",
                status_class="warn",
            )

        permissions = channel.permissions_for(member)

        missing_required = [
            friendly_name
            for permission_name, friendly_name in required_permissions.items()
            if not bool(getattr(permissions, permission_name, False))
        ]

        if missing_required:
            return make_health_item(
                label=label,
                value="Missing " + ", ".join(missing_required),
                status_class="bad",
            )

        missing_optional = [
            friendly_name
            for permission_name, friendly_name in optional_permissions.items()
            if not bool(getattr(permissions, permission_name, False))
        ]

        if missing_optional:
            return make_health_item(
                label=label,
                value="OK, but missing " + ", ".join(missing_optional),
                status_class="warn",
            )

        return make_health_item(
            label=label,
            value="OK",
            status_class="good",
        )


    def build_sanity_health_items(
        guild: discord.Guild,
        review_channel_id: int | None,
        log_channel_id: int | None,
        approved_add_role_id: int | None,
        approved_remove_role_id: int | None,
    ) -> list[dict[str, str]]:
        return [
            get_guild_permission_health_item(
                guild=guild,
                label="Role management",
                permission_name="manage_roles",
                friendly_name="Manage Roles",
            ),
            get_guild_permission_health_item(
                guild=guild,
                label="Ban permission",
                permission_name="ban_members",
                friendly_name="Ban Members",
            ),
            get_guild_permission_health_item(
                guild=guild,
                label="Invite tracking permission",
                permission_name="manage_guild",
                friendly_name="Manage Server",
            ),
            get_role_hierarchy_health_item(
                guild=guild,
                label="Give role hierarchy",
                role_id=approved_add_role_id,
            ),
            get_role_hierarchy_health_item(
                guild=guild,
                label="Remove role hierarchy",
                role_id=approved_remove_role_id,
            ),
            get_channel_permission_health_item(
                guild=guild,
                label="Review channel permissions",
                channel_id=review_channel_id,
                required_permissions={
                    "view_channel": "View Channel",
                    "send_messages": "Send Messages",
                    "embed_links": "Embed Links",
                    "attach_files": "Attach Files",
                    "read_message_history": "Read Message History",
                    "create_public_threads": "Create Public Threads",
                    "send_messages_in_threads": "Send Messages in Threads",
                },
                optional_permissions={
                    "manage_threads": "Manage Threads",
                },
            ),
            get_channel_permission_health_item(
                guild=guild,
                label="Log channel permissions",
                channel_id=log_channel_id,
                required_permissions={
                    "view_channel": "View Channel",
                    "send_messages": "Send Messages",
                    "embed_links": "Embed Links",
                    "attach_files": "Attach Files",
                },
            ),
        ]

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

        health_items.extend(
            build_sanity_health_items(
                guild=guild,
                review_channel_id=review_channel_id,
                log_channel_id=log_channel_id,
                approved_add_role_id=add_role_id,
                approved_remove_role_id=remove_role_id,
            )
        )

        app_stats["health_items"] = health_items
        return app_stats

    @app.route("/uploads/<path:filename>")
    def uploaded_image(filename: str):
        if not is_logged_in():
            return redirect(url_for("login"))

        return send_from_directory(UPLOAD_DIR, filename)

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "GET":
            return render_template_string(LOGIN_HTML, error=None)

        username = request.form.get("username", "")
        password = request.form.get("password", "")

        login_ok = any(
            hmac.compare_digest(username, credential.username)
            and hmac.compare_digest(password, credential.password)
            for credential in bot.config.webui_credentials
        )

        if not login_ok:
            return render_template_string(
                LOGIN_HTML,
                error="Incorrect username or password.",
            )

        session["logged_in"] = True
        session["username"] = username

        return redirect(url_for("index"))

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
        if not is_logged_in():
            return redirect(url_for("login"))

        message: str | None = None
        error: str | None = None

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

                    message = (
                        f"Restored {restored_text}. "
                        f"Safety copy created at {restore_result.safety_backup_directory}. "
                        "Restart the bot now."
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
            message=message,
            error=error,
        )

    @app.route("/embed-builder")
    def embed_builder():
        if not is_logged_in():
            return redirect(url_for("login"))

        return render_template_string(
            EMBED_FORM_HTML,
            channels=get_available_channels(),
            uploaded_images=list_uploaded_images(),
            message=None,
            error=None,
        )


    @app.route("/dm-templates", methods=["GET", "POST"])
    def dm_templates():
        if not is_logged_in():
            return redirect(url_for("login"))

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

    @app.route("/verification", methods=["GET", "POST"])
    def verification_page():
        if not is_logged_in():
            return redirect(url_for("login"))

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

                if action == "refresh_invites":
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
        if not is_logged_in():
            return redirect(url_for("login"))

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

                message = "Permissions saved."

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
                message=message,
                error=error,
            )

    @app.route("/upload", methods=["POST"])
    def upload_image():
        if not is_logged_in():
            return redirect(url_for("login"))

        try:
            uploaded_file = request.files.get("image")

            if uploaded_file is None or not uploaded_file.filename:
                raise ValueError("No image selected.")

            safe_name = validate_uploaded_image_filename(uploaded_file.filename)
            destination = UPLOAD_DIR / safe_name

            if destination.exists():
                stem = destination.stem
                suffix = destination.suffix
                counter = 1

                while destination.exists():
                    destination = UPLOAD_DIR / f"{stem}_{counter}{suffix}"
                    counter += 1

            uploaded_file.save(destination)

            return render_template_string(
                EMBED_FORM_HTML,
                channels=get_available_channels(),
                uploaded_images=list_uploaded_images(),
                message=f"Uploaded {destination.name}.",
                error=None,
            )

        except Exception as error:
            return render_template_string(
                EMBED_FORM_HTML,
                channels=get_available_channels(),
                uploaded_images=list_uploaded_images(),
                message=None,
                error=str(error),
            )

    @app.route("/send", methods=["POST"])
    def send_embed():
        if not is_logged_in():
            return redirect(url_for("login"))

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

            image_attachment_url, thumbnail_attachment_url, files = build_selected_attachment_files(
                image_upload_filename=request.form.get("image_upload_filename") or None,
                thumbnail_upload_filename=request.form.get("thumbnail_upload_filename") or None,
            )

            image_url = image_attachment_url or request.form.get("image_url") or None
            thumbnail_url = thumbnail_attachment_url or request.form.get("thumbnail_url") or None

            embeds = EmbedFactory.from_web_form_embeds(
                title=request.form.get("title", ""),
                description=request.form.get("description") or None,
                hex_colour=request.form.get("colour") or None,
                image_url=image_url,
                thumbnail_url=thumbnail_url,
                author_name=request.form.get("author_name") or None,
                author_icon_url=request.form.get("author_icon_url") or None,
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

            return render_template_string(
                EMBED_FORM_HTML,
                channels=get_available_channels(),
                uploaded_images=list_uploaded_images(),
                message=f"Embed sent. Used {len(embeds)} embed(s).",
                error=None,
            )

        except Exception as error:
            return render_template_string(
                EMBED_FORM_HTML,
                channels=get_available_channels(),
                uploaded_images=list_uploaded_images(),
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