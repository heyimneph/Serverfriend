import discord
import datetime
import logging
import socket
import asyncio
import os
import aiosqlite

from discord import app_commands
from discord.ext import commands, tasks
from mcstatus import JavaServer

from cogs.customisation import get_embed_colour
from core.utils import log_command_usage

# ---------------------------------------------------------------------------------------------------------------------
# DATABASE INITIALISATION
# ---------------------------------------------------------------------------------------------------------------------

# Ensure the database directory exists
os.makedirs('./data/databases', exist_ok=True)

# Connect to SQLite database asynchronously
db_path = './data/databases/serverfriend.db'


# ---------------------------------------------------------------------------------------------------------------------
# Logging Configuration
# ---------------------------------------------------------------------------------------------------------------------

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------------------------------------------------
# Utility Functions (Updated for Async)
# ---------------------------------------------------------------------------------------------------------------------


async def async_socket_connect(ip, port, timeout=5):
    try:
        conn = asyncio.open_connection(ip, port)
        _, writer = await asyncio.wait_for(conn, timeout=timeout)
        writer.close()
        await writer.wait_closed()
    except asyncio.TimeoutError:
        logging.error(f"Timeout Error in async_socket_connect: Connection to {ip}:{port} timed out")
    except Exception as e:
        logging.error(f"Error in async_socket_connect: {e}")

def send_steam_query(ip: str, port: int, timeout: float = 5.0) -> str:
    try:
        message = b'\xFF\xFF\xFF\xFFTSource Engine Query\x00'
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.settimeout(timeout)
            sock.sendto(message, (ip, port))
            try:
                data, _ = sock.recvfrom(4096)
                return ":green_circle:"  # Server responded
            except socket.timeout:
                return ":red_circle:"  # No response
    except Exception as e:
        logging.error(f"Error in send_steam_query: {e}")
        return ":red_circle:"

def ping_udp_server(ip: str, port: int, timeout: float = 5.0) -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.settimeout(timeout)
            message = b"Test packet"
            sock.sendto(message, (ip, port))
            try:
                data, _ = sock.recvfrom(1024)
                return ":green_circle:"  # Server responded
            except socket.timeout:
                return ":red_circle:"  # No response
    except Exception as e:
        logging.error(f"Error in ping_udp_server: {e}")
        return ":red_circle:"

def check_tcp_server_status(ip: str, port: int, timeout: float = 5.0) -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(timeout)
            sock.connect((ip, port))
            return ":green_circle:"  # Server is UP
    except Exception as e:
        logging.error(f"Error in check_tcp_server_status: {e}")
        return ":red_circle:"  # Server is DOWN

async def check_server_status(server_type, ip, port=None):
    try:
        if server_type == "minecraft":
            server = JavaServer.lookup(ip)
            server.status()
            return ":green_circle:"
        elif server_type == "valheim":
            return await asyncio.get_event_loop().run_in_executor(None, send_steam_query, ip, port + 1)
        elif server_type == "zomboid":
            return await asyncio.get_event_loop().run_in_executor(None, send_steam_query, ip, port)
        elif server_type == "palworld":
            return await asyncio.get_event_loop().run_in_executor(None, ping_udp_server, ip, port)
        elif server_type == "scp":
            return await asyncio.get_event_loop().run_in_executor(None, check_tcp_server_status, ip, port)
        elif server_type=="enshrouded":
            return await asyncio.get_event_loop().run_in_executor(None, send_steam_query, ip, port)
        elif server_type=="vrising":
            return await asyncio.get_event_loop().run_in_executor(None, send_steam_query, ip, port)


    except asyncio.TimeoutError:
        return ":red_circle:"
    except Exception as e:
        return ":red_circle:"

# ---------------------------------------------------------------------------------------------------------------------
# ServerUpdatesCog Class
# ---------------------------------------------------------------------------------------------------------------------
class ServerUpdatesCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.channel_id = None
        self.message_id = None

    @commands.Cog.listener()
    async def on_ready(self):
        await self.cog_load()
        self.update_status.start()
        logger.error(f"Game Servers - Message Task: Started")

    async def cog_load(self):
        async with aiosqlite.connect(db_path) as conn:
            async with conn.execute('SELECT channel_id, message_id FROM server_status WHERE id = 1') as cursor:
                data = await cursor.fetchone()
                if data:
                    self.channel_id, self.message_id = data

    def cog_unload(self):
        self.update_status.cancel()

    @tasks.loop(minutes=1)
    async def update_status(self):

        try:
            if not (self.channel_id and self.message_id):
                return

            channel = self.bot.get_channel(self.channel_id)
            if not channel:
                logging.error("Channel not found!")
                return

            message = await channel.fetch_message(self.message_id)
            if not message:
                logging.error("Message not found!")
                return

            embed = await self.construct_embed()
            await message.edit(embed=embed)

        except Exception as e:
            logging.error(f"Unhandled exception in update_status: {e}")


    @update_status.before_loop
    async def before_update_status(self):
        await self.bot.wait_until_ready()

    async def construct_embed(self):
        date_raw = datetime.datetime.utcnow()
        date = date_raw.strftime(f"%d/%m/%Y")
        time = date_raw.strftime("%H:%M")

        async with aiosqlite.connect(db_path) as conn:
            embed = discord.Embed(title="GAME SERVER LIST",
                                  description="Passwords: `᲼᲼᲼᲼᲼᲼᲼᲼᲼᲼᲼᲼᲼᲼᲼᲼`",
                                  color=await get_embed_colour(conn))

        # Server check tasks
        server_check_tasks = [
            check_server_status("minecraft", "mc.nephbox.net"),  # results[0]
            check_server_status("minecraft", "dawncraft.nephbox.net"),  # results[1]
            check_server_status("minecraft", "pixelmon.nephbox.net"),  # results[2]
            check_server_status("minecraft", "allthemods.nephbox.net"),  # results[3]
            check_server_status("minecraft", "deceased.nephbox.net"),  # results[4]
            check_server_status("minecraft", "prominence.nephbox.net"),  # results[5]
            check_server_status("valheim", "192.168.0.40", 2456),  # results[6]
            check_server_status("palworld", "192.168.0.40", 8766),  # results[7]
            check_server_status("zomboid", "192.168.0.40", 19132),  # results[8]
            check_server_status("enshrouded", "82.14.1.253", 15637),  # results[9]
            check_server_status("vrising", "82.14.1.253", 9877),  # results[10]
        ]

        results = await asyncio.gather(*server_check_tasks)

        # Minecraft server statuses
        embed.add_field(name="Minecraft", value=(
            f"┕ {results[0]} Vanilla(ish):‎ ‎ ‎ ‎ ‎ ‎ ‎ ‎  ‎`mc.nephbox.net`     \n"
            f"┕ {results[1]} Dawncraft :‎ ‎ ‎ ‎ ‎ ‎ ‎ ‎ `dawncraft.nephbox.net` \n"
            f"┕ {results[2]} Pixelmon:‎ ‎ ‎ ‎ ‎ ‎ ‎ ‎ ‎ ‎ ‎ ‎`pixelmon.nephbox.net`  \n"
            f"┕ {results[3]} All the Mods:‎ ‎ ‎ ‎ ‎ `allthemods.nephbox.net` \n"
            f"┕ {results[4]} Deceased: ‎ ‎ ‎ ‎ ‎ ‎ ‎ ‎ ‎ `deceased.nephbox.net`   \n"
            f"┕ {results[5]} Prominence: ‎ ‎ ‎ ‎ ‎ `prominence.nephbox.net` "
        ), inline=False)

        # Modpacks with links
        modpacks = {
            "Dawncraft": "https://www.curseforge.com/minecraft/modpacks/dawn-craft",
            "Pixelmon": "https://www.curseforge.com/minecraft/modpacks/the-pixelmon-modpack",
            "All the Mods": "https://www.curseforge.com/minecraft/modpacks/all-the-mods-9",
            "Deceased": "https://www.curseforge.com/minecraft/modpacks/deceasedcraft",
            "Prominence": "https://www.curseforge.com/minecraft/modpacks/prominence-2-rpg"
        }
        embed.add_field(name="Modpacks", value="\n".join([f"[{name}]({url})" for name, url in modpacks.items()]),
                        inline=True)

        # Wikis (if needed)
        wikis = {
            "Dawncraft Wiki": "https://dawncraft.fandom.com/wiki/DawnCraft_Wiki",
            "Pixelmon Wiki": "https://pixelmonmod.com/wiki/Main_Page",
            "All the Mods Wiki": "https://ftb.fandom.com/wiki/All_the_Mods_(modpack)",
            "Deceased Wiki": "https://deceasedcraft.wiki.gg/wiki/Main_Page",
            "Prominence Wiki": "https://rpg.prominence.wiki/"
        }
        embed.add_field(name="Wikis", value="\n".join([f"[{name}]({url})" for name, url in wikis.items()]), inline=True)


        # Other servers (no modpack required)
        embed.add_field(name="Other", value=(
            f"┕ {results[6]} Valheim:‎ ‎ ‎ ‎ ‎ ‎ ‎ ‎ ‎ ‎ `valheim.nephbox.net`\n"
            f"┕ {results[7]} Palworld:‎ ‎ ‎ ‎ ‎ ‎ ‎ ‎ ‎`palworld.nephbox.net:8766`\n"
            f"┕ {results[8]} Zomboid:‎ ‎ ‎ ‎ ‎ ‎ ‎ ‎ ‎`zomboid.nephbox.net:19132`\n"
            f"┕ {results[9]} Enshrouded: ‎ `enshrouded.nephbox.net:15637`"
        ), inline=False)

        # Additional information
        embed.add_field(name="Additional Information", value=(
            "If one of the servers are down and you want to play, open a support ticket! \n \n"
            "Servers can be turned on quickly once I am aware of the issue. Please note that not "
            "all servers are online 24/7 as they can be resource intensive."
        ), inline=False)

        # Embed footer and thumbnail
        embed.set_thumbnail(url=str(self.bot.user.avatar))
        embed.set_footer(text=f"Last Updated at {time} on {date}", icon_url=str(self.bot.user.avatar))

        return embed

    async def set_channel_and_message(self, channel_id, message_id):
        async with aiosqlite.connect(db_path) as conn:
            await conn.execute('''
            INSERT INTO server_status (id, channel_id, message_id) VALUES (?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET channel_id = excluded.channel_id, message_id = excluded.message_id
            ''', (1, channel_id, message_id))
            await conn.commit()

    # ---------------------------------------------------------------------------------------------------------------------
# UPDATE COMMANDS
# -------------------------------------------------------------------------------------------------------------------
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.command(description="Set the channel for server status updates and send the status message.")
    async def server_message(self, interaction: discord.Interaction):
        await interaction.response.defer()
        embed = await self.construct_embed()
        response = await interaction.followup.send(embed=embed, ephemeral=False)
        await self.set_channel_and_message(interaction.channel.id, response.id)
        await log_command_usage(self.bot, interaction)

# ---------------------------------------------------------------------------------------------------------------------
# Setup function
# ---------------------------------------------------------------------------------------------------------------------

async def setup(bot):
    async with aiosqlite.connect(db_path) as conn:
        await conn.execute('''
        CREATE TABLE IF NOT EXISTS server_status (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            channel_id INTEGER,
            message_id INTEGER
        )
        ''')
        await conn.commit()
    await bot.add_cog(ServerUpdatesCog(bot))
