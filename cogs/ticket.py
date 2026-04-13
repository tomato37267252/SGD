import discord
from discord.ext import commands
from discord.ui import View
from utils.transcript import create_transcript
import config

class TicketView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Create Ticket", style=discord.ButtonStyle.green)
    async def create_ticket(self, interaction: discord.Interaction, button):
        guild = interaction.guild
        user = interaction.user

        category = discord.utils.get(guild.categories, name=config.TICKET_CATEGORY)
        if not category:
            category = await guild.create_category(config.TICKET_CATEGORY)

        for channel in guild.text_channels:
            if channel.name == f"ticket-{user.name}":
                await interaction.response.send_message(f"❌ You already have a ticket: {channel.mention}", ephemeral=True)
                return

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            user: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }

        channel = await guild.create_text_channel(
            name=f"ticket-{user.name}",
            category=category,
            overwrites=overwrites
        )

        await channel.send(f"🎫 Ticket for {user.mention}", view=CloseView())
        await interaction.response.send_message(f"✅ Ticket created: {channel.mention}", ephemeral=True)

class CloseView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Close Ticket", style=discord.ButtonStyle.red)
    async def close_ticket(self, interaction: discord.Interaction, button):
        channel = interaction.channel
        await interaction.response.send_message("🔒 Closing ticket...")
        transcript = await create_transcript(channel)
        log_channel = interaction.guild.get_channel(config.LOG_CHANNEL_ID)

        if log_channel:
            await log_channel.send(f"📁 Transcript from {channel.name}", file=discord.File(transcript))

        await channel.delete()

class Ticket(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def panel(self, ctx):
        embed = discord.Embed(title="🎫 Support", description="Click the button below to create a ticket.", color=discord.Color.blue())
        await ctx.send(embed=embed, view=TicketView())

async def setup(bot):
    await bot.add_cog(Ticket(bot))
