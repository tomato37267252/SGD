import discord
from discord.ext import commands
import json
import os
import datetime
import asyncio

BOT_NAME = "Storm G3N"

TICKETS_FILE = "tickets.json"


def load_tickets():
    if os.path.exists(TICKETS_FILE):
        try:
            with open(TICKETS_FILE, 'r') as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_tickets(data):
    with open(TICKETS_FILE, 'w') as f:
        json.dump(data, f, indent=2)


class TicketSystem(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.tickets = load_tickets()  # {channel_id: {user_id, guild_id, reason, opened_at}}

    def emoji(self, name, default=''):
        return self.bot.config.get('emojis', {}).get(name, default)

    def is_owner(self, member):
        cfg = self.bot.config.get('botConfig', {})
        owner_role_id = int(cfg.get('ownerRoleId', 0))
        if not owner_role_id:
            return member.guild_permissions.administrator
        return any(r.id == owner_role_id for r in member.roles)

    def get_ticket_category_id(self):
        cfg = self.bot.config.get('botConfig', {})
        return int(cfg.get('ticketCategoryId', 0))

    def get_ticket_log_channel_id(self):
        cfg = self.bot.config.get('botConfig', {})
        return int(cfg.get('ticketLogChannelId', 0) or cfg.get('logsChannelId', 0))

    def get_support_role_id(self):
        cfg = self.bot.config.get('botConfig', {})
        return int(cfg.get('supportRoleId', 0))

    def user_has_open_ticket(self, guild_id, user_id):
        for ch_id, data in self.tickets.items():
            if str(data.get('guild_id')) == str(guild_id) and str(data.get('user_id')) == str(user_id):
                return int(ch_id)
        return None

    # ── $ticket ──────────────────────────────────

    @commands.command(name='ticket')
    async def ticket(self, ctx, *, reason: str = None):
        """$ticket [raison] — Ouvre un ticket de support"""
        cross   = self.emoji('cross',      '❌')
        tick    = self.emoji('tick',       '✅')
        arrow   = self.emoji('arrow_arrow','➡️')
        lock    = self.emoji('lock_key',   '🎫')

        # Check si l'user a déjà un ticket ouvert
        existing = self.user_has_open_ticket(ctx.guild.id, ctx.author.id)
        if existing:
            ch = ctx.guild.get_channel(existing)
            ch_mention = ch.mention if ch else f"<#{existing}>"
            e = discord.Embed(title=f"{cross} Ticket déjà ouvert", color=0xff0000)
            e.description = (
                f"{arrow} Tu as déjà un ticket ouvert : {ch_mention}\n"
                f"Utilise `$closeticket` pour le fermer avant d'en ouvrir un nouveau."
            )
            e.set_footer(text=BOT_NAME)
            return await ctx.reply(embed=e, mention_author=False)

        # Trouver/créer la catégorie
        category = None
        cat_id = self.get_ticket_category_id()
        if cat_id:
            category = ctx.guild.get_channel(cat_id)

        # Permissions du channel
        support_role_id = self.get_support_role_id()
        overwrites = {
            ctx.guild.default_role: discord.PermissionOverwrite(read_messages=False),
            ctx.author: discord.PermissionOverwrite(
                read_messages=True,
                send_messages=True,
                attach_files=True,
                embed_links=True
            ),
            ctx.guild.me: discord.PermissionOverwrite(
                read_messages=True,
                send_messages=True,
                manage_channels=True,
                manage_messages=True
            ),
        }
        if support_role_id:
            support_role = ctx.guild.get_role(support_role_id)
            if support_role:
                overwrites[support_role] = discord.PermissionOverwrite(
                    read_messages=True,
                    send_messages=True,
                    manage_messages=True
                )

        # Numéro du ticket
        ticket_count = len([t for t in self.tickets.values() if str(t.get('guild_id')) == str(ctx.guild.id)])
        ticket_num   = ticket_count + 1
        channel_name = f"ticket-{ctx.author.name.lower().replace(' ', '-')}-{ticket_num:04d}"

        try:
            ticket_channel = await ctx.guild.create_text_channel(
                name=channel_name,
                category=category,
                overwrites=overwrites,
                topic=f"Ticket de {ctx.author} | Raison: {reason or 'Non spécifiée'}"
            )
        except discord.Forbidden:
            e = discord.Embed(title=f"{cross} Erreur de permissions", color=0xff0000)
            e.description = f"{arrow} Je n'ai pas les permissions pour créer un channel."
            e.set_footer(text=BOT_NAME)
            return await ctx.reply(embed=e, mention_author=False)

        # Enregistrer le ticket
        self.tickets[str(ticket_channel.id)] = {
            "user_id":   str(ctx.author.id),
            "guild_id":  str(ctx.guild.id),
            "reason":    reason or "Non spécifiée",
            "opened_at": datetime.datetime.utcnow().isoformat(),
            "ticket_num": ticket_num
        }
        save_tickets(self.tickets)

        # Message dans le ticket
        mention_parts = [ctx.author.mention]
        if support_role_id:
            sr = ctx.guild.get_role(support_role_id)
            if sr:
                mention_parts.append(sr.mention)

        await ticket_channel.send(" ".join(mention_parts))

        ticket_embed = discord.Embed(
            title=f"{lock} Ticket #{ticket_num:04d}",
            color=0x5865F2
        )
        ticket_embed.description = (
            f"Bienvenue {ctx.author.mention} ! Un membre du staff va t'aider bientôt.\n\n"
            f"**Raison :** {reason or 'Non spécifiée'}\n"
            f"**Ouvert le :** <t:{int(datetime.datetime.utcnow().timestamp())}:F>\n\n"
            f"Pour fermer ce ticket : `$closeticket`\n"
            f"Pour le fermer avec un motif : `$closeticket <motif>`"
        )
        ticket_embed.set_footer(text=BOT_NAME)
        await ticket_channel.send(embed=ticket_embed)

        # Confirmation dans le channel d'origine
        confirm = discord.Embed(title=f"{tick} Ticket ouvert !", color=0x00ff00)
        confirm.description = f"{arrow} Ton ticket a été créé : {ticket_channel.mention}"
        confirm.set_footer(text=BOT_NAME)
        await ctx.reply(embed=confirm, mention_author=False)

        # Log
        log_ch_id = self.get_ticket_log_channel_id()
        if log_ch_id:
            log_ch = self.bot.get_channel(log_ch_id)
            if log_ch:
                log_e = discord.Embed(title="🎫 Ticket Ouvert", color=0x5865F2)
                log_e.add_field(name="Utilisateur", value=f"{ctx.author.mention} (`{ctx.author.id}`)", inline=True)
                log_e.add_field(name="Channel",     value=ticket_channel.mention,                       inline=True)
                log_e.add_field(name="Raison",      value=reason or "Non spécifiée",                   inline=False)
                log_e.set_footer(text=f"{BOT_NAME} • {datetime.datetime.utcnow().strftime('%H:%M:%S UTC')}")
                await log_ch.send(embed=log_e)

    # ── $closeticket ─────────────────────────────

    @commands.command(name='closeticket')
    async def closeticket(self, ctx, *, reason: str = None):
        """$closeticket [motif] — Ferme le ticket actuel"""
        cross = self.emoji('cross', '❌')
        tick  = self.emoji('tick',  '✅')
        arrow = self.emoji('arrow_arrow', '➡️')

        ticket_data = self.tickets.get(str(ctx.channel.id))

        if not ticket_data:
            e = discord.Embed(title=f"{cross} Pas un ticket", color=0xff0000)
            e.description = f"{arrow} Cette commande doit être utilisée dans un channel de ticket."
            e.set_footer(text=BOT_NAME)
            return await ctx.reply(embed=e, mention_author=False)

        # Seul l'owner du ticket, le staff ou admin peut fermer
        is_ticket_owner = str(ctx.author.id) == str(ticket_data.get('user_id'))
        if not is_ticket_owner and not self.is_owner(ctx.author) and not ctx.author.guild_permissions.manage_channels:
            support_role_id = self.get_support_role_id()
            has_support_role = support_role_id and any(r.id == support_role_id for r in ctx.author.roles)
            if not has_support_role:
                e = discord.Embed(title=f"{cross} Accès refusé", color=0xff0000)
                e.description = f"{arrow} Seul le créateur du ticket ou le staff peut le fermer."
                e.set_footer(text=BOT_NAME)
                return await ctx.reply(embed=e, mention_author=False)

        ticket_owner = ctx.guild.get_member(int(ticket_data.get('user_id', 0)))
        ticket_num   = ticket_data.get('ticket_num', '?')
        opened_at    = ticket_data.get('opened_at', '')

        # Message de fermeture
        close_e = discord.Embed(title=f"🔒 Ticket #{ticket_num:04d} — Fermé", color=0xff4444)
        close_e.description = (
            f"**Fermé par :** {ctx.author.mention}\n"
            f"**Motif :** {reason or 'Aucun motif fourni'}\n\n"
            f"Ce channel sera supprimé dans **5 secondes**."
        )
        close_e.set_footer(text=BOT_NAME)
        await ctx.send(embed=close_e)

        # Log avant suppression
        log_ch_id = self.get_ticket_log_channel_id()
        if log_ch_id:
            log_ch = self.bot.get_channel(log_ch_id)
            if log_ch:
                log_e = discord.Embed(title="🔒 Ticket Fermé", color=0xff4444)
                log_e.add_field(name="Ticket",       value=f"#{ticket_num:04d} (`{ctx.channel.name}`)", inline=True)
                log_e.add_field(name="Propriétaire", value=ticket_owner.mention if ticket_owner else ticket_data.get('user_id'), inline=True)
                log_e.add_field(name="Fermé par",    value=ctx.author.mention, inline=True)
                log_e.add_field(name="Motif",        value=reason or "Aucun motif fourni", inline=False)
                if opened_at:
                    log_e.add_field(name="Ouvert le", value=opened_at[:19].replace('T', ' ') + " UTC", inline=False)
                log_e.set_footer(text=f"{BOT_NAME} • {datetime.datetime.utcnow().strftime('%H:%M:%S UTC')}")
                await log_ch.send(embed=log_e)

        # Supprimer le ticket de la liste
        self.tickets.pop(str(ctx.channel.id), None)
        save_tickets(self.tickets)

        await asyncio.sleep(5)
        try:
            await ctx.channel.delete(reason=f"Ticket fermé par {ctx.author}")
        except Exception as e:
            print(f"[{BOT_NAME}] Erreur suppression ticket: {e}")

    # ── $ticketadd ───────────────────────────────

    @commands.command(name='ticketadd')
    async def ticketadd(self, ctx, member: discord.Member = None):
        """$ticketadd @user — Ajoute un utilisateur au ticket (staff/owner)"""
        cross = self.emoji('cross', '❌')
        tick  = self.emoji('tick',  '✅')
        arrow = self.emoji('arrow_arrow', '➡️')

        if str(ctx.channel.id) not in self.tickets:
            e = discord.Embed(title=f"{cross} Pas un ticket", color=0xff0000)
            e.description = f"{arrow} Cette commande doit être utilisée dans un channel de ticket."
            e.set_footer(text=BOT_NAME)
            return await ctx.reply(embed=e, mention_author=False)

        if not self.is_owner(ctx.author) and not ctx.author.guild_permissions.manage_channels:
            e = discord.Embed(title=f"{cross} Accès refusé", color=0xff0000)
            e.description = f"{arrow} Réservé au staff."
            e.set_footer(text=BOT_NAME)
            return await ctx.reply(embed=e, mention_author=False)

        if not member:
            e = discord.Embed(title=f"{cross} Usage incorrect", color=0xff0000)
            e.description = f"{arrow} **Usage :** `$ticketadd @utilisateur`"
            e.set_footer(text=BOT_NAME)
            return await ctx.reply(embed=e, mention_author=False)

        await ctx.channel.set_permissions(member,
            read_messages=True,
            send_messages=True,
            attach_files=True
        )
        e = discord.Embed(title=f"{tick} Utilisateur ajouté", color=0x00ff00)
        e.description = f"{member.mention} a été ajouté au ticket."
        e.set_footer(text=BOT_NAME)
        await ctx.reply(embed=e, mention_author=False)

    # ── $ticketremove ─────────────────────────────

    @commands.command(name='ticketremove')
    async def ticketremove(self, ctx, member: discord.Member = None):
        """$ticketremove @user — Retire un utilisateur du ticket (staff/owner)"""
        cross = self.emoji('cross', '❌')
        tick  = self.emoji('tick',  '✅')
        arrow = self.emoji('arrow_arrow', '➡️')

        if str(ctx.channel.id) not in self.tickets:
            e = discord.Embed(title=f"{cross} Pas un ticket", color=0xff0000)
            e.description = f"{arrow} Cette commande doit être utilisée dans un channel de ticket."
            e.set_footer(text=BOT_NAME)
            return await ctx.reply(embed=e, mention_author=False)

        if not self.is_owner(ctx.author) and not ctx.author.guild_permissions.manage_channels:
            e = discord.Embed(title=f"{cross} Accès refusé", color=0xff0000)
            e.description = f"{arrow} Réservé au staff."
            e.set_footer(text=BOT_NAME)
            return await ctx.reply(embed=e, mention_author=False)

        if not member:
            e = discord.Embed(title=f"{cross} Usage incorrect", color=0xff0000)
            e.description = f"{arrow} **Usage :** `$ticketremove @utilisateur`"
            e.set_footer(text=BOT_NAME)
            return await ctx.reply(embed=e, mention_author=False)

        ticket_data = self.tickets.get(str(ctx.channel.id), {})
        if str(member.id) == str(ticket_data.get('user_id')):
            e = discord.Embed(title=f"{cross} Action impossible", color=0xff0000)
            e.description = f"{arrow} Tu ne peux pas retirer le créateur du ticket."
            e.set_footer(text=BOT_NAME)
            return await ctx.reply(embed=e, mention_author=False)

        await ctx.channel.set_permissions(member, overwrite=None)
        e = discord.Embed(title=f"{tick} Utilisateur retiré", color=0x00ff00)
        e.description = f"{member.mention} a été retiré du ticket."
        e.set_footer(text=BOT_NAME)
        await ctx.reply(embed=e, mention_author=False)

    # ── $tickets ─────────────────────────────────

    @commands.command(name='tickets')
    async def tickets_list(self, ctx):
        """$tickets — Liste tous les tickets ouverts (admin/owner)"""
        cross = self.emoji('cross', '❌')
        arrow = self.emoji('arrow_arrow', '➡️')

        if not self.is_owner(ctx.author) and not ctx.author.guild_permissions.manage_channels:
            e = discord.Embed(title=f"{cross} Accès refusé", color=0xff0000)
            e.description = f"{arrow} Réservé au staff."
            e.set_footer(text=BOT_NAME)
            return await ctx.reply(embed=e, mention_author=False)

        guild_tickets = {
            ch_id: data for ch_id, data in self.tickets.items()
            if str(data.get('guild_id')) == str(ctx.guild.id)
        }

        if not guild_tickets:
            e = discord.Embed(title="🎫 Tickets ouverts", color=0x5865F2)
            e.description = "Aucun ticket ouvert pour le moment."
            e.set_footer(text=BOT_NAME)
            return await ctx.reply(embed=e, mention_author=False)

        lines = []
        for ch_id, data in guild_tickets.items():
            ch     = ctx.guild.get_channel(int(ch_id))
            user   = ctx.guild.get_member(int(data.get('user_id', 0)))
            num    = data.get('ticket_num', '?')
            reason = data.get('reason', 'N/A')
            ch_str = ch.mention if ch else f"<#{ch_id}> (supprimé)"
            u_str  = user.mention if user else f"`{data.get('user_id')}`"
            lines.append(f"**#{num:04d}** — {ch_str} · {u_str}\n  └ Raison: {reason[:50]}")

        e = discord.Embed(title=f"🎫 Tickets ouverts ({len(guild_tickets)})", color=0x5865F2)
        e.description = "\n\n".join(lines)
        e.set_footer(text=BOT_NAME)
        await ctx.reply(embed=e, mention_author=False)


async def setup(bot):
    await bot.add_cog(TicketSystem(bot))
