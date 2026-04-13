import discord
from discord.ext import commands
import json
import os

# ──────────────────────────────────────────
#  Load config
# ──────────────────────────────────────────
try:
    with open('config.json', 'r') as f:
        config_data = json.load(f)
except Exception:
    config_data = {}

BOT_NAME = "Storm G3N"


class StormG3NBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        intents.presences = True
        super().__init__(command_prefix='$', intents=intents, help_command=None)
        self.config = config_data
        cfg = self.config.get('botConfig', {})
        self.gen_channel_id  = int(cfg.get('genChannelId',  0))
        self.logs_channel_id = int(cfg.get('logsChannelId', 0))
        self.status_role_id  = int(cfg.get('statusRoleId',  0))
        self.status_text     = cfg.get('statusText', '.gg/StormGen')

    async def setup_hook(self):
        print(f"[{BOT_NAME}] Loading extensions...")
        for filename in os.listdir('./commands'):
            if filename.endswith('.py') and filename != '__init__.py':
                try:
                    await self.load_extension(f'commands.{filename[:-3]}')
                    print(f"  OK: {filename}")
                except Exception as e:
                    print(f"  FAIL: {filename}: {e}")

    async def on_ready(self):
        print(f'[{BOT_NAME}] Logged in as {self.user} (ID: {self.user.id})')
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name="Storm G3N | $help"
            )
        )
        try:
            synced = await self.tree.sync()
            print(f"Synced {len(synced)} slash command(s)")
        except Exception as e:
            print(f"Sync failed: {e}")

    async def on_message(self, message):
        if message.author.bot:
            return
        vouch = self.get_cog('VouchSystem')
        if vouch and hasattr(vouch, 'handle_message'):
            await vouch.handle_message(message)
        await self.process_commands(message)

    async def on_presence_update(self, before, after):
        if after.bot or not after.guild:
            return
        custom_status = next(
            (a for a in after.activities if isinstance(a, discord.CustomActivity)), None
        )
        has_target = (
            custom_status and custom_status.state
            and self.status_text in custom_status.state
        )
        role = after.guild.get_role(self.status_role_id)
        if not role:
            return
        log_channel = self.get_channel(self.logs_channel_id)
        try:
            if has_target and role not in after.roles:
                await after.add_roles(role)
                if log_channel:
                    await log_channel.send(f"**{after}** has the correct status - role added")
            elif not has_target and role in after.roles:
                await after.remove_roles(role)
                if log_channel:
                    await log_channel.send(f"**{after}** changed/removed their status - role removed")
        except Exception as e:
            print(f"Role update failed for {after}: {e}")


bot = StormG3NBot()

if __name__ == "__main__":
    token = (
        config_data.get('botConfig', {}).get('token')
        or os.environ.get("DISCORD_TOKEN")
    )
    if not token:
        print(f"[{BOT_NAME}] No token found! Set 'token' in config.json or the DISCORD_TOKEN env variable.")
    else:
        bot.run(token)
