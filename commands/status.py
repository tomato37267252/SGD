import discord
from discord.ext import commands
from discord.ext import tasks

BOT_NAME    = "Storm G3N"
STATUS_TEXT = ".gg/MetalDrops"


class StatusRole(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        cfg = self.bot.config.get('botConfig', {})
        self.gen_access_role_id = int(cfg.get('genAccessRoleId', 0))
        self.log_ch_id          = int(cfg.get('logsChannelId',   0))
        self.status_text        = cfg.get('statusText', STATUS_TEXT)
        self.check_loop.start()

    def cog_unload(self):
        self.check_loop.cancel()

    def emoji(self, name, default=''):
        return self.bot.config.get('emojis', {}).get(name, default)

    def get_custom_status(self, member) -> str:
        for activity in member.activities:
            if isinstance(activity, discord.CustomActivity):
                return activity.state or ""
        return ""

    def member_has_status(self, member) -> bool:
        return self.status_text in self.get_custom_status(member)

    async def log(self, message: str):
        if not self.log_ch_id:
            return
        ch = self.bot.get_channel(self.log_ch_id)
        if ch:
            try:
                await ch.send(message)
            except Exception as e:
                print(f"[{BOT_NAME}] Log error: {e}")

    async def sync_member(self, member, source="Auto"):
        if not self.gen_access_role_id:
            return
        role = member.guild.get_role(self.gen_access_role_id)
        if not role:
            return

        has_status = self.member_has_status(member)
        has_role   = role in member.roles

        try:
            if has_status and not has_role:
                await member.add_roles(role, reason=f"Storm G3N: {source}")
                await self.log(
                    f"✅ **[{source}]** {member.mention} (`{member}`) "
                    f"status `{self.status_text}` detected → **G3N Access** granted."
                )
                print(f"[{BOT_NAME}] [{source}] Granted G3N Access to {member}")
                try:
                    dm = discord.Embed(title="✅ G3N Access Granted!", color=0x2ecc71)
                    dm.description = (
                        f"Hey **{member.display_name}**! 👋\n\n"
                        f"Your status `{self.status_text}` was detected on **{member.guild.name}**.\n"
                        f"You now have the **G3N Access** role!\n\n"
                        f"Use `$free <service>` in the generator channel. Type `$help` for all services."
                    )
                    dm.set_footer(text=BOT_NAME)
                    await member.send(embed=dm)
                except discord.Forbidden:
                    pass

            elif not has_status and has_role:
                await member.remove_roles(role, reason=f"Storm G3N: {source}")
                await self.log(
                    f"❌ **[{source}]** {member.mention} (`{member}`) "
                    f"removed status → **G3N Access** removed."
                )
                print(f"[{BOT_NAME}] [{source}] Removed G3N Access from {member}")
                try:
                    dm = discord.Embed(title="❌ G3N Access Removed", color=0xff0000)
                    dm.description = (
                        f"Hey **{member.display_name}**,\n\n"
                        f"Your **G3N Access** role was removed because "
                        f"`{self.status_text}` is no longer in your Custom Status.\n\n"
                        f"Set it back to get the role again automatically!"
                    )
                    dm.set_footer(text=BOT_NAME)
                    await member.send(embed=dm)
                except discord.Forbidden:
                    pass

        except discord.Forbidden:
            print(f"[{BOT_NAME}] MISSING PERMISSIONS for {member}! Check role hierarchy.")
        except Exception as e:
            print(f"[{BOT_NAME}] sync_member error for {member}: {e}")

    # ── Instant detection ────────────────────────

    @commands.Cog.listener()
    async def on_presence_update(self, before, after):
        if after.bot or not after.guild:
            return
        await self.sync_member(after, source="Live")

    # ── Loop every 2 min ─────────────────────────

    @tasks.loop(minutes=2)
    async def check_loop(self):
        for guild in self.bot.guilds:
            for member in guild.members:
                if member.bot:
                    continue
                await self.sync_member(member, source="Auto")

    @check_loop.before_loop
    async def before_check_loop(self):
        await self.bot.wait_until_ready()
        for guild in self.bot.guilds:
            try:
                await guild.chunk()
                print(f"[{BOT_NAME}] Chunked {guild.member_count} members in '{guild.name}'")
            except Exception as e:
                print(f"[{BOT_NAME}] Chunk error: {e}")

    # ── $checkroles ──────────────────────────────

    @commands.command(name='checkroles')
    @commands.has_permissions(administrator=True)
    async def checkroles(self, ctx):
        """$checkroles — Force re-check all members for G3N Access role (admin)"""
        role = ctx.guild.get_role(self.gen_access_role_id)
        if not role:
            return await ctx.reply("❌ `genAccessRoleId` is not configured.", mention_author=False)

        msg = await ctx.reply("🔄 Checking all members...", mention_author=False)
        added = removed = 0

        for member in ctx.guild.members:
            if member.bot:
                continue
            has_status = self.member_has_status(member)
            try:
                if has_status and role not in member.roles:
                    await member.add_roles(role, reason="Storm G3N: $checkroles")
                    await self.log(f"✅ **[Force]** {member.mention} → **G3N Access** granted.")
                    added += 1
                elif not has_status and role in member.roles:
                    await member.remove_roles(role, reason="Storm G3N: $checkroles")
                    await self.log(f"❌ **[Force]** {member.mention} → **G3N Access** removed.")
                    removed += 1
            except Exception as e:
                print(f"[{BOT_NAME}] checkroles error for {member}: {e}")

        e = discord.Embed(title="✅ Check Complete", color=0x00ff00)
        e.description = f"**{added}** granted · **{removed}** removed"
        e.set_footer(text=BOT_NAME)
        await msg.edit(content=None, embed=e)

    # ── $setstatus ───────────────────────────────

    @commands.command(name='setstatus')
    @commands.has_permissions(administrator=True)
    async def setstatus(self, ctx, *, text: str = None):
        """$setstatus <text> — Change required status text (admin)"""
        cross = self.emoji('cross', '❌')
        if not text:
            e = discord.Embed(title=f"{cross} Incorrect Usage", color=0xff0000)
            e.description = "**Usage:** `$setstatus <status text>`"
            e.set_footer(text=BOT_NAME)
            return await ctx.reply(embed=e, mention_author=False)

        self.status_text     = text
        self.bot.status_text = text
        e = discord.Embed(title="✅ Status Updated", color=0x00ff00)
        e.description = f"New required status:\n```\n{text}\n```"
        e.set_footer(text=BOT_NAME)
        await ctx.reply(embed=e, mention_author=False)


async def setup(bot):
    await bot.add_cog(StatusRole(bot))
