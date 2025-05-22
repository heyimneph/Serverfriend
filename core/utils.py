import discord
import os
import logging
import aiosqlite

# Ensure the database directory exists
os.makedirs('./data/databases', exist_ok=True)

# Path to the SQLite database
db_path = './data/databases/serverfriend.db'

# ---------------------------------------------------------------------------------------------------------------------
# Command Logging
# ---------------------------------------------------------------------------------------------------------------------
async def log_command_usage(bot, interaction):
    try:
        # Gather command options and values
        command_options = ""
        if 'options' in interaction.data:
            for option in interaction.data['options']:
                command_options += f"{option['name']}: {option.get('value', 'Not provided')}\n"

        async with aiosqlite.connect(db_path) as conn:
            logging.info(f"Connected to the database at {db_path}")
            async with conn.execute(
                'SELECT log_channel_id FROM config WHERE guild_id = ?', (interaction.guild.id,)
            ) as cursor:
                row = await cursor.fetchone()

                if row:
                    log_channel_id = row[0]
                    log_channel = bot.get_channel(int(log_channel_id))

                    if log_channel:
                        embed = discord.Embed(
                            description=f"Command: `{interaction.command.name}`",
                            color=discord.Color.blue()
                        )
                        embed.add_field(name="User", value=interaction.user.mention, inline=True)
                        embed.add_field(name="Guild ID", value=interaction.guild.id, inline=True)
                        embed.add_field(name="Channel", value=interaction.channel.mention, inline=True)
                        if command_options:
                            embed.add_field(name="Command Options", value=command_options.strip(), inline=False)
                        embed.set_footer(text=f"User ID: {interaction.user.id}")
                        embed.set_author(name=str(interaction.user), icon_url=interaction.user.display_avatar.url)
                        embed.timestamp = discord.utils.utcnow()
                        await log_channel.send(embed=embed)
                    else:
                        logging.error(f"Log channel not found for log_channel_id: {log_channel_id}")
                else:
                    logging.error(f"No log_channel_id found for guild_id: {interaction.guild.id}")

    except aiosqlite.Error as e:
        logging.error(f"Error logging command usage: {e}")
    except Exception as e:
        logging.error(f"Unexpected error logging command usage: {e}")


async def check_permissions(interaction):
    async with aiosqlite.connect(db_path) as conn:
        cursor = await conn.execute('''
            SELECT can_use_commands FROM permissions WHERE guild_id = ? AND user_id = ?
        ''', (interaction.guild_id, interaction.user.id))
        permission = await cursor.fetchone()
        return permission and permission[0]