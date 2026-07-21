import asyncio

async def background_worker():
    """Background task that runs when server starts."""
    while True:
        print("Background task running...")
        await asyncio.sleep(10)  # Replace with real logic
