import discord
from discord.ext import commands
import json
import os
import datetime
import re
import asyncio

BOT_NAME   = "Storm G3N"
DATA_FILE  = 'data.json'
COUNTDOWN  = 300
BAN_MINUTES = 30

ALLOWED_SERVICES = [
    "mc_bedrock", "xbox", "minecraft", "steam", "cape",
    "mcfa", "crunchyroll", "xbox_codes", "ms_365",
    "xbox_ultimate", "xbox_pc", "crunchyroll_mega", "netflix_cookies"
]


class VouchSystem(commands.Cog):
    def __init__(self, bot):
        self.bot     = bot
        self.data    = {"permBlocks": {}, "tempBlocks": {}, "vouches": {}}
        self.pending = {}
        self.load_data()

        cfg = self.bot.config.get('botConfig', {})
        self.vouch_channel_id  = int(cfg.get('vouchChannelId',           0))
        self.vouch_target_id   = int(cfg.get('vouchTargetId',            0))
        self.failure_log_id    = int(cfg.get('vouchFailureLogChannelId',  0))
        self.appeal_channel_id = int(cfg.get('appealChannelId',          0))

        items_re = "|".join(re.escape(s) for s in ALLOWED_SERVICES)
        self.vouch_regex   = re.compile(
            rf"^Legit\s+got\s+({items_re})\s+by\s+<@!?(\d+)>$", re.I
        )
        self.attempt_regex = re.compile(r"^(vouch|legit|got)\b.*", re.I)

    # ── Data ─────────────────────────────────────

    def emoji(self, name, default=''):
        return self.bot.config.get('emojis', {}).get(name, default)

    def load_data(self):
        if os.path.exists(DATA_FILE):
            try:
                with open(DATA_FILE, 'r') as f:
                    loaded = json.load(f)
                    self.data = loaded
                    # Ensure vouches key exists for old data files
                    self.data.setdefault("vouches", {})
                    return
            except Exception:
                pass
        self.save_data()

    def save_data(self):
        with open(DATA_FILE, 'w') as f:
            json.dump(self.data, f, indent=2)

    def ensure_guild(self, gid):
        gid = str(gid)
        self.data["permBlocks"].setdefault(gid, {})
        self.data["tempBlocks"].setdefault(gid, {})
        self.data["vouches"].setdefault(gid, {})
        self.pending.setdefault(gid, {})

    # ── Block checks ─────────────────────────────

    def is_blocked(self, guild, user_id) -> bool:
        gid = str(guild.id)
        uid = str(user_id)
        self.ensure_guild(gid)
        if self.data["permBlocks"][gid].get(uid):
            return True
        ts = self.data["tempBlocks"][gid].get(uid)
        if ts and datetime.datetime.now().timestamp() <= ts:
            return True
        return False

    # ── Auto vouch message check ──────────────────

    def is_valid_vouch(self, content: str) -> bool:
        m = self.vouch_regex.match(content.strip())
        return bool(m) and int(m.group(2)) == self.vouch_target_id

    async def block_user(self, guild, member, reason: str):
        gid = str(guild.id)
        mid = str(member.id)
        self.ensure_guild(gid)
        if mid in self.data["tempBlocks"][gid]:
            return

        expires_ts = int(
            (datetime.datetime.now() + datetime.timedelta(minutes=BAN_MINUTES)).timestamp()
        )

        embed = discord.Embed(title="🚫 Temporarily Banned", color=0x000000)
        embed.description = f"🔒 {member.mention} has been **temporarily blocked** from the generator."
        embed.add_field(name="📝 Reason",   value=f"> {reason}",              inline=False)
        embed.add_field(name="⏱️ Duration", value=f"> {BAN_MINUTES} minutes", inline=True)
        embed.add_field(name="⏱️ Expires",  value=f"> <t:{expires_ts}:R>",    inline=True)
        embed.add_field(name="📝 Appeal",   value=f"> <#{self.appeal_channel_id}>", inline=False)
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.set_footer(text=BOT_NAME)

        log_ch = self.bot.get_channel(self.failure_log_id)
        if log_ch:
            await log_ch.send(content=member.mention, embed=embed)
        try:
            await member.send(embed=embed)
        except Exception:
            pass

        self.data["tempBlocks"][gid][mid] = expires_ts
        self.save_data()

        await asyncio.sleep(BAN_MINUTES * 60)
        if self.data["tempBlocks"].get(gid, {}).get(mid) == expires_ts:
            del self.data["tempBlocks"][gid][mid]
            self.save_data()
            unban_embed = discord.Embed(
                title="🔓 Ban Expired",
                description=f"🎉 {member.mention} can use the generator again.",
                color=0x00ff80
            )
            unban_embed.set_footer(text=BOT_NAME)
            if log_ch:
                await log_ch.send(content=member.mention, embed=unban_embed)
            try:
                await member.send(embed=unban_embed)
            except Exception:
                pass

    def register_pending(self, guild, member):
        gid = str(guild.id)
        mid = str(member.id)
        self.ensure_guild(gid)
        old = self.pending[gid].get(mid)
        if old and not old.done():
            old.cancel()

        async def countdown():
            await asyncio.sleep(COUNTDOWN)
            if self.pending.get(gid, {}).get(mid):
                asyncio.create_task(
                    self.block_user(guild, member, "Did not vouch after generating an account")
                )
                self.pending[gid].pop(mid, None)

        self.pending[gid][mid] = asyncio.create_task(countdown())

    async def handle_message(self, message):
        if message.author.bot or not message.guild:
            return
        if message.channel.id != self.vouch_channel_id:
            return

        gid = str(message.guild.id)
        mid = str(message.author.id)
        self.ensure_guild(gid)
        content = message.content.strip()

        looks_like = self.attempt_regex.match(content)
        valid      = self.is_valid_vouch(content)

        if looks_like and not valid:
            try:
                await message.delete()
            except Exception:
                pass
            await message.channel.send(
                f"{message.author.mention} ❌ Invalid vouch format.\n"
                f"Correct format: `Legit got <service> by <@{self.vouch_target_id}>`",
                delete_after=8
            )
            return

        if valid and mid in self.pending.get(gid, {}):
            task = self.pending[gid].pop(mid, None)
            if task and not task.done():
                task.cancel()
            await message.add_reaction('✅')

    # ── $vouch command ───────────────────────────

    @commands.command(name='vouch')
    async def vouch_cmd(self, ctx, member: discord.Member = None, *, reason: str = None):
        """$vouch @user <reason> — Vouch for a member"""
        cross  = self.emoji('cross',  '❌')
        star   = self.emoji('star',   '⭐')
        tick   = self.emoji('tick',   '✅')

        # Usage check
        if not member or not reason:
            e = discord.Embed(title=f"{cross} Incorrect Usage", color=0xff0000)
            e.description = (
                "**Usage:** `$vouch @user <reason>`\n\n"
                "**Example:** `$vouch @JohnDoe Great seller, fast delivery!`"
            )
            e.set_footer(text=BOT_NAME)
            return await ctx.reply(embed=e, mention_author=False)

        # Can't vouch yourself
        if member.id == ctx.author.id:
            e = discord.Embed(title=f"{cross} Not Allowed", color=0xff0000)
            e.description = "You cannot vouch for yourself."
            e.set_footer(text=BOT_NAME)
            return await ctx.reply(embed=e, mention_author=False)

        # Can't vouch a bot
        if member.bot:
            e = discord.Embed(title=f"{cross} Not Allowed", color=0xff0000)
            e.description = "You cannot vouch for a bot."
            e.set_footer(text=BOT_NAME)
            return await ctx.reply(embed=e, mention_author=False)

        gid = str(ctx.guild.id)
        mid = str(member.id)
        self.ensure_guild(gid)

        # Save vouch
        now = datetime.datetime.now()
        entry = {
            "from_id":   str(ctx.author.id),
            "from_name": str(ctx.author),
            "reason":    reason,
            "timestamp": now.isoformat()
        }
        if mid not in self.data["vouches"][gid]:
            self.data["vouches"][gid][mid] = []
        self.data["vouches"][gid][mid].append(entry)
        self.save_data()

        total = len(self.data["vouches"][gid][mid])

        # Public vouch embed
        vouch_channel = self.bot.get_channel(self.vouch_channel_id) or ctx.channel
        e = discord.Embed(
            title=f"⭐ New Vouch — {member.display_name}",
            color=0xf1c40f
        )
        e.add_field(name="👤 Vouched For", value=member.mention,       inline=True)
        e.add_field(name="✍️ Vouched By",  value=ctx.author.mention,   inline=True)
        e.add_field(name="📊 Total Vouches", value=f"**{total}**",     inline=True)
        e.add_field(name="📝 Reason",      value=reason,               inline=False)
        e.set_thumbnail(url=member.display_avatar.url)
        e.set_footer(text=f"{BOT_NAME} • {now.strftime('%Y-%m-%d %H:%M')}")

        # Post in vouch channel if different from current channel
        if vouch_channel and vouch_channel.id != ctx.channel.id:
            await vouch_channel.send(embed=e)
            confirm = discord.Embed(color=0x2ecc71)
            confirm.description = f"{tick} Vouch submitted for {member.mention} in <#{vouch_channel.id}>!"
            confirm.set_footer(text=BOT_NAME)
            await ctx.reply(embed=confirm, mention_author=False)
        else:
            await ctx.send(embed=e)

    # ── $vouches command ─────────────────────────

    @commands.command(name='vouches')
    async def vouches_cmd(self, ctx, member: discord.Member = None):
        """$vouches @user — View all vouches for a member"""
        cross = self.emoji('cross', '❌')

        if not member:
            member = ctx.author

        gid  = str(ctx.guild.id)
        mid  = str(member.id)
        self.ensure_guild(gid)

        entries = self.data["vouches"][gid].get(mid, [])

        if not entries:
            e = discord.Embed(title="📭 No Vouches", color=0x888888)
            e.description = f"**{member.display_name}** has no vouches yet."
            e.set_footer(text=BOT_NAME)
            return await ctx.reply(embed=e, mention_author=False)

        # Show last 10 vouches
        shown    = entries[-10:]
        lines    = []
        for v in reversed(shown):
            ts   = datetime.datetime.fromisoformat(v["timestamp"])
            lines.append(
                f"⭐ **{v['from_name']}** — {v['reason']}\n"
                f"  *(on {ts.strftime('%Y-%m-%d')})*"
            )

        e = discord.Embed(
            title=f"⭐ Vouches for {member.display_name}",
            color=0xf1c40f
        )
        e.description = "\n\n".join(lines)
        e.set_thumbnail(url=member.display_avatar.url)
        e.set_footer(text=f"{BOT_NAME} • Total: {len(entries)} vouch(es)")
        await ctx.reply(embed=e, mention_author=False)

    # ── $clearvouch command ──────────────────────

    @commands.command(name='clearvouch')
    @commands.has_permissions(administrator=True)
    async def clearvouch_cmd(self, ctx, member: discord.Member = None):
        """$clearvouch @user — Clear all vouches for a member (admin)"""
        cross = self.emoji('cross', '❌')
        tick  = self.emoji('tick',  '✅')

        if not member:
            e = discord.Embed(title=f"{cross} Incorrect Usage", color=0xff0000)
            e.description = "**Usage:** `$clearvouch @user`"
            e.set_footer(text=BOT_NAME)
            return await ctx.reply(embed=e, mention_author=False)

        gid = str(ctx.guild.id)
        mid = str(member.id)
        self.ensure_guild(gid)

        count = len(self.data["vouches"][gid].get(mid, []))
        self.data["vouches"][gid][mid] = []
        self.save_data()

        e = discord.Embed(title=f"{tick} Vouches Cleared", color=0x00ff00)
        e.description = f"Cleared **{count}** vouch(es) for {member.mention}."
        e.set_footer(text=BOT_NAME)
        await ctx.reply(embed=e, mention_author=False)

    # ── Admin commands ───────────────────────────

    @commands.command(name='setbantime')
    @commands.has_permissions(administrator=True)
    async def setbantime(self, ctx, minutes: int = None):
        """$setbantime <minutes> — Set auto-ban duration (admin)"""
        global BAN_MINUTES
        cross = self.emoji('cross', '❌')
        if not minutes or minutes <= 0:
            e = discord.Embed(title=f"{cross} Incorrect Usage", color=0xff0000)
            e.description = "**Usage:** `$setbantime <minutes>`"
            e.set_footer(text=BOT_NAME)
            return await ctx.reply(embed=e, mention_author=False)

        BAN_MINUTES = minutes
        e = discord.Embed(title="✅ Ban Duration Updated", color=0x00ff00)
        e.description = f"Auto-ban duration is now **{minutes} minute(s)**."
        e.set_footer(text=BOT_NAME)
        await ctx.reply(embed=e, mention_author=False)

    @commands.command(name='pending')
    @commands.has_permissions(administrator=True)
    async def show_pending(self, ctx):
        """$pending — Show users who haven't vouched yet (admin)"""
        gid = str(ctx.guild.id)
        self.ensure_guild(gid)
        users = self.pending.get(gid, {})

        if not users:
            return await ctx.reply("✅ No one is pending a vouch.", mention_author=False)

        lines = [
            f"• {ctx.guild.get_member(int(uid)).mention if ctx.guild.get_member(int(uid)) else f'<@{uid}>'}"
            for uid in users
        ]
        e = discord.Embed(title="⏳ Pending Vouches", color=0xffaa00)
        e.description = "\n".join(lines)
        e.set_footer(text=BOT_NAME)
        await ctx.reply(embed=e, mention_author=False)


async def setup(bot):
    await bot.add_cog(VouchSystem(bot))
