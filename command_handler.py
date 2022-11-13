import asyncio
import time
import re
import subprocess
import discord
from discord import ui
from discord.ext import commands

import main


def parse_price(price_input, cur_price, cad_usd_conversion_ratio):
    price_input = price_input.lower()
    try:
        amt = float(re.findall(r"\d+\.?\d*", price_input)[0])
        if "k" in price_input:
            amt *= 1000
        if "+" in price_input:
            amt += cur_price
        if "-" in price_input:
            amt -= cur_price
        if "ca" in price_input:
            amt /= cad_usd_conversion_ratio

        return round(amt, 2)

    except IndexError or ValueError:
        return None


def alert_val_to_string(alert_val):
    if alert_val is None:
        return "Not Set"
    else:
        return "$" + str(alert_val)


def parse_single_multi_val(num, string):
    if num == 1:
        return string
    else:
        return string + 's'


class EmbedView(ui.View):
    def __init__(self, client):
        super().__init__()
        self.client = client

    @ui.button(label="Restart Bots", style=discord.ButtonStyle.red)
    async def restart_bots(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.channel.send("Restarting all price bots.")
        await self.stop()
        await asyncio.sleep(main.delete_cooldown)
        try:
            subprocess.Popen("sudo service crypto-price-bots restart", shell=True, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE)
        except discord.errors.HTTPException as _e:
            await interaction.channel.send(str(_e))

    @ui.button(label="Clear Alerts", style=discord.ButtonStyle.blurple)
    async def clear_alerts(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await interaction.channel.send(f"Cleared all alerts.")
        self.client.alert_handler.clear_all_alerts()


class CommandHandler(commands.Cog):
    def __init__(self, client):
        self.client = client

    @commands.Cog.listener()
    async def on_message(self, m):
        # On mention activities
        if m.content in [f"<@{self.client.user.id}>", f"<@!{self.client.user.id}>"]:
            # Determine ticker through getting the nickname of the bot, usually in this format:
            # BTC - $30495.40
            embed_view = EmbedView(self.client)

            embed = discord.Embed(description=f"{self.client.asset}: ${round(self.client.usd_price, 4)}",
                                  color=0x00ff00)

            embed.add_field(name="CAD:", value=f"${round(self.client.usd_price * self.client.usd_cad_conversion, 3)}")
            embed.add_field(name="Price up:", value=alert_val_to_string(self.client.alert_up))
            embed.add_field(name="Price down:", value=alert_val_to_string(self.client.alert_down))

            await m.delete()

            msg = await m.channel.send(embed=embed, view=EmbedView(self.client))

            await embed_view.wait()
            embed_view.clear_items()
            await msg.edit(view=embed_view)

        # Set price alerts
        # * Intelligent command setter
        # * User only needs to mention the relevant price bot, it will then algorithmically determine the proper pair to assign it to
        elif m.content.startswith(f"<@{self.client.user.id}>") or m.content.startswith(f"<@!{self.client.user.id}>"):
            m_list = m.content.split()  # Should return list: [asset ticker, number]

            bot_member = m.guild.get_member(self.client.user.id)

            # If alert price not valid: Ignore since message could be generic
            # If alert price valid: Set alert
            alert_string = ""
            for i in range(1, len(m_list)):
                alert_string += m_list[i]

            prim_curr_price = float(re.findall(r"\d+\.\d+", bot_member.nick)[0])
            prim_alert_price = parse_price(alert_string, prim_curr_price, self.client.usd_cad_conversion)

            await m.reply(self.client.alert_handler.set_alert(prim_curr_price, prim_alert_price))

    @commands.command(name="alerts")
    async def alerts(self, context):
        # If one of the alerts is not None, the bot replies with the alerts
        if (self.client.alert_up is not None) or (self.client.alert_down is not None):
            embed = discord.Embed(title=f"Current Alerts", color=0x00ff00)
            embed.add_field(name="Asset:", value=f"{self.client.asset}")
            embed.add_field(name="Price up:", value=alert_val_to_string(self.client.alert_up))
            embed.add_field(name="Price down:", value=alert_val_to_string(self.client.alert_down))

            await context.message.reply(embed=embed)
        await context.message.add_reaction("\U00002705")  # Add a reaction since bots without alerts don't reply

    @commands.command(name="uptime")
    async def uptime(self, context):
        await context.send(
            f"{self.client.name} price bot online since <t:{self.client.start_time}> (<t:{self.client.start_time}:R>)")

    @commands.command(name="last")
    async def last(self, context):
        wstime = self.client.last_ws_update
        await context.send(
            f"{self.client.asset}: Last websocket message received on <t:{wstime}:D> at <t:{wstime}:t> (<t:{wstime}:R>)")

    @commands.command(name="requests")
    async def requests(self, context):
        await context.send(
            f"{self.client.name} price bot has made {self.client.discord_api_gets} GETs and {self.client.discord_api_posts} POSTs to the Discord API since <t:{self.client.start_time}>  (<t:{self.client.start_time}:R>).")

    @commands.command(name="var")
    async def var(self, context):
        await context.send(
            f"{self.client.name} price bot variability is {self.client.variability_threshold * 100}% (approx. ${round(self.client.usd_price * self.client.variability_threshold, 4)}.")

    @commands.command(name="ping")
    async def ping(self, context):
        before_ping = time.monotonic()
        message_ping = await context.send("Pong!")
        ping_time = (time.monotonic() - before_ping) * 1000
        await message_ping.edit(content=f"Pong! `{int(ping_time)}ms`")


async def setup(client):
    await client.add_cog(CommandHandler(client))
