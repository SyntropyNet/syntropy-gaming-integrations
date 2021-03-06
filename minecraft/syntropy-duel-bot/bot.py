import os
import time
import discord
import docker
import asyncio
import functools
import socket
from api import ApiManager
from aioify import aioify
from discord.ext import commands
from dotenv import load_dotenv


load_dotenv()
TOKEN = os.getenv("DISCORD_BOT_TOKEN")
NETWORK_NAME = os.getenv("DOCKER_NETWORK", "syntropynet-network")
PREFIX = ".synduel "

duel_info = {"running": False, "duel": {"duelers": [], "api_keys": {}, "ip": ""}}
duel_lock = asyncio.Lock()
bot = commands.Bot(command_prefix=PREFIX)
api_mgr = ApiManager(os.getenv("SYNTROPY_USERNAME"), os.getenv("SYNTROPY_PASSWORD"))
docker_client = docker.from_env()

def create_or_get_container():
    try:
        return docker_client.containers.get("syn-minecraft")
    except docker.errors.NotFound:
        pass

    container = docker_client.containers.run("itzg/minecraft-server", detach=True, ports={'25565/tcp': 25565}, volumes={'/data': {'bind': '/data', 'mode': 'rw'}}, name="syn-minecraft", network=NETWORK_NAME, environment=["SYNTROPY_SERVICE_NAME=minecraft", "EULA=TRUE"])

    return container

def get_container_ip(container):
    while True:
        try:
            container.reload()
            ip_addr = container.attrs['NetworkSettings']['Networks']['syntropy_network']['IPAddress']
            return ip_addr 
        except KeyError:
            continue


def get_connection_id(connections, agent_id):
    return [c["agent_connection_id"] for c in connections if c["agent_1_id"] == agent_id or c["agent_2_id"] == agent_id][0]


def get_subnet_id(services, service_name):
    service = [s for s in services if s["agent_service_name"] == service_name]
    if len(service) == 0: return None
    service = service[0]
    return service["agent_service_subnets"][0]["agent_service_subnet_id"]


@aioify
def start_duel(ctx, duelers):
    dueler_ids = {dueler: f"{dueler.id}-{dueler.name}" for dueler in duelers}

    for dueler in duelers:
        api_key = api_mgr.get_or_create_api_key(dueler_ids[dueler])[
            "api_key_secret"
        ]
        asyncio.run_coroutine_threadsafe(
            dueler.send(
                f"**Welcome to your Minecraft Duel.**\n\nSyntropy Agent API key: `{api_key}` \nSyntropy Agent Name: `{dueler.name}-{dueler.id}`\nInput these into your Syntropy Agent configuration to continue"
            ),
            bot.loop,
        )

    dueler_endpoints = {}

    for dueler in duelers:
        start_time = time.time()
        while True:
            endpoints = api_mgr.get_endpoints(dueler_ids[dueler])
            if len(endpoints) != 0:
                endpoint = endpoints[0]
                if endpoint["agent_is_online"]:
                    dueler_endpoints[dueler] = endpoint
                    break
            if time.time() - start_time > 180:
                asyncio.run_coroutine_threadsafe(ctx.message.channel.send("The duelers have failed to connect in time. The duel has been stopped."), bot.loop)
                return
            time.sleep(10)
            
               
    container = create_or_get_container()
    ip_addr = get_container_ip(container) 

    syn_network = api_mgr.recreate_network("minecraft-duel")

    agent_ids = []

    minecraft_endpoint = api_mgr.get_endpoints(socket.gethostname())[0] 

    for dueler in duelers:
        agent_ids += [dueler_endpoints[dueler]["agent_id"], minecraft_endpoint["agent_id"]]

    time.sleep(5)

    connections = api_mgr.add_connections(syn_network["network_id"], agent_ids) 

    for dueler in duelers:
        connection_id = get_connection_id(connections, dueler_endpoints[dueler]["agent_id"])
        services = api_mgr.get_services([dueler_endpoints[dueler]["agent_id"], minecraft_endpoint["agent_id"]]
) 
        subnet_id = get_subnet_id(services, "minecraft") 
        api_mgr.enable_service(connection_id, subnet_id)

    for dueler in duelers:
        asyncio.run_coroutine_threadsafe(
            dueler.send(
                "Your Minecraft Duel is ready. Connect to this server to continue: `{0}`".format(
                    ip_addr
                )
            ),
            bot.loop
        )


@bot.event
async def on_ready():
    print("The bot is ready")


@bot.command("create")
async def create_duel(ctx, enemy: discord.Member):
    async with duel_lock:
        if duel_info["running"]:
            await ctx.message.channel.send("There is currently a duel running")
            return
        else:
            duel_info["running"] = True
    await ctx.message.channel.send(
        f"{ctx.author.name} has challenged {enemy.name} to a duel!"
    )
    await start_duel(ctx, [ctx.author, enemy])


bot.run(TOKEN)
