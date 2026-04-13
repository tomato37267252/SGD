import os
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = int(os.getenv("GUILD_ID", 0))
TICKET_CATEGORY = os.getenv("TICKET_CATEGORY", "Tickets")
LOG_CHANNEL_ID = int(os.getenv("LOG_CHANNEL_ID", 0))
