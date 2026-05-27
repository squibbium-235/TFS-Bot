from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from ...utils.embed_builder import EmbedFactory
from ...utils.form_builder import FormAnswer, FormQuestion, build_form_modal


VERIFICATION_QUESTIONS: list[FormQuestion] = [
    FormQuestion(
        key="age",
        label="How old are you?",
        style=discord.TextStyle.short,
        placeholder="Example: 18",
        required=True,
        min_length=1,
        max_length=3,
    ),
    FormQuestion(
        key="reason",
        label="Why do you want to join?",
        style=discord.TextStyle.paragraph,
        placeholder="Write a short answer.",
        required=True,
        min_length=20,
        max_length=1000,
    ),
    FormQuestion(
        key="rules",
        label="Do you agree to follow the rules?",
        style=discord.TextStyle.short,
        placeholder="Yes / No",
        required=True,
        min_length=2,
        max_length=20,
    ),
]


async def handle_verify_submit(
    interaction: discord.Interaction,
    answers: list[FormAnswer],
) -> None:
    # Temporary behaviour.
    # Later this will:
    # - save the application
    # - scan for blocked terms
    # - calculate AI score
    # - send the full application to the review channel
    # - add approve/reject/question/kick/ban buttons
    summary = "\n".join(
        f"**{answer.label}**\n{answer.value or '*No answer provided.*'}"
        for answer in answers
    )

    embed = EmbedFactory.base(
        title="Application Submitted",
        description=summary,
    )

    await interaction.response.send_message(
        "Your application has been submitted.",
        embed=embed,
        ephemeral=True,
    )


class VerifyView(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Verify",
        style=discord.ButtonStyle.primary,
        custom_id="verify:start",
    )
    async def verify_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        modal = build_form_modal(
            title="Verification Application",
            custom_id=f"verify:application:{interaction.user.id}",
            questions=VERIFICATION_QUESTIONS,
            on_submit=handle_verify_submit,
        )

        await interaction.response.send_modal(modal)


def build_verify_embed() -> discord.Embed:
    embed = EmbedFactory.base(
        title="Welcome To The Furry Sanctuary!",
        description="🔽 Click the button below to **VERIFY!** 🔽",
    )

    embed.add_field(
        name="Please follow our rules at all times",
        value="Press the Verify button to start your application.",
        inline=False,
    )

    return embed


class SetupVerifyCommand(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(
        name="setupverify",
        description="Posts the verification panel in this channel.",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def setup_verify_slash(self, interaction: discord.Interaction) -> None:
        embed = build_verify_embed()

        await interaction.channel.send(embed=embed, view=VerifyView())
        await interaction.response.send_message(
            "Verification panel posted.",
            ephemeral=True,
        )

    @commands.command(name="setupverify")
    @commands.has_permissions(manage_guild=True)
    async def setup_verify_text(self, ctx: commands.Context) -> None:
        embed = build_verify_embed()

        await ctx.send(embed=embed, view=VerifyView())
        await ctx.reply("Verification panel posted.", mention_author=False)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(SetupVerifyCommand(bot))
