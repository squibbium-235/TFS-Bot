from __future__ import annotations

from datetime import datetime

import discord

from src.services.application_store import (
    APPLICATION_STATUS_PENDING,
    ApplicationStore,
    StoredApplication,
)


def get_application_store(
    client: discord.Client,
) -> ApplicationStore | None:
    return getattr(
        client,
        "application_store",
        None,
    )


async def send_ephemeral(
    interaction: discord.Interaction,
    message: str,
) -> None:
    kwargs = {
        "ephemeral": True,
        "allowed_mentions": (
            discord.AllowedMentions.none()
        ),
    }

    if interaction.response.is_done():
        await interaction.followup.send(
            message,
            **kwargs,
        )

    else:
        await interaction.response.send_message(
            message,
            **kwargs,
        )


async def audit_action(
    interaction: discord.Interaction,
    action: str,
    detail: str,
) -> None:
    audit_store = getattr(
        interaction.client,
        "audit_store",
        None,
    )

    if audit_store is None:
        return

    try:
        await audit_store.log(
            source="Discord",
            actor_id=str(
                interaction.user.id
            ),
            actor_name=str(
                interaction.user
            ),
            guild_id=(
                interaction.guild_id
            ),
            action=action,
            detail=detail,
        )

    except Exception:
        # Audit logging must never
        # break moderation actions.
        pass


async def get_claimed_pending_application_or_respond(
    interaction: discord.Interaction,
    application_id: str,
) -> tuple[
    ApplicationStore,
    StoredApplication,
] | None:
    store = get_application_store(
        interaction.client
    )

    if store is None:
        await send_ephemeral(
            interaction,
            (
                "The application database "
                "is not available."
            ),
        )

        return None

    application = await store.get_application(
        application_id
    )

    if application is None:
        await send_ephemeral(
            interaction,
            (
                "This application no "
                "longer exists."
            ),
        )

        return None

    if (
        application.status
        != APPLICATION_STATUS_PENDING
    ):
        await send_ephemeral(
            interaction,
            (
                "This application is "
                f"already "
                f"`{application.status}`."
            ),
        )

        return None

    if application.claimed_by is None:
        claimed = await store.claim_application(
            application_id,
            interaction.user.id,
        )

        if claimed:
            application = (
                await store.get_application(
                    application_id
                )
                or application
            )

            await audit_action(
                interaction,
                "application.claim",
                application_id,
            )

        else:
            application = (
                await store.get_application(
                    application_id
                )
                or application
            )

    if (
        application.claimed_by
        != interaction.user.id
    ):
        if application.claimed_by:
            owner_text = (
                f"<@{application.claimed_by}>"
            )

        else:
            owner_text = (
                "another moderator"
            )

        await send_ephemeral(
            interaction,
            (
                "This application is "
                "currently claimed by "
                f"{owner_text}."
            ),
        )

        return None

    return (
        store,
        application,
    )


class ApplicationNoteModal(
    discord.ui.Modal
):
    def __init__(
        self,
        application_id: str,
    ) -> None:
        super().__init__(
            title="Add Staff Note",
            custom_id=(
                "application:"
                "staff_note:"
                f"{application_id}"
            )[:100],
        )

        self.application_id = (
            application_id
        )

        self.note = discord.ui.TextInput(
            label="Note",
            style=(
                discord.TextStyle.paragraph
            ),
            required=True,
            max_length=1000,
            placeholder=(
                "Internal note for staff..."
            ),
        )

        self.add_item(
            self.note
        )

    async def on_submit(
        self,
        interaction: discord.Interaction,
    ) -> None:
        store = get_application_store(
            interaction.client
        )

        if store is None:
            await send_ephemeral(
                interaction,
                (
                    "The application "
                    "database is not "
                    "available."
                ),
            )

            return

        try:
            await store.add_note(
                application_id=(
                    self.application_id
                ),
                author_id=(
                    interaction.user.id
                ),
                content=str(
                    self.note.value
                ),
            )

        except ValueError as error:
            await send_ephemeral(
                interaction,
                str(
                    error
                ),
            )

            return

        await audit_action(
            interaction,
            "application.note.add",
            self.application_id,
        )

        await send_ephemeral(
            interaction,
            "Staff note added.",
        )


class ClaimApplicationButton(
    discord.ui.Button
):
    def __init__(
        self,
        application_id: str,
    ) -> None:
        super().__init__(
            label="Claim",
            style=(
                discord.ButtonStyle.secondary
            ),
            custom_id=(
                "application:claim"
            ),
            row=1,
        )

        self.application_id = (
            application_id
        )

    async def callback(
        self,
        interaction: discord.Interaction,
    ) -> None:
        store = get_application_store(
            interaction.client
        )

        if store is None:
            await send_ephemeral(
                interaction,
                (
                    "The application "
                    "database is not "
                    "available."
                ),
            )

            return

        application = (
            await store.get_application(
                self.application_id
            )
        )

        if application is None:
            await send_ephemeral(
                interaction,
                (
                    "This application "
                    "no longer exists."
                ),
            )

            return

        if (
            application.status
            != APPLICATION_STATUS_PENDING
        ):
            await send_ephemeral(
                interaction,
                (
                    "This application is "
                    f"already "
                    f"`{application.status}`."
                ),
            )

            return

        if (
            application.claimed_by
            == interaction.user.id
        ):
            await send_ephemeral(
                interaction,
                (
                    "You already have "
                    "this application "
                    "claimed."
                ),
            )

            return

        claimed = await store.claim_application(
            self.application_id,
            interaction.user.id,
        )

        if not claimed:
            application = (
                await store.get_application(
                    self.application_id
                )
            )

            if (
                application
                and application.claimed_by
            ):
                await send_ephemeral(
                    interaction,
                    (
                        "This application is "
                        "already claimed by "
                        f"<@{application.claimed_by}>."
                    ),
                )

            else:
                await send_ephemeral(
                    interaction,
                    (
                        "This application "
                        "could not be claimed."
                    ),
                )

            return

        await audit_action(
            interaction,
            "application.claim",
            self.application_id,
        )

        await send_ephemeral(
            interaction,
            "Application claimed.",
        )


class ReleaseApplicationClaimButton(
    discord.ui.Button
):
    def __init__(
        self,
        application_id: str,
    ) -> None:
        super().__init__(
            label="Release",
            style=(
                discord.ButtonStyle.secondary
            ),
            custom_id=(
                "application:release"
            ),
            row=1,
        )

        self.application_id = (
            application_id
        )

    async def callback(
        self,
        interaction: discord.Interaction,
    ) -> None:
        store = get_application_store(
            interaction.client
        )

        if store is None:
            await send_ephemeral(
                interaction,
                (
                    "The application "
                    "database is not "
                    "available."
                ),
            )

            return

        released = await store.release_claim(
            self.application_id,
            interaction.user.id,
        )

        if not released:
            await send_ephemeral(
                interaction,
                (
                    "You do not own "
                    "this application's "
                    "claim."
                ),
            )

            return

        await audit_action(
            interaction,
            "application.claim.release",
            self.application_id,
        )

        await send_ephemeral(
            interaction,
            "Application claim released.",
        )


class AddApplicationNoteButton(
    discord.ui.Button
):
    def __init__(
        self,
        application_id: str,
    ) -> None:
        super().__init__(
            label="Add Note",
            style=(
                discord.ButtonStyle.secondary
            ),
            custom_id=(
                "application:add_note"
            ),
            row=1,
        )

        self.application_id = (
            application_id
        )

    async def callback(
        self,
        interaction: discord.Interaction,
    ) -> None:
        await interaction.response.send_modal(
            ApplicationNoteModal(
                self.application_id
            )
        )


class ViewApplicationNotesButton(
    discord.ui.Button
):
    def __init__(
        self,
        application_id: str,
    ) -> None:
        super().__init__(
            label="View Notes",
            style=(
                discord.ButtonStyle.secondary
            ),
            custom_id=(
                "application:view_notes"
            ),
            row=1,
        )

        self.application_id = (
            application_id
        )

    async def callback(
        self,
        interaction: discord.Interaction,
    ) -> None:
        store = get_application_store(
            interaction.client
        )

        if store is None:
            await send_ephemeral(
                interaction,
                (
                    "The application "
                    "database is not "
                    "available."
                ),
            )

            return

        notes = await store.list_notes(
            self.application_id,
            limit=10,
        )

        if not notes:
            await send_ephemeral(
                interaction,
                (
                    "There are no staff "
                    "notes on this "
                    "application."
                ),
            )

            return

        lines: list[str] = []

        for note in reversed(
            notes
        ):
            try:
                created = (
                    datetime.fromisoformat(
                        note.created_at
                    )
                )

                timestamp = (
                    f"<t:"
                    f"{int(created.timestamp())}"
                    f":R>"
                )

            except ValueError:
                timestamp = (
                    "`Unknown time`"
                )

            lines.append(
                (
                    f"**<@{note.author_id}>** "
                    f"{timestamp}\n"
                    f"{note.content}"
                )
            )

        message = "\n\n".join(
            lines
        )

        if len(message) > 1900:
            message = (
                message[:1897]
                + "..."
            )

        await send_ephemeral(
            interaction,
            message,
        )