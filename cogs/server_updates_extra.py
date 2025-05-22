import discord
import logging
import socket
import asyncio
import aiosqlite
import time
import os

from discord import app_commands
from discord.ext import commands, tasks
from mcstatus import JavaServer

# Ensure the database directory exists
os.makedirs('./data/databases', exist_ok=True)

# Connect to SQLite database asynchronously
db_path = './data/databases/serverfriend.db'

# ---------------------------------------------------------------------------------------------------------------------
# Logging Configuration
# ---------------------------------------------------------------------------------------------------------------------

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

# ----------------------------------------------------------------------------------------------------------------------
# Utility Functions
# ----------------------------------------------------------------------------------------------------------------------
def send_steam_query(ip: str, port: int, timeout: float = 5.0) -> str:
    try:
        message = b'\xFF\xFF\xFF\xFFTSource Engine Query\x00'
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.settimeout(timeout)
            sock.sendto(message, (ip, port))
            try:
                data, _ = sock.recvfrom(4096)
                return "🟢"  # Server responded
            except socket.timeout:
                return "🔴"  # No response
    except Exception as e:
        logging.error(f"Error in send_steam_query: {e}")
        return "🔴"

def ping_udp_server(ip: str, port: int, timeout: float = 5.0) -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.settimeout(timeout)
            message = b"Test packet"
            sock.sendto(message, (ip, port))
            try:
                data, _ = sock.recvfrom(1024)
                return "🟢"  # Server responded
            except socket.timeout:
                return "🔴"  # No response
    except Exception as e:
        logging.error(f"Error in ping_udp_server: {e}")
        return "🔴"

def check_tcp_server_status(ip: str, port: int, timeout: float = 5.0) -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(timeout)
            sock.connect((ip, port))
            return "🟢"  # Server is UP
    except Exception as e:
        logging.error(f"Error in check_tcp_server_status: {e}")
        return "🔴"  # Server is DOWN

# ----------------------------------------------------------------------------------------------------------------------
# ServerUpdatesExtraCog Class
# ----------------------------------------------------------------------------------------------------------------------
class ServerUpdatesExtraCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.server_data = []

    @commands.Cog.listener()
    async def on_ready(self):
        await self.cog_load()
        self.server_status_task.start()
        logger.error(f"Game Server - Channels Task: Started")


    async def cog_load(self):
        async with aiosqlite.connect(db_path) as conn:
            async with conn.execute('SELECT guild_id FROM servers') as cursor:
                data = await cursor.fetchall()
                self.server_data = data

    def cog_unload(self):
        self.server_status_task.cancel()

    @tasks.loop(seconds=10)
    async def server_status_task(self):
        async with aiosqlite.connect(db_path) as conn:
            async with conn.execute('SELECT * FROM servers') as cursor:
                async for row in cursor:
                    guild = self.bot.get_guild(row[1])
                    if guild:
                        server_entry = row
                        await self.update_server_status(guild, server_entry)

    async def update_server_status(self, guild, server_entry):
        channel = guild.get_channel(server_entry[6])  # channel_id is at index 6 in the server_entry tuple
        if not channel:
            logger.error(f"Channel with ID {server_entry[6]} not found in {guild.name}.")
            return

        status = await self.check_server_status(server_entry)
        new_name = f"{status}{server_entry[2]}"  # name is at index 2 in the server_entry tuple

        if new_name != channel.name:
            await channel.edit(name=new_name)

    async def check_server_status(self, server_entry):
        ip = server_entry[3]  # ip is at index 3 in the server_entry tuple
        port = server_entry[5] if server_entry[5] else 25565  # port is at index 5 in the server_entry tuple
        server_type = server_entry[4]  # type is at index 4 in the server_entry tuple

        # Use the appropriate check function based on the server type
        if server_type == "minecraft":
            return await self.check_minecraft_status(ip)
        elif server_type == "steam":
            return await self.check_steam_query_status(ip, port)
        elif server_type == "udp":
            return await self.check_udp_status(ip, port)
        elif server_type == "tcp":
            return await self.check_tcp_status(ip, port)
        else:
            return "🔴"

    async def check_minecraft_status(self, ip):
        try:
            server = JavaServer.lookup(ip)
            server.status()
            return "🟢"
        except Exception:
            return "🔴"

    async def check_steam_query_status(self, ip, port):
        return await asyncio.get_event_loop().run_in_executor(None, send_steam_query, ip, port)

    async def check_udp_status(self, ip, port):
        return await asyncio.get_event_loop().run_in_executor(None, ping_udp_server, ip, port)

    async def check_tcp_status(self, ip, port, timeout=5.0, retries=1, delay=5):
        """Asynchronously check TCP server status with retry logic."""
        for attempt in range(retries):
            try:
                # Attempt to open a connection to the specified IP and port
                _, writer = await asyncio.wait_for(asyncio.open_connection(ip, port), timeout=timeout)
                writer.close()
                await writer.wait_closed()
                logger.info(f"Successfully connected to {ip}:{port} on attempt {attempt + 1}")
                return "🟢"  # Server is UP
            except asyncio.TimeoutError:
                logger.error(f"Timeout Error: Connection to {ip}:{port} ")
                return "🔴"
            except ConnectionRefusedError:
                logger.error(f"Connection Refused: Connection to {ip}:{port} refused on attempt {attempt + 1}")
                return "🔴"
            except Exception as e:
                logger.error(f"Error in check_tcp_server_status for {ip}:{port} on attempt {attempt + 1}: {e}")
                return "🔴"

            if attempt < retries - 1:
                time.sleep(delay)  # Wait before retrying

        return "🔴"  # Server is DOWN after retries

# ---------------------------------------------------------------------------------------------------------------------
# Add/Remove Category for Server Updates
# ---------------------------------------------------------------------------------------------------------------------
    async def fetch_server_category(self, guild_id):
        async with aiosqlite.connect(db_path) as conn:
            async with conn.execute('SELECT * FROM server_updates WHERE guild_id = ?', (guild_id,)) as cursor:
                return await cursor.fetchone()

    async def fetch_server_category_id(self, guild_id):
        async with aiosqlite.connect(db_path) as conn:
            async with conn.execute('SELECT server_category_id FROM server_updates WHERE guild_id = ?', (guild_id,)) as cursor:
                category_document = await cursor.fetchone()
                return category_document[0] if category_document else None

    class CategorySelect(discord.ui.Select):
        def __init__(self, cog, categories, *args, **kwargs):
            self.cog = cog
            options = [discord.SelectOption(label=category.name, value=category.id) for category in categories]
            super().__init__(placeholder="Select a category", min_values=1, max_values=1, options=options, *args, **kwargs)

        async def callback(self, interaction: discord.Interaction):
            selected_category_id = self.values[0]
            category = next((cat for cat in interaction.guild.categories if str(cat.id) == selected_category_id), None)

            if category:
                async with aiosqlite.connect(db_path) as conn:
                    await conn.execute('''
                    INSERT INTO server_updates (guild_id, server_category_id, server_category_name) VALUES (?, ?, ?)
                    ON CONFLICT(guild_id) DO UPDATE SET server_category_id = excluded.server_category_id, server_category_name = excluded.server_category_name
                    ''', (interaction.guild.id, selected_category_id, category.name))
                    await conn.commit()

                await interaction.response.send_message(f"`Success: Selected category '{category.name}'`", ephemeral=True)

    class RemovalConfirm(discord.ui.View):
        def __init__(self, cog, category_id, category_name):
            super().__init__(timeout=60)
            self.cog = cog
            self.category_id = category_id
            self.category_name = category_name

        @discord.ui.button(label="Confirm Removal", style=discord.ButtonStyle.red)
        async def confirm_removal(self, interaction: discord.Interaction, button: discord.ui.Button):
            async with aiosqlite.connect(db_path) as conn:
                await conn.execute('DELETE FROM server_updates WHERE guild_id = ? AND server_category_id = ?', (interaction.guild.id, self.category_id))
                await conn.commit()

            await interaction.response.send_message(f"`Success: Category '{self.category_name}' has been removed from monitoring.`", ephemeral=True)
            self.stop()

    @app_commands.command(description="Select a category to monitor for Server Updates")
    @app_commands.checks.has_permissions(administrator=True)
    async def add_category(self, interaction: discord.Interaction):
        categories = interaction.guild.categories

        if not categories:
            await interaction.response.send_message("No categories found in this server.")
            return

        view = discord.ui.View()
        view.add_item(self.CategorySelect(self, categories=categories))
        await interaction.response.send_message("Select a category to monitor:", view=view, ephemeral=True)


    @app_commands.command(description="Remove Server Update Category")
    @app_commands.checks.has_permissions(administrator=True)
    async def remove_category(self, interaction: discord.Interaction):
        monitored_category = await self.fetch_server_category(interaction.guild.id)

        if monitored_category:
            category_name = monitored_category[2]  # server_category_name is at index 2 in the monitored_category tuple
            category_id = monitored_category[1]  # server_category_id is at index 1 in the monitored_category tuple

            view = self.RemovalConfirm(self, category_id, category_name)
            await interaction.response.send_message(f"Are you sure you want to remove '{category_name}' from monitoring?", view=view, ephemeral=True)
        else:
            await interaction.response.send_message("No category is currently being monitored.", ephemeral=True)

    @app_commands.command(description="Add a game server to monitor")
    @app_commands.describe(name="Name of the server", ip="IP address of the server",
                           type="Type of the game server (udp, tcp, steam, minecraft)",
                           port="Optional port for the server")
    @app_commands.checks.has_permissions(administrator=True)
    async def add_server(self, interaction: discord.Interaction, name: str, ip: str, type: str, port: int = None):
        category_id = await self.fetch_server_category_id(interaction.guild.id)
        if not category_id:
            await interaction.response.send_message("No category is set for monitoring.", ephemeral=True)
            return

        category = discord.utils.get(interaction.guild.categories, id=int(category_id))
        if not category:
            await interaction.response.send_message("The monitored category does not exist.", ephemeral=True)
            return

        channel = discord.utils.get(category.text_channels, name=name)
        if not channel:
            channel = await category.create_text_channel(name)
            await channel.send(f"Check out <#1141742882764628096> for more information!")  # Tag the specific channel ID

        async with aiosqlite.connect(db_path) as conn:
            await conn.execute('''
            INSERT INTO servers (guild_id, name, ip, type, port, channel_id) VALUES (?, ?, ?, ?, ?, ?)
            ''', (interaction.guild.id, name, ip, type, port, channel.id))
            await conn.commit()

        await interaction.response.send_message(f"Server {name} has been added and will be monitored.", ephemeral=True)

    @app_commands.command(description="Remove a game server from monitoring")
    @app_commands.checks.has_permissions(administrator=True)
    async def remove_server(self, interaction: discord.Interaction):
        async with aiosqlite.connect(db_path) as conn:
            async with conn.execute('SELECT id, name, channel_id FROM servers WHERE guild_id = ?', (interaction.guild.id,)) as cursor:
                servers = await cursor.fetchall()

        if not servers:
            await interaction.response.send_message("No servers are being monitored.", ephemeral=True)
            return

        view = discord.ui.View()
        view.add_item(self.ServerSelect(self, servers=servers))
        await interaction.response.send_message("Select a server to remove:", view=view, ephemeral=True)

    class ServerSelect(discord.ui.Select):
        def __init__(self, cog, servers, *args, **kwargs):
            self.cog = cog
            self.servers = servers
            options = [discord.SelectOption(label=server[1], value=str(server[0])) for server in servers]
            super().__init__(placeholder="Select a server", min_values=1, max_values=1, options=options, *args, **kwargs)

        async def callback(self, interaction: discord.Interaction):
            selected_server_id = int(self.values[0])
            server = next((server for server in self.servers if server[0] == selected_server_id), None)

            if server:
                async with aiosqlite.connect(db_path) as conn:
                    await conn.execute('DELETE FROM servers WHERE id = ?', (selected_server_id,))
                    await conn.commit()

                channel = interaction.guild.get_channel(server[2])
                if channel:
                    await channel.delete()

                await interaction.response.send_message(f"Server '{server[1]}' has been removed and its channel deleted.", ephemeral=True)

# ----------------------------------------------------------------------------------------------------------------------
# Setup Function
# ----------------------------------------------------------------------------------------------------------------------
async def setup(bot):
    async with aiosqlite.connect(db_path) as conn:
        await conn.execute('''
        CREATE TABLE IF NOT EXISTS server_updates (
            guild_id INTEGER PRIMARY KEY,
            server_category_id INTEGER,
            server_category_name TEXT
        )
        ''')

        await conn.execute('''
        CREATE TABLE IF NOT EXISTS servers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER,
            name TEXT,
            ip TEXT,
            type TEXT,
            port INTEGER,
            channel_id INTEGER
        )
        ''')

    await bot.add_cog(ServerUpdatesExtraCog(bot))
