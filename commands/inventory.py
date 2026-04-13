import discord
from discord.ext import commands
import os
import re
import json
import aiohttp
from commands.generation import SERVICES

BOT_NAME = "Storm G3N"

NO_FILTER_SERVICES = {"netflix_cookies", "xbox_codes", "ms_365", "steam"}

STOCK_PATHS = {
    "🆓 Free Vault": {
        "Minecraft":   "stock/Minecraft.txt",
        "Steam":       "stock/Steam.txt",
        "Crunchyroll": "stock/Crunchyroll.txt",
        "Mc_Bedrock":  "stock/Mc_Bedrock.txt",
        "Xbox":        "stock/Xbox.txt",
        "Cape":        "stock/Cape.txt",
        "Xbox_Codes":  "stock/XboxCodes.txt",
        "MS_365":      "stock/MS365.txt",
    },
    "🚀 Booster Vault": {
        "Xbox_Ultimate":    "bosststock/XboxUltimate.txt",
        "Xbox_PC":          "bosststock/XboxPC.txt",
        "Crunchyroll_Mega": "bosststock/CrunchyrollMega.txt",
        "Netflix_Cookies":  "bosststock/NetflixCookies.txt",
    },
    "💎 Premium Vault": {
        "Mcfa": "paidstock/Mcfa.txt",
    }
}

DYNAMIC_FILE     = "dynamic_stock.json"
STOCK_MSG_FILE   = "stock_message.json"  # stores {guild_id: {channel_id, message_id}}
VAULT_EXTRA_FILE = "vault_extra.json"    # extra services added via $freeadd / $boostadd


def load_dynamic():
    if os.path.exists(DYNAMIC_FILE):
        try:
            with open(DYNAMIC_FILE, 'r') as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_dynamic(data):
    with open(DYNAMIC_FILE, 'w') as f:
        json.dump(data, f, indent=2)


def load_vault_extra():
    if os.path.exists(VAULT_EXTRA_FILE):
        try:
            with open(VAULT_EXTRA_FILE, 'r') as f:
                return json.load(f)
        except Exception:
            pass
    return {"free": {}, "booster": {}}


def save_vault_extra(data):
    with open(VAULT_EXTRA_FILE, 'w') as f:
        json.dump(data, f, indent=2)


def load_stock_messages():
    if os.path.exists(STOCK_MSG_FILE):
        try:
            with open(STOCK_MSG_FILE, 'r') as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_stock_messages(data):
    with open(STOCK_MSG_FILE, 'w') as f:
        json.dump(data, f, indent=2)


def extract_email_pass(text: str) -> list:
    pattern = re.compile(r'^[a-zA-Z0-9_.+\-]+@[a-zA-Z0-9\-]+\.[a-zA-Z]{2,}:.+$')
    return [l.strip() for l in text.splitlines()
            if l.strip() and pattern.match(l.strip())]


class InventoryCommands(commands.Cog):
    def __init__(self, bot):
        self.bot            = bot
        self.dynamic        = load_dynamic()
        self.stock_messages = load_stock_messages()  # {guild_id: {channel_id, message_id}}
        # Load and inject extra free/booster services added via $freeadd / $boostadd
        vault_extra = load_vault_extra()
        for name, path in vault_extra.get("free", {}).items():
            STOCK_PATHS["🆓 Free Vault"][name] = path
        for name, path in vault_extra.get("booster", {}).items():
            STOCK_PATHS["🚀 Booster Vault"][name] = path

    def emoji(self, name, default='📦'):
        return self.bot.config.get('emojis', {}).get(name, default)

    def is_owner(self, member):
        cfg           = self.bot.config.get('botConfig', {})
        owner_role_id = int(cfg.get('ownerRoleId', 0))
        if not owner_role_id:
            return member.guild_permissions.administrator
        return any(r.id == owner_role_id for r in member.roles)

    def count(self, path):
        try:
            if not os.path.exists(path):
                return 0
            with open(path, 'r', encoding='utf-8') as f:
                return len([l for l in f.read().splitlines() if l.strip()])
        except Exception:
            return 0

    def find_static_service(self, service: str):
        key = service.lower().replace('-', '_')
        for vault_name, vault_services in STOCK_PATHS.items():
            for sname, spath in vault_services.items():
                if sname.lower() == key:
                    return sname, spath, vault_name
        return None, None, None

    def build_stock_embed(self):
        """Build the stock embed — used for both $stock and live refresh."""
        warden = self.emoji('warden', '🛡️')
        embed  = discord.Embed(title=f"{warden} Storm G3N — Live Inventory", color=0x001000)
        embed.description = "```Stock updates automatically on every change```"

        for vault, services in STOCK_PATHS.items():
            lines = ""
            for name, path in services.items():
                n   = self.count(path)
                bar = "🟢" if n > 10 else ("🟡" if n > 0 else "🔴")
                lines += f"{bar} `{name:<22}` → **{n}** units\n"
            embed.add_field(name=vault, value=lines or "Empty", inline=False)

        if self.dynamic:
            lines = ""
            for key, data in self.dynamic.items():
                n     = self.count(data["path"])
                bar   = "🟢" if n > 10 else ("🟡" if n > 0 else "🔴")
                label = data.get("label", key)
                extra = ""
                if data.get("channel_id"):
                    extra += f" · <#{data['channel_id']}>"
                if data.get("role_id"):
                    extra += f" · <@&{data['role_id']}>"
                lines += f"{bar} `{label:<22}` → **{n}** units{extra}\n"
            embed.add_field(name="⚙️ Custom Vault", value=lines, inline=False)

        import datetime
        embed.set_footer(text=f"{BOT_NAME} • Last updated: {datetime.datetime.utcnow().strftime('%H:%M:%S UTC')}")
        return embed

    async def refresh_stock_message(self, guild_id: int):
        """Edit the pinned live-stock message if one exists for this guild."""
        gid  = str(guild_id)
        info = self.stock_messages.get(gid)
        if not info:
            return
        try:
            ch  = self.bot.get_channel(int(info["channel_id"]))
            if not ch:
                return
            msg = await ch.fetch_message(int(info["message_id"]))
            await msg.edit(embed=self.build_stock_embed())
        except discord.NotFound:
            # Message was deleted — clean up
            self.stock_messages.pop(gid, None)
            save_stock_messages(self.stock_messages)
        except Exception as e:
            print(f"[{BOT_NAME}] refresh_stock_message error: {e}")

    # ── $stock ───────────────────────────────────

    @commands.command(name='stock')
    async def stock(self, ctx):
        """$stock — View live stock"""
        await ctx.send(embed=self.build_stock_embed())

    # ── $stocklive — pin a live-updating message ─

    @commands.command(name='stocklive')
    @commands.has_permissions(administrator=True)
    async def stocklive(self, ctx):
        """$stocklive — Pin a live stock message in this channel that auto-updates (admin)"""
        tick  = self.emoji('tick',  '✅')
        cross = self.emoji('cross', '❌')
        gid   = str(ctx.guild.id)

        # Delete old one if exists
        old = self.stock_messages.get(gid)
        if old:
            try:
                old_ch  = self.bot.get_channel(int(old["channel_id"]))
                old_msg = await old_ch.fetch_message(int(old["message_id"]))
                await old_msg.delete()
            except Exception:
                pass

        msg = await ctx.send(embed=self.build_stock_embed())
        try:
            await msg.pin()
        except Exception:
            pass

        self.stock_messages[gid] = {
            "channel_id": str(ctx.channel.id),
            "message_id": str(msg.id)
        }
        save_stock_messages(self.stock_messages)

        e = discord.Embed(title=f"{tick} Live Stock Message Set!", color=0x00ff00)
        e.description = (
            "This message will automatically update whenever stock changes\n"
            "(restock, generation, removestock, genadd, genremove)."
        )
        e.set_footer(text=BOT_NAME)
        confirm = await ctx.send(embed=e)
        # Auto-delete confirm after 10s to keep channel clean
        import asyncio
        await asyncio.sleep(10)
        try:
            await confirm.delete()
            await ctx.message.delete()
        except Exception:
            pass

    # ── $restock ─────────────────────────────────

    @commands.command(name='restock')
    @commands.has_permissions(administrator=True)
    async def restock(self, ctx, vault: str = None, service: str = None):
        tick  = self.emoji('tick',  '✅')
        cross = self.emoji('cross', '❌')

        if not vault or not service:
            e = discord.Embed(title=f"{cross} Incorrect Usage", color=0xff0000)
            e.description = (
                "**Usage:** `$restock <vault> <service>` + attach `.txt`\n\n"
                "**Vaults:** `free` | `booster` | `premium` | `custom`"
            )
            e.set_footer(text=BOT_NAME)
            return await ctx.reply(embed=e, mention_author=False)

        vault_map = {
            "free":    "🆓 Free Vault",
            "booster": "🚀 Booster Vault",
            "premium": "💎 Premium Vault",
        }

        if vault.lower() == "custom":
            key  = service.lower().replace('-', '_')
            data = self.dynamic.get(key)
            if not data:
                available = ', '.join(f'`{k}`' for k in self.dynamic) or 'None'
                e = discord.Embed(title=f"{cross} Unknown Custom Service", color=0xff0000)
                e.description = f"Available custom services: {available}"
                e.set_footer(text=BOT_NAME)
                return await ctx.reply(embed=e, mention_author=False)
            service_path = data["path"]
            do_filter    = data.get("filter", True)
            display_name = data.get("label", key)
        else:
            vault_key = vault_map.get(vault.lower())
            if not vault_key:
                e = discord.Embed(title=f"{cross} Unknown Vault", color=0xff0000)
                e.description = "Valid vaults: `free`, `booster`, `premium`, `custom`"
                e.set_footer(text=BOT_NAME)
                return await ctx.reply(embed=e, mention_author=False)

            service_path = None
            display_name = service
            for sname, spath in STOCK_PATHS[vault_key].items():
                if sname.lower() == service.lower().replace('-', '_'):
                    service_path = spath
                    display_name = sname
                    break

            if not service_path:
                available = ', '.join(f'`{s}`' for s in STOCK_PATHS[vault_key])
                e = discord.Embed(title=f"{cross} Unknown Service", color=0xff0000)
                e.description = f"Available in **{vault_key}**: {available}"
                e.set_footer(text=BOT_NAME)
                return await ctx.reply(embed=e, mention_author=False)

            do_filter = display_name.lower() not in NO_FILTER_SERVICES

        if not ctx.message.attachments:
            e = discord.Embed(title=f"{cross} Missing File", color=0xff0000)
            e.description = "Attach a `.txt` file."
            e.set_footer(text=BOT_NAME)
            return await ctx.reply(embed=e, mention_author=False)

        att = ctx.message.attachments[0]
        if not att.filename.endswith('.txt'):
            e = discord.Embed(title=f"{cross} Wrong Format", color=0xff0000)
            e.description = "File must be `.txt`."
            e.set_footer(text=BOT_NAME)
            return await ctx.reply(embed=e, mention_author=False)

        async with aiohttp.ClientSession() as session:
            async with session.get(att.url) as r:
                raw = await r.text(encoding='utf-8', errors='ignore')

        if do_filter:
            lines = extract_email_pass(raw)
            total = len([l for l in raw.splitlines() if l.strip()])
            note  = f"*(filtered {len(lines)}/{total} valid `email:password` lines)*"
        else:
            lines = [l.strip() for l in raw.splitlines() if l.strip()]
            note  = "*(raw — no filter applied)*"

        if not lines:
            e = discord.Embed(title=f"{cross} No Valid Entries", color=0xff0000)
            e.description = "No valid lines found in the file."
            e.set_footer(text=BOT_NAME)
            return await ctx.reply(embed=e, mention_author=False)

        folder = os.path.dirname(service_path)
        if folder:
            os.makedirs(folder, exist_ok=True)
        with open(service_path, 'a', encoding='utf-8') as f:
            f.write('\n'.join(lines) + '\n')

        restock_ch = int(self.bot.config.get('botConfig', {}).get('restockChannelId', 0))
        if restock_ch:
            ch = self.bot.get_channel(restock_ch)
            if ch:
                ann = discord.Embed(
                    title="🔄 Restock Alert!",
                    description=f"**{display_name}** restocked with **{len(lines)}** entries! {note}",
                    color=0x00ff00
                )
                ann.set_footer(text=BOT_NAME)
                await ch.send(embed=ann)

        e = discord.Embed(title=f"{tick} Restock Successful!", color=0x00ff00)
        e.description = f"**{len(lines)}** entries added to `{display_name}`. {note}"
        e.set_footer(text=BOT_NAME)
        await ctx.reply(embed=e, mention_author=False)

        # Refresh live stock message
        await self.refresh_stock_message(ctx.guild.id)

    # ── $removestock ─────────────────────────────

    @commands.command(name='removestock')
    @commands.has_permissions(administrator=True)
    async def removestock(self, ctx, service: str = None):
        tick  = self.emoji('tick',  '✅')
        cross = self.emoji('cross', '❌')

        if not service:
            e = discord.Embed(title=f"{cross} Incorrect Usage", color=0xff0000)
            e.description = "**Usage:** `$removestock <service>` or `$removestock all`"
            e.set_footer(text=BOT_NAME)
            return await ctx.reply(embed=e, mention_author=False)

        paths = []
        if service.lower() == 'all':
            for vs in STOCK_PATHS.values():
                paths.extend(vs.values())
            for d in self.dynamic.values():
                paths.append(d["path"])
        else:
            _, spath, _ = self.find_static_service(service)
            if spath:
                paths.append(spath)
            else:
                key = service.lower().replace('-', '_')
                if key in self.dynamic:
                    paths.append(self.dynamic[key]["path"])

        if not paths:
            e = discord.Embed(title=f"{cross} Not Found", color=0xff0000)
            e.description = f"No stock file found for `{service}`."
            e.set_footer(text=BOT_NAME)
            return await ctx.reply(embed=e, mention_author=False)

        for p in paths:
            if os.path.exists(p):
                with open(p, 'w', encoding='utf-8') as f:
                    f.truncate(0)

        e = discord.Embed(title=f"{tick} Stock Cleared", color=0x00ff00)
        e.description = f"**{len(paths)}** file(s) cleared."
        e.set_footer(text=BOT_NAME)
        await ctx.reply(embed=e, mention_author=False)

        await self.refresh_stock_message(ctx.guild.id)

    # ── $genadd ──────────────────────────────────

    @commands.command(name='genadd')
    async def genadd(self, ctx, service: str = None, *, options: str = ""):
        """$genadd <name> [channel:#ch] [role:@role] [filter:no] — Add custom service (owner)"""
        cross = self.emoji('cross', '❌')
        tick  = self.emoji('tick',  '✅')

        if not self.is_owner(ctx.author):
            e = discord.Embed(title=f"{cross} Access Denied", color=0xff0000)
            e.description = "This command is reserved for **Owners** only."
            e.set_footer(text=BOT_NAME)
            return await ctx.reply(embed=e, mention_author=False)

        if not service:
            e = discord.Embed(title=f"{cross} Incorrect Usage", color=0xff0000)
            e.description = (
                "**Usage:** `$genadd <name> [options]`\n\n"
                "**Options (all optional):**\n"
                "`channel:#channel` → restrict generation to a specific channel\n"
                "`role:@Role` → require a role to generate\n"
                "`filter:no` → skip email:pass filter (for cookies, codes, etc.)\n\n"
                "**Examples:**\n"
                "`$genadd CC`\n"
                "`$genadd Spotify channel:#gen-spotify role:@VIP filter:yes`\n"
                "`$genadd NetflixCookies filter:no`"
            )
            e.set_footer(text=BOT_NAME)
            return await ctx.reply(embed=e, mention_author=False)

        key = service.lower().replace(' ', '_').replace('-', '_')

        if key in self.dynamic:
            e = discord.Embed(title=f"{cross} Already Exists", color=0xff0000)
            e.description = f"`{key}` already exists. Use `$genremove {key}` first to recreate it."
            e.set_footer(text=BOT_NAME)
            return await ctx.reply(embed=e, mention_author=False)

        channel_id = ctx.message.channel_mentions[0].id if ctx.message.channel_mentions else 0
        role_id    = ctx.message.role_mentions[0].id    if ctx.message.role_mentions    else 0
        do_filter  = "filter:no" not in options.lower()

        file_path = f"customstock/{key}.txt"
        os.makedirs("customstock", exist_ok=True)
        open(file_path, 'a').close()

        self.dynamic[key] = {
            "path":       file_path,
            "channel_id": channel_id,
            "role_id":    role_id,
            "filter":     do_filter,
            "label":      service
        }
        save_dynamic(self.dynamic)

        ch_info   = f"<#{channel_id}>" if channel_id else "Any channel"
        role_info = f"<@&{role_id}>"   if role_id   else "None"
        filt_info = "email:password"   if do_filter  else "Raw (no filter)"

        e = discord.Embed(title=f"{tick} Custom Service Added!", color=0x00ff00)
        e.add_field(name="🏷️ Service",  value=f"`{key}`",  inline=True)
        e.add_field(name="📢 Channel",  value=ch_info,     inline=True)
        e.add_field(name="🔒 Role",     value=role_info,   inline=True)
        e.add_field(name="🔍 Filter",   value=filt_info,   inline=True)
        e.add_field(
            name="📋 Next Steps",
            value=(
                f"1. Add stock: `$restock custom {key}` + attach `.txt`\n"
                f"2. Generate: `$custom {key}`"
            ),
            inline=False
        )
        e.set_footer(text=BOT_NAME)
        await ctx.reply(embed=e, mention_author=False)

        await self.refresh_stock_message(ctx.guild.id)

    # ── $genedit ─────────────────────────────────

    @commands.command(name='genedit')
    async def genedit(self, ctx, service: str = None, *, options: str = ""):
        """$genedit <name> [channel:#ch] [role:@role] [filter:yes/no] — Edit custom service (owner)"""
        cross = self.emoji('cross', '❌')
        tick  = self.emoji('tick',  '✅')

        if not self.is_owner(ctx.author):
            e = discord.Embed(title=f"{cross} Access Denied", color=0xff0000)
            e.description = "This command is reserved for **Owners** only."
            e.set_footer(text=BOT_NAME)
            return await ctx.reply(embed=e, mention_author=False)

        if not service:
            e = discord.Embed(title=f"{cross} Incorrect Usage", color=0xff0000)
            e.description = "**Usage:** `$genedit <service> [channel:#ch] [role:@role] [filter:yes/no]`"
            e.set_footer(text=BOT_NAME)
            return await ctx.reply(embed=e, mention_author=False)

        key = service.lower().replace('-', '_')
        if key not in self.dynamic:
            e = discord.Embed(title=f"{cross} Not Found", color=0xff0000)
            e.description = f"`{service}` does not exist. Use `$genlist` to see all services."
            e.set_footer(text=BOT_NAME)
            return await ctx.reply(embed=e, mention_author=False)

        data = self.dynamic[key]
        if ctx.message.channel_mentions:
            data["channel_id"] = ctx.message.channel_mentions[0].id
        if ctx.message.role_mentions:
            data["role_id"] = ctx.message.role_mentions[0].id
        if "filter:no" in options.lower():
            data["filter"] = False
        elif "filter:yes" in options.lower():
            data["filter"] = True

        self.dynamic[key] = data
        save_dynamic(self.dynamic)

        ch_info   = f"<#{data['channel_id']}>" if data.get("channel_id") else "Any channel"
        role_info = f"<@&{data['role_id']}>"   if data.get("role_id")    else "None"
        filt_info = "email:password"            if data.get("filter")     else "Raw"

        e = discord.Embed(title=f"{tick} Service Updated!", color=0x00ff00)
        e.add_field(name="🏷️ Service", value=f"`{key}`", inline=True)
        e.add_field(name="📢 Channel", value=ch_info,    inline=True)
        e.add_field(name="🔒 Role",    value=role_info,  inline=True)
        e.add_field(name="🔍 Filter",  value=filt_info,  inline=True)
        e.set_footer(text=BOT_NAME)
        await ctx.reply(embed=e, mention_author=False)

    # ── $genremove ───────────────────────────────

    @commands.command(name='genremove')
    async def genremove(self, ctx, service: str = None):
        """$genremove <name> — Remove a custom service (owner)"""
        cross = self.emoji('cross', '❌')
        tick  = self.emoji('tick',  '✅')

        if not self.is_owner(ctx.author):
            e = discord.Embed(title=f"{cross} Access Denied", color=0xff0000)
            e.description = "This command is reserved for **Owners** only."
            e.set_footer(text=BOT_NAME)
            return await ctx.reply(embed=e, mention_author=False)

        if not service:
            e = discord.Embed(title=f"{cross} Incorrect Usage", color=0xff0000)
            e.description = "**Usage:** `$genremove <service>`"
            e.set_footer(text=BOT_NAME)
            return await ctx.reply(embed=e, mention_author=False)

        key = service.lower().replace('-', '_')
        if key not in self.dynamic:
            e = discord.Embed(title=f"{cross} Not Found", color=0xff0000)
            e.description = f"`{service}` does not exist. Use `$genlist` to see all."
            e.set_footer(text=BOT_NAME)
            return await ctx.reply(embed=e, mention_author=False)

        path = self.dynamic.pop(key)["path"]
        save_dynamic(self.dynamic)
        if os.path.exists(path):
            os.remove(path)

        e = discord.Embed(title=f"{tick} Service Removed", color=0x00ff00)
        e.description = f"`{key}` has been removed from the Custom Vault."
        e.set_footer(text=BOT_NAME)
        await ctx.reply(embed=e, mention_author=False)

        await self.refresh_stock_message(ctx.guild.id)

    # ── $genlist ─────────────────────────────────

    @commands.command(name='genlist')
    async def genlist(self, ctx):
        """$genlist — List all custom services"""
        if not self.dynamic:
            return await ctx.reply(
                "⚙️ No custom services yet. Use `$genadd <name>` to add one.",
                mention_author=False
            )

        lines = []
        for key, data in self.dynamic.items():
            n     = self.count(data["path"])
            label = data.get("label", key)
            ch    = f"<#{data['channel_id']}>" if data.get("channel_id") else "Any"
            role  = f"<@&{data['role_id']}>"   if data.get("role_id")    else "None"
            filt  = "✅" if data.get("filter") else "❌"
            lines.append(
                f"**`{label}`** — **{n}** units\n"
                f"  Channel: {ch} · Role: {role} · Filter: {filt}"
            )

        e = discord.Embed(title="⚙️ Custom Vault Services", color=0x5865F2)
        e.description = "\n\n".join(lines)
        e.set_footer(text=BOT_NAME)
        await ctx.reply(embed=e, mention_author=False)


    # ── $freeadd ─────────────────────────────────

    @commands.command(name='freeadd')
    async def freeadd(self, ctx, service: str = None, *, options: str = ""):
        """$freeadd <name> [filter:no] — Add a service to the Free Vault (owner only)"""
        cross = self.emoji('cross', '❌')
        tick  = self.emoji('tick',  '✅')

        if not self.is_owner(ctx.author):
            e = discord.Embed(title=f"{cross} Access Denied", color=0xff0000)
            e.description = "This command is reserved for **Owners** only."
            e.set_footer(text=BOT_NAME)
            return await ctx.reply(embed=e, mention_author=False)

        if not service:
            e = discord.Embed(title=f"{cross} Incorrect Usage", color=0xff0000)
            e.description = (
                "**Usage:** `$freeadd <name> [filter:no]`\n\n"
                "Adds a new service to the **🆓 Free Vault** and registers it for `$free`.\n\n"
                "**Options:**\n"
                "`filter:no` → skip email:pass filter (for cookies, codes, etc.)\n\n"
                "**Examples:**\n"
                "`$freeadd Spotify`\n"
                "`$freeadd SteamKeys filter:no`\n\n"
                "After adding, restock with: `$restock free <name>` + attach `.txt`"
            )
            e.set_footer(text=BOT_NAME)
            return await ctx.reply(embed=e, mention_author=False)

        key      = service.lower().replace(' ', '_').replace('-', '_')
        label    = service
        folder   = "stock"
        file_path = f"{folder}/{key}.txt"

        # Check not already in Free Vault
        if label in STOCK_PATHS["🆓 Free Vault"] or key in [k.lower() for k in STOCK_PATHS["🆓 Free Vault"]]:
            e = discord.Embed(title=f"{cross} Already Exists", color=0xff0000)
            e.description = f"`{label}` is already in the Free Vault."
            e.set_footer(text=BOT_NAME)
            return await ctx.reply(embed=e, mention_author=False)

        do_filter = "filter:no" not in options.lower()

        os.makedirs(folder, exist_ok=True)
        open(file_path, 'a').close()

        # Add to runtime STOCK_PATHS
        STOCK_PATHS["🆓 Free Vault"][label] = file_path

        # Add to generation SERVICES
        gen_cog = self.bot.get_cog('GenerationCommands')
        if gen_cog:
            SERVICES["free"]["services"][key] = file_path
        if not do_filter:
            NO_FILTER_SERVICES.add(key)

        # Persist
        vault_extra = load_vault_extra()
        vault_extra.setdefault("free", {})[label] = file_path
        save_vault_extra(vault_extra)

        filt_info = "email:password" if do_filter else "Raw (no filter)"
        e = discord.Embed(title=f"{tick} Free Vault Service Added!", color=0x00ff00)
        e.add_field(name="🏷️ Service",  value=f"`{label}`",  inline=True)
        e.add_field(name="🗂️ Vault",    value="🆓 Free Vault", inline=True)
        e.add_field(name="🔍 Filter",   value=filt_info,       inline=True)
        e.add_field(
            name="📋 Next Steps",
            value=(
                f"1. Add stock: `$restock free {key}` + attach `.txt`\n"
                f"2. Generate: `$free {key}`"
            ),
            inline=False
        )
        e.set_footer(text=BOT_NAME)
        await ctx.reply(embed=e, mention_author=False)
        await self.refresh_stock_message(ctx.guild.id)

    # ── $boostadd ────────────────────────────────

    @commands.command(name='boostadd')
    async def boostadd(self, ctx, service: str = None, *, options: str = ""):
        """$boostadd <name> [filter:no] — Add a service to the Booster Vault (owner only)"""
        cross = self.emoji('cross', '❌')
        tick  = self.emoji('tick',  '✅')

        if not self.is_owner(ctx.author):
            e = discord.Embed(title=f"{cross} Access Denied", color=0xff0000)
            e.description = "This command is reserved for **Owners** only."
            e.set_footer(text=BOT_NAME)
            return await ctx.reply(embed=e, mention_author=False)

        if not service:
            e = discord.Embed(title=f"{cross} Incorrect Usage", color=0xff0000)
            e.description = (
                "**Usage:** `$boostadd <name> [filter:no]`\n\n"
                "Adds a new service to the **🚀 Booster Vault** and registers it for `$boost`.\n\n"
                "**Options:**\n"
                "`filter:no` → skip email:pass filter (for cookies, codes, etc.)\n\n"
                "**Examples:**\n"
                "`$boostadd DisneyPlus`\n"
                "`$boostadd HBOCookies filter:no`\n\n"
                "After adding, restock with: `$restock booster <name>` + attach `.txt`"
            )
            e.set_footer(text=BOT_NAME)
            return await ctx.reply(embed=e, mention_author=False)

        key       = service.lower().replace(' ', '_').replace('-', '_')
        label     = service
        folder    = "bosststock"
        file_path = f"{folder}/{key}.txt"

        # Check not already in Booster Vault
        if label in STOCK_PATHS["🚀 Booster Vault"] or key in [k.lower() for k in STOCK_PATHS["🚀 Booster Vault"]]:
            e = discord.Embed(title=f"{cross} Already Exists", color=0xff0000)
            e.description = f"`{label}` is already in the Booster Vault."
            e.set_footer(text=BOT_NAME)
            return await ctx.reply(embed=e, mention_author=False)

        do_filter = "filter:no" not in options.lower()

        os.makedirs(folder, exist_ok=True)
        open(file_path, 'a').close()

        # Add to runtime STOCK_PATHS
        STOCK_PATHS["🚀 Booster Vault"][label] = file_path

        # Add to generation SERVICES
        gen_cog = self.bot.get_cog('GenerationCommands')
        if gen_cog:
            SERVICES["booster"]["services"][key] = file_path
        if not do_filter:
            NO_FILTER_SERVICES.add(key)

        # Persist
        vault_extra = load_vault_extra()
        vault_extra.setdefault("booster", {})[label] = file_path
        save_vault_extra(vault_extra)

        filt_info = "email:password" if do_filter else "Raw (no filter)"
        e = discord.Embed(title=f"{tick} Booster Vault Service Added!", color=0x00ff00)
        e.add_field(name="🏷️ Service",  value=f"`{label}`",     inline=True)
        e.add_field(name="🗂️ Vault",    value="🚀 Booster Vault", inline=True)
        e.add_field(name="🔍 Filter",   value=filt_info,          inline=True)
        e.add_field(
            name="📋 Next Steps",
            value=(
                f"1. Add stock: `$restock booster {key}` + attach `.txt`\n"
                f"2. Generate: `$boost {key}`"
            ),
            inline=False
        )
        e.set_footer(text=BOT_NAME)
        await ctx.reply(embed=e, mention_author=False)
        await self.refresh_stock_message(ctx.guild.id)


    # ── $freeremove ──────────────────────────────

    @commands.command(name='freeremove')
    async def freeremove(self, ctx, service: str = None):
        """$freeremove <service> — Retire un service du Free Vault (owner only)"""
        cross = self.emoji('cross', '❌')
        tick  = self.emoji('tick',  '✅')
        arrow = self.emoji('arrow_arrow', '➡️')

        if not self.is_owner(ctx.author):
            e = discord.Embed(title=f"{cross} Accès refusé", color=0xff0000)
            e.description = "Cette commande est réservée aux **Owners** uniquement."
            e.set_footer(text=BOT_NAME)
            return await ctx.reply(embed=e, mention_author=False)

        if not service:
            available = ', '.join(f'`{s}`' for s in STOCK_PATHS["🆓 Free Vault"])
            e = discord.Embed(title=f"{cross} Usage incorrect", color=0xff0000)
            e.description = (
                f"**Usage :** `$freeremove <service>`\n\n"
                f"**Services disponibles :** {available}"
            )
            e.set_footer(text=BOT_NAME)
            return await ctx.reply(embed=e, mention_author=False)

        key = service.lower().replace(' ', '_').replace('-', '_')

        # Chercher le service (insensible à la casse)
        found_label = None
        for label in list(STOCK_PATHS["🆓 Free Vault"].keys()):
            if label.lower().replace(' ', '_').replace('-', '_') == key:
                found_label = label
                break

        if not found_label:
            available = ', '.join(f'`{s}`' for s in STOCK_PATHS["🆓 Free Vault"])
            e = discord.Embed(title=f"{cross} Service introuvable", color=0xff0000)
            e.description = f"{arrow} `{service}` n'existe pas dans le Free Vault.\n\n**Disponibles :** {available}"
            e.set_footer(text=BOT_NAME)
            return await ctx.reply(embed=e, mention_author=False)

        file_path = STOCK_PATHS["🆓 Free Vault"].pop(found_label)

        # Retirer de SERVICES generation
        gen_cog = self.bot.get_cog('GenerationCommands')
        if gen_cog:
            SERVICES["free"]["services"].pop(key, None)
        NO_FILTER_SERVICES.discard(key)

        # Retirer de la persistence vault_extra
        vault_extra = load_vault_extra()
        vault_extra.get("free", {}).pop(found_label, None)
        vault_extra.get("free", {}).pop(key, None)
        save_vault_extra(vault_extra)

        e = discord.Embed(title=f"{tick} Service retiré du Free Vault", color=0x00ff00)
        e.add_field(name="🏷️ Service", value=f"`{found_label}`",   inline=True)
        e.add_field(name="🗂️ Vault",   value="🆓 Free Vault",        inline=True)
        e.description = (
            f"{arrow} Le service a été retiré de la liste.\n"
            f"*(Le fichier stock `{file_path}` n'a pas été supprimé.)*"
        )
        e.set_footer(text=BOT_NAME)
        await ctx.reply(embed=e, mention_author=False)
        await self.refresh_stock_message(ctx.guild.id)

    # ── $boostremove ─────────────────────────────

    @commands.command(name='boostremove')
    async def boostremove(self, ctx, service: str = None):
        """$boostremove <service> — Retire un service du Booster Vault (owner only)"""
        cross = self.emoji('cross', '❌')
        tick  = self.emoji('tick',  '✅')
        arrow = self.emoji('arrow_arrow', '➡️')

        if not self.is_owner(ctx.author):
            e = discord.Embed(title=f"{cross} Accès refusé", color=0xff0000)
            e.description = "Cette commande est réservée aux **Owners** uniquement."
            e.set_footer(text=BOT_NAME)
            return await ctx.reply(embed=e, mention_author=False)

        if not service:
            available = ', '.join(f'`{s}`' for s in STOCK_PATHS["🚀 Booster Vault"])
            e = discord.Embed(title=f"{cross} Usage incorrect", color=0xff0000)
            e.description = (
                f"**Usage :** `$boostremove <service>`\n\n"
                f"**Services disponibles :** {available}"
            )
            e.set_footer(text=BOT_NAME)
            return await ctx.reply(embed=e, mention_author=False)

        key = service.lower().replace(' ', '_').replace('-', '_')

        # Chercher le service (insensible à la casse)
        found_label = None
        for label in list(STOCK_PATHS["🚀 Booster Vault"].keys()):
            if label.lower().replace(' ', '_').replace('-', '_') == key:
                found_label = label
                break

        if not found_label:
            available = ', '.join(f'`{s}`' for s in STOCK_PATHS["🚀 Booster Vault"])
            e = discord.Embed(title=f"{cross} Service introuvable", color=0xff0000)
            e.description = f"{arrow} `{service}` n'existe pas dans le Booster Vault.\n\n**Disponibles :** {available}"
            e.set_footer(text=BOT_NAME)
            return await ctx.reply(embed=e, mention_author=False)

        file_path = STOCK_PATHS["🚀 Booster Vault"].pop(found_label)

        # Retirer de SERVICES generation
        gen_cog = self.bot.get_cog('GenerationCommands')
        if gen_cog:
            SERVICES["booster"]["services"].pop(key, None)
        NO_FILTER_SERVICES.discard(key)

        # Retirer de la persistence vault_extra
        vault_extra = load_vault_extra()
        vault_extra.get("booster", {}).pop(found_label, None)
        vault_extra.get("booster", {}).pop(key, None)
        save_vault_extra(vault_extra)

        e = discord.Embed(title=f"{tick} Service retiré du Booster Vault", color=0x00ff00)
        e.add_field(name="🏷️ Service", value=f"`{found_label}`",     inline=True)
        e.add_field(name="🗂️ Vault",   value="🚀 Booster Vault",       inline=True)
        e.description = (
            f"{arrow} Le service a été retiré de la liste.\n"
            f"*(Le fichier stock `{file_path}` n'a pas été supprimé.)*"
        )
        e.set_footer(text=BOT_NAME)
        await ctx.reply(embed=e, mention_author=False)
        await self.refresh_stock_message(ctx.guild.id)


async def setup(bot):
    await bot.add_cog(InventoryCommands(bot))
