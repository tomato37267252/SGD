import discord
from discord.ext import commands
import os
import json
import datetime

BOT_NAME = "Storm G3N"

SERVICES = {
    "free": {
        "config_key": "genChannelId",
        "services": {
            "minecraft":       "stock/Minecraft.txt",
            "steam":           "stock/Steam.txt",
            "crunchyroll":     "stock/Crunchyroll.txt",
            "mc_bedrock":      "stock/Mc_Bedrock.txt",
            "xbox":            "stock/Xbox.txt",
            "cape":            "stock/Cape.txt",
            "xbox_codes":      "stock/XboxCodes.txt",
            "ms_365":          "stock/MS365.txt",
        }
    },
    "booster": {
        "config_key": "boosterChannelId",
        "services": {
            "xbox_ultimate":      "bosststock/XboxUltimate.txt",
            "xbox_pc":            "bosststock/XboxPC.txt",
            "crunchyroll_mega":   "bosststock/CrunchyrollMega.txt",
            "netflix_cookies":    "bosststock/NetflixCookies.txt",
        }
    },
    "vip": {
        "config_key": "vipChannelId",
        "services": {
            "mcfa": "paidstock/Mcfa.txt",
        }
    }
}


class GenerationCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        cfg = self.bot.config.get('botConfig', {})
        self.channel_ids = {
            tier: int(cfg.get(data["config_key"], 0))
            for tier, data in SERVICES.items()
        }
        self.gen_access_role_id = int(cfg.get('genAccessRoleId', 0))
        # Load extra free/booster services persisted via $freeadd / $boostadd
        self._load_vault_extras()

    def _load_vault_extras(self):
        """Inject services added via $freeadd/$boostadd into SERVICES at startup."""
        vault_extra_file = "vault_extra.json"
        if not os.path.exists(vault_extra_file):
            return
        try:
            with open(vault_extra_file, 'r') as f:
                extras = json.load(f)
            for label, path in extras.get("free", {}).items():
                key = label.lower().replace(' ', '_').replace('-', '_')
                SERVICES["free"]["services"].setdefault(key, path)
            for label, path in extras.get("booster", {}).items():
                key = label.lower().replace(' ', '_').replace('-', '_')
                SERVICES["booster"]["services"].setdefault(key, path)
        except Exception:
            pass

    def emoji(self, name, default=''):
        return self.bot.config.get('emojis', {}).get(name, default)

    def get_account(self, file_path):
        if not os.path.exists(file_path):
            return None
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                lines = [l for l in f.read().splitlines() if l.strip()]
            if not lines:
                return None
            account = lines.pop(0)
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write('\n'.join(lines) + ('\n' if lines else ''))
            return account
        except Exception:
            return None

    def has_gen_access(self, member):
        if not self.gen_access_role_id:
            return True
        return any(r.id == self.gen_access_role_id for r in member.roles)

    async def run_gen(self, ctx, tier, service_name):
        tier_data  = SERVICES[tier]
        channel_id = self.channel_ids[tier]

        cross   = self.emoji('cross',      '❌')
        arrow   = self.emoji('arrow_arrow','➡️')
        excl    = self.emoji('red_excl',   '🚨')
        star    = self.emoji('s_yellow',   '⭐')
        mail    = self.emoji('mail',       '📧')
        pwd     = self.emoji('password',   '🔑')
        success = self.emoji('success',    '✅')
        upload  = self.emoji('upload',     '📤')
        lock    = self.emoji('lock_key',   '🔒')

        # Wrong channel
        if ctx.channel.id != channel_id:
            e = discord.Embed(title=f"{cross} Wrong Channel", color=0xff0000)
            e.description = f"{arrow} Please use this command in <#{channel_id}>."
            e.set_footer(text=BOT_NAME)
            return await ctx.reply(embed=e, mention_author=False)

        # G3N Access role check (free tier only)
        if tier == "free" and not self.has_gen_access(ctx.author):
            e = discord.Embed(title=f"{lock} Access Denied", color=0xff0000)
            e.description = (
                f"{arrow} You need the **G3N Access** role to use the free generator.\n\n"
                f"**How to get it:** Set `.gg/MetalDrops` as your Discord Custom Status "
                f"and run `$cstatus`!"
            )
            e.set_footer(text=BOT_NAME)
            return await ctx.reply(embed=e, mention_author=False)

        # Missing service
        if not service_name:
            available = ', '.join(f'`{s}`' for s in tier_data["services"])
            e = discord.Embed(title=f"{cross} Missing Service", color=0xff0000)
            e.description = f"{arrow} Please specify a service.\nAvailable: {available}\nSee `$stock` for quantities."
            e.set_footer(text=BOT_NAME)
            return await ctx.reply(embed=e, mention_author=False)

        service_name = service_name.lower()
        file_path    = tier_data["services"].get(service_name)

        # Unknown service
        if not file_path:
            available = ', '.join(f'`{s}`' for s in tier_data["services"])
            e = discord.Embed(title=f"{excl} Unknown Service", color=0xff0000)
            e.description = f"{arrow} Available services for this tier: {available}"
            e.set_footer(text=BOT_NAME)
            return await ctx.reply(embed=e, mention_author=False)

        # Banned user
        vouch = self.bot.get_cog('VouchSystem')
        if vouch and vouch.is_blocked(ctx.guild, ctx.author.id):
            appeal_ch = self.bot.config.get('botConfig', {}).get('appealChannelId', 0)
            e = discord.Embed(title=f"{cross} Access Blocked", color=0xff0000)
            e.description = (
                f"{arrow} You are temporarily blocked from the generator.\n"
                f"**Reason:** You did not vouch in time.\n"
                f"**Appeal:** <#{appeal_ch}>"
            )
            e.set_footer(text=BOT_NAME)
            return await ctx.reply(embed=e, mention_author=False)

        # Get account
        account = self.get_account(file_path)
        if not account:
            e = discord.Embed(title=f"{excl} Out of Stock", color=0xff0000)
            e.description = f"{arrow} This service is currently out of stock. Check back later!"
            e.set_footer(text=BOT_NAME)
            return await ctx.reply(embed=e, mention_author=False)

        # Register vouch requirement
        if vouch:
            vouch.pending.setdefault(str(ctx.guild.id), {})[str(ctx.author.id)] = {
                "time": datetime.datetime.now(),
                "service": service_name
            }

        # Send DM
        try:
            parts    = account.split(':', 1)
            vouch_ch = self.bot.config.get('botConfig', {}).get('vouchChannelId', 0)
            dm = discord.Embed(title=f"{star} Your Account is Ready! {star}", color=0x00ff00)
            if len(parts) == 2:
                dm.add_field(name=f"{mail} Email",    value=f"||`{parts[0]}`||", inline=True)
                dm.add_field(name=f"{pwd} Password",  value=f"||`{parts[1]}`||", inline=True)
            dm.add_field(name=f"{star} Full Combo", value=f"||```\n{account}\n```||", inline=False)
            dm.add_field(
                name="🚨 Vouch Required",
                value=f"Please vouch in <#{vouch_ch}> or you will be blocked from the generator!",
                inline=False
            )
            dm.set_footer(text=BOT_NAME)
            await ctx.author.send(embed=dm)
        except discord.Forbidden:
            e = discord.Embed(title=f"{excl} DMs Closed", color=0xff0000)
            e.description = f"{arrow} Could not send your account via DM. Please open your DMs and try again."
            e.set_footer(text=BOT_NAME)
            return await ctx.reply(embed=e, mention_author=False)

        # Public confirmation
        pub = discord.Embed(title=f"{success} Account Generated!", color=0x00ff00)
        pub.description = (
            f"{upload} Your account has been sent to your DMs.\n\n"
            f"{star} Service: **{service_name}**\n"
            f"{star} Generated by: {ctx.author.mention}\n\n"
            f"⚠️ Don't forget to vouch or you will be blocked!"
        )
        pub.set_footer(text=BOT_NAME)
        await ctx.reply(embed=pub, mention_author=False)

        # Refresh live stock message
        inv = self.bot.get_cog('InventoryCommands')
        if inv:
            await inv.refresh_stock_message(ctx.guild.id)

    @commands.command(name='free')
    async def free(self, ctx, service: str = None):
        """$free <service> — Generate a free tier account (requires G3N Access role)"""
        await self.run_gen(ctx, "free", service)

    @commands.command(name='boost')
    async def boost(self, ctx, service: str = None):
        """$boost <service> — Generate a booster tier account"""
        await self.run_gen(ctx, "booster", service)

    @commands.command(name='custom')
    async def custom(self, ctx, service: str = None):
        """$custom <service> — Generate from a custom vault service"""
        cross  = self.emoji('cross',      '❌')
        excl   = self.emoji('red_excl',   '🚨')
        star   = self.emoji('s_yellow',   '⭐')
        mail   = self.emoji('mail',       '📧')
        pwd    = self.emoji('password',   '🔑')
        success= self.emoji('success',    '✅')
        upload = self.emoji('upload',     '📤')
        arrow  = self.emoji('arrow_arrow','➡️')

        inv = self.bot.get_cog('InventoryCommands')
        if not inv:
            return await ctx.reply("❌ Inventory system unavailable.", mention_author=False)

        if not service:
            if inv.dynamic:
                available = ', '.join(f'`{s}`' for s in inv.dynamic)
                e = discord.Embed(title=f"{cross} Missing Service", color=0xff0000)
                e.description = f"{arrow} Available custom services: {available}"
            else:
                e = discord.Embed(title=f"{cross} No Custom Services", color=0xff0000)
                e.description = f"{arrow} No custom services exist yet. An owner can add one with `$genadd`."
            e.set_footer(text=BOT_NAME)
            return await ctx.reply(embed=e, mention_author=False)

        service_key = service.lower().replace('-', '_')
        file_path   = inv.dynamic.get(service_key)

        if not file_path:
            available = ', '.join(f'`{s}`' for s in inv.dynamic) or 'None'
            e = discord.Embed(title=f"{excl} Unknown Service", color=0xff0000)
            e.description = f"{arrow} Available custom services: {available}"
            e.set_footer(text=BOT_NAME)
            return await ctx.reply(embed=e, mention_author=False)

        # Banned check
        vouch = self.bot.get_cog('VouchSystem')
        if vouch and vouch.is_blocked(ctx.guild, ctx.author.id):
            appeal_ch = self.bot.config.get('botConfig', {}).get('appealChannelId', 0)
            e = discord.Embed(title=f"{cross} Access Blocked", color=0xff0000)
            e.description = (
                f"{arrow} You are temporarily blocked from the generator.\n"
                f"**Appeal:** <#{appeal_ch}>"
            )
            e.set_footer(text=BOT_NAME)
            return await ctx.reply(embed=e, mention_author=False)

        account = self.get_account(file_path)
        if not account:
            e = discord.Embed(title=f"{excl} Out of Stock", color=0xff0000)
            e.description = f"{arrow} `{service_key}` is currently out of stock."
            e.set_footer(text=BOT_NAME)
            return await ctx.reply(embed=e, mention_author=False)

        # Send DM
        try:
            parts    = account.split(':', 1)
            vouch_ch = self.bot.config.get('botConfig', {}).get('vouchChannelId', 0)
            dm = discord.Embed(title=f"{star} Your Item is Ready! {star}", color=0x00ff00)
            if len(parts) == 2:
                dm.add_field(name=f"{mail} Email",   value=f"||`{parts[0]}`||", inline=True)
                dm.add_field(name=f"{pwd} Password", value=f"||`{parts[1]}`||", inline=True)
            dm.add_field(name=f"{star} Full", value=f"||```\n{account}\n```||", inline=False)
            dm.add_field(name="🚨 Vouch Required", value=f"Vouch in <#{vouch_ch}> or you'll be blocked!", inline=False)
            dm.set_footer(text=BOT_NAME)
            await ctx.author.send(embed=dm)
        except discord.Forbidden:
            e = discord.Embed(title=f"{excl} DMs Closed", color=0xff0000)
            e.description = f"{arrow} Open your DMs and try again."
            e.set_footer(text=BOT_NAME)
            return await ctx.reply(embed=e, mention_author=False)

        pub = discord.Embed(title=f"{success} Generated!", color=0x00ff00)
        pub.description = (
            f"{upload} Sent to your DMs.\n\n"
            f"{star} Service: **{service_key}**\n"
            f"{star} By: {ctx.author.mention}\n\n"
            f"⚠️ Don't forget to vouch!"
        )
        pub.set_footer(text=BOT_NAME)
        await ctx.reply(embed=pub, mention_author=False)

        # Refresh live stock message
        if inv:
            await inv.refresh_stock_message(ctx.guild.id)

    @commands.command(name='vip')
    async def vip(self, ctx, service: str = None):
        """$vip <service> — Generate a VIP tier account"""
        await self.run_gen(ctx, "vip", service)


async def setup(bot):
    await bot.add_cog(GenerationCommands(bot))
