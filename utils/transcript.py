import datetime

async def create_transcript(channel):
    filename = f"/tmp/{channel.name}.txt"
    with open(filename, "w", encoding="utf-8") as f:
        async for message in channel.history(limit=None, oldest_first=True):
            time = message.created_at.strftime("%Y-%m-%d %H:%M")
            f.write(f"[{time}] {message.author}: {message.content}\n")
    return filename
