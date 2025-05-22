import os
import discord
import logging

from datetime import datetime
from discord.ext import commands
from dotenv import load_dotenv

from discord.ext.commands import is_owner, Context


# Loads the .env file that resides on the same level as the script
load_dotenv("config.env.txt")

# Grab API tokens from the .env file and other things
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
GUILD = os.getenv('DISCORD_GUILD')
INVITE_URL = os.getenv('DISCORD_INVITE')

OPENAI_KEY = os.getenv('OPENAI_KEY')

PAYPAL_CLIENT = os.getenv('PAYPAL_CLIENT')
PAYPAL_SECRET = os.getenv('PAYPAL_SECRET')
PAYPAL_URL = os.getenv('PAYPAL_URL')
ENCRYPTION_KEY = os.getenv('ENCRYPTION_KEY')

PLEX_TOKEN = os.getenv('PLEX_TOKEN')
PLEX_URL = os.getenv('PLEX_URL')
OVERSEERR_API_KEY = os.getenv('OVERSEERR_API_KEY')
OVERSEERR_URL = os.getenv('OVERSEERR_URL')
RADARR_API_KEY = os.getenv('RADARR_API_KEY')
RADARR_URL = os.getenv('RADARR_URL')
TAUTULLI_URL = os.getenv('TAUTULLI_URL')
TAUTULLI_API_KEY = os.getenv('TAUTULLI_API_KEY')
SABNZBD_API = os.getenv('SABNZBD_API')
SABNZBD_URL = os.getenv('SABNZBD_URL')

RUN_IN_IDE = os.getenv('RUN_IN_IDE')


# Discord
DISCORD_PREFIX = "%"

# Other External Keys
LAUNCH_TIME = datetime.utcnow()


# Login Clients
intents = discord.Intents.all()
intents.message_content = True

# Ensure the logs directory exists
os.makedirs('data', exist_ok=True)
os.makedirs('data/logs', exist_ok=True)
os.makedirs('data/databases', exist_ok=True)


# Setting up logging before anything else
logging.basicConfig(level=logging.ERROR)  # Change to DEBUG for more detailed logs if needed
logger = logging.getLogger('discord')
handler = logging.FileHandler(filename='data/logs/discord.log', encoding='utf-8', mode='w')
handler.setFormatter(logging.Formatter('%(asctime)s:%(levelname)s:%(name)s: %(message)s'))
logger.addHandler(handler)

client = commands.Bot(command_prefix=DISCORD_PREFIX, intents=intents, help_command=None,
                      activity=discord.Activity(type=discord.ActivityType.watching, name="NEPHFLIX"))


async def perform_sync():
    synced = await client.tree.sync()
    return len(synced)

@client.command()
@is_owner()
async def sync(ctx: Context) -> None:
    synced = await client.tree.sync()
    await ctx.reply("{} commands synced".format(len(synced)))
