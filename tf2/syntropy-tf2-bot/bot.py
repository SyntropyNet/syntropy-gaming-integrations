import os
import time
import discord

import asyncio
import functools
import socket
from container_manager import ContainerManager
from api import ApiManager
from aioify import aioify
from discord.ext import commands
from dotenv import load_dotenv
from syntropy_sdk import AgentsPairObject

load_dotenv()
TOKEN = os.getenv("DISCORD_BOT_TOKEN")
SRCDS_TOKEN=os.getenv("SRCDS_TOKEN")
NETWORK_NAME = os.getenv("DOCKER_NETWORK", "syntropynet-network")
PREFIX = ".syntf2 "
CONTAINER_NAME = "syn-tf2"

tf2_lock = asyncio.Lock()
bot = commands.Bot(command_prefix=PREFIX)
api_mgr = ApiManager(os.getenv("SYNTROPY_ACCESS_TOKEN"))
container_manager = ContainerManager(CONTAINER_NAME, NETWORK_NAME, SRCDS_TOKEN)

def get_subnet_id(services, service_name, terraria_agent_id):
    services = services[0].agent_1.agent_services if services[0].agent_1.agent_id == terraria_agent_id else services[0].agent_2.agent_services
    service = [s for s in services if s.agent_service_name == service_name]
    if len(service) == 0: return None
    service = service[0]
    return service.agent_service_subnets[0].agent_service_subnet_id


@aioify
def start_tf2(ctx, players):
    players_ids = {player: f"{player.name}-{player.id}" for player in players}
    print("sending api keys to players")
    for player in players:
        api_key = api_mgr.get_or_create_api_key(players_ids[player])
        if api_key == -1:
            api_key = "use the api key bot provided before"
        else:
            api_key = api_key.api_key_secret
        asyncio.run_coroutine_threadsafe(
            player.send(
                f"**Welcome to your Team Fortress 2 server.**\n\nSyntropy Agent API key: `{api_key}` \nSyntropy Agent Name: `{player.name}-{player.id}`\nInput these into your Syntropy Agent configuration to continue"
            ),
            bot.loop,
        )

    players_endpoints = {}

    for player in players:
        start_time = time.time()
        print("waiting for player " + player.name)
        while True:
            endpoints = api_mgr.get_endpoints(players_ids[player])
            if len(endpoints) != 0:
                endpoint = endpoints[0]
                if endpoint.agent_is_online:
                    players_endpoints[player] = endpoint
                    break
            if time.time() - start_time > 180:
                asyncio.run_coroutine_threadsafe(ctx.message.channel.send("Players have failed to connect in time. The server has been stopped."), bot.loop)
                return
            time.sleep(10)
            
    container_manager.number_of_players = len(players)
    print("starting container")
    container = container_manager.start_container()
    ip_addr = container_manager.get_container_ip(container)

    agent_ids = []

    tf2_endpoint = api_mgr.get_endpoints(socket.gethostname())[0]

    for player in players:
        agent_ids.append(AgentsPairObject(players_endpoints[player].agent_id, tf2_endpoint.agent_id))
    time.sleep(5)

    api_mgr.remove_all_connections(tf2_endpoint.agent_id)
    connections_ids = api_mgr.add_connections(agent_ids, tf2_endpoint.agent_id)

    for player in players:
        connection_id = connections_ids[players_endpoints[player].agent_id]
        services = api_mgr.get_services([connection_id]) 
        subnet_id = get_subnet_id(services, "tf2", tf2_endpoint.agent_id)
        api_mgr.enable_service(connection_id, subnet_id)

    for player in players:
        asyncio.run_coroutine_threadsafe(
            player.send(
                "Your Team Fortress 2 server is ready. Connect to this server to continue: steam://connect/{0}".format(
                    ip_addr
                )
            ),
            bot.loop
        )


@bot.event
async def on_ready():
    print("The bot is ready")


@bot.command("start")
async def start_server(ctx, *players: discord.Member):
    async with tf2_lock:
        if container_manager.is_running():
            await ctx.message.channel.send("Server is already running")
            return
    await ctx.message.channel.send(
        f"{ctx.author.name} has created a Team Fortress 2 server!"
    )
    await start_tf2(ctx, [ctx.author] + list(players))

@bot.command("stop")
async def stop_server(ctx):
    async with tf2_lock:
        if not container_manager.is_running():
            await ctx.message.channel.send("Server is not running")
            return
        
    await ctx.message.channel.send("Stopping the server")
    container_manager.stop_container()

bot.run(TOKEN)
