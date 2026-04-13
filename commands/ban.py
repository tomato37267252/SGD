import discord
from discord.ext import commands

BOT_NAME = "Storm G3N"


class BanCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def emoji(self, name, default=''):
        return self.bot.config.get('emojis', {}).get(name, default)

    def vouch(self):
        return self.bot.get_cog('VouchSystem')

    @commands.command(name='ban')
    @commands.has_permissions(ban_members=True)
    async def ban(self, ctx, member: discord.Member = None):
        """$ban @user — Permanently ban a user from the generator"""
        cross  = self.emoji('cross',      '❌')
        hammer = self.emoji('ban_hammer', '🔨')

        if not member:
            e = discord.Embed(title=f"{cross} Incorrect Usage", color=0xff0000)
            e.description = "**Usage:** `$ban @user`"
            e.set_footer(text=BOT_NAME)
            return await ctx.reply(embed=e, mention_author=False)

        if member.id == ctx.author.id:
            return await ctx.reply("❌ You cannot ban yourself.", mention_author=False)

        v = self.vouch()
        if not v:
            return await ctx.reply("❌ Vouch system unavailable.", mention_author=False)

        gid = str(ctx.guild.id)
        mid = str(member.id)
        v.ensure_guild(gid)
        v.data["permBlocks"][gid][mid] = True
        v.data["tempBlocks"][gid].pop(mid, None)
        v.save_data()

        e = discord.Embed(title=f"{hammer} Permanent Ban", color=0xff0000)
        e.description = f"**{member}** is permanently blocked from the generator."
        e.add_field(name="Banned By", value=str(ctx.author), inline=True)
        e.add_field(name="User ID",   value=str(member.id),  inline=True)
        e.set_footer(text=BOT_NAME)
        await ctx.send(embed=e)

    @commands.command(name='tempban')
    @commands.has_permissions(ban_members=True)
    async def tempban(self, ctx, member: discord.Member = None, minutes: int = None):
        """$tempban @user <minutes> — Temporarily ban a user from the generator"""
        cross = self.emoji('cross', '❌')
        timer = self.emoji('timer', '⏱️')

        if not member or minutes is None:
            e = discord.Embed(title=f"{cross} Incorrect Usage", color=0xff0000)
            e.description = "**Usage:** `$tempban @user <minutes>`"
            e.set_footer(text=BOT_NAME)
            return await ctx.reply(embed=e, mention_author=False)

        if minutes <= 0:
            return await ctx.reply("❌ Duration must be greater than 0.", mention_author=False)
        if member.id == ctx.author.id:
            return await ctx.reply("❌ You cannot ban yourself.", mention_author=False)

        v = self.vouch()
        if not v:
            return await ctx.reply("❌ Vouch system unavailable.", mention_author=False)

        gid = str(ctx.guild.id)
        mid = str(member.id)
        v.ensure_guild(gid)

        if v.data["permBlocks"][gid].get(mid):
            return await ctx.reply(f"❌ **{member}** is already permanently banned. Use `$unban` first.", mention_author=False)

        expires = int(discord.utils.utcnow().timestamp() + minutes * 60)
        v.data["tempBlocks"][gid][mid] = expires
        v.save_data()

        e = discord.Embed(title=f"{timer} Temporary Ban", color=0xff8800)
        e.description = f"**{member}** is blocked from the generator for **{minutes} minute(s)**."
        e.add_field(name="Banned By", value=str(ctx.author),    inline=True)
        e.add_field(name="Duration",  value=f"{minutes} min",   inline=True)
        e.add_field(name="Expires",   value=f"<t:{expires}:R>", inline=False)
        e.set_footer(text=BOT_NAME)
        await ctx.send(embed=e)

    @commands.command(name='unban')
    @commands.has_permissions(ban_members=True)
    async def unban(self, ctx, member: discord.Member = None):
        """$unban @user — Unblock a user from the generator"""
        cross = self.emoji('cross', '❌')
        unban = self.emoji('unban', '🔓')

        if not member:
            e = discord.Embed(title=f"{cross} Incorrect Usage", color=0xff0000)
            e.description = "**Usage:** `$unban @user`"
            e.set_footer(text=BOT_NAME)
            return await ctx.reply(embed=e, mention_author=False)

        v = self.vouch()
        if not v:
            return await ctx.reply("❌ Vouch system unavailable.", mention_author=False)

        gid = str(ctx.guild.id)
        mid = str(member.id)
        v.ensure_guild(gid)

        perm = v.data["permBlocks"][gid].pop(mid, None)
        temp = v.data["tempBlocks"][gid].pop(mid, None)

        if not perm and not temp:
            return await ctx.reply(f"❌ **{member}** is not currently banned.", mention_author=False)

        v.save_data()

        types = []
        if perm: types.append("Permanent Ban")
        if temp: types.append("Temporary Ban")

        e = discord.Embed(title=f"{unban} User Unbanned", color=0x00ff00)
        e.description = f"**{member}** can now use the generator again."
        e.add_field(name="Unbanned By",   value=str(ctx.author),    inline=True)
        e.add_field(name="Type Removed",  value=" + ".join(types),  inline=True)
        e.set_footer(text=BOT_NAME)
        await ctx.send(embed=e)

    @commands.command(name='bans')
    @commands.has_permissions(ban_members=True)
    async def bans(self, ctx):
        """$bans — List all generator-banned users (admin)"""
        v = self.vouch()
        if not v:
            return await ctx.reply("❌ Vouch system unavailable.", mention_author=False)

        gid = str(ctx.guild.id)
        v.ensure_guild(gid)

        perm_lines = [f"• <@{uid}>" for uid in v.data["permBlocks"][gid]] or ["None"]

        import datetime as _dt
        now_ts = _dt.datetime.now().timestamp()
        temp_lines = [
            f"• <@{uid}> — expires <t:{ts}:R>"
            for uid, ts in v.data["tempBlocks"][gid].items()
            if now_ts <= ts
        ] or ["None"]

        e = discord.Embed(title="🚫 Generator Bans", color=0xff0000)
        e.add_field(name="🔒 Permanent",  value="\n".join(perm_lines), inline=False)
        e.add_field(name="⏱️ Temporary", value="\n".join(temp_lines), inline=False)
        e.set_footer(text=BOT_NAME)
        await ctx.send(embed=e)


async def setup(bot):
    await bot.add_cog(BanCommands(bot))
