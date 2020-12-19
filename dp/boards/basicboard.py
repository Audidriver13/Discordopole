import discord
import json

from datetime import datetime

from dp.utils.util import Area, DPEmote, get_loading_footer
from dp.pogo import Stop, Gym, Mon, Item

"""
There's a big Board class (Board()) - Each Board is a child class of that.
When a Board is generated, it first generates a list with the objects it'll display.
An object could e.g. be a Quest reward or a Raid.
This object then gets transferred to the big generate_text() function which takes
care of embed generation, templates, etc. - frontend stuff that's the same across
all boards basically. Templates are generated in utils/templates.py, most smaller
classes used can be found in utils/util.py
"""

class Board():
    def __init__(self, dp, board):
        self.board = board
        self.dp = dp
        self.embed = discord.Embed()
        self.area = Area(dp, board["area"])
        self.static_map = ""
    
    def embed_details(self, text):
        self.embed.description = text
        self.embed.title = self.board.get("title", "")
        self.embed.timestamp = datetime.utcnow()
        self.embed.set_footer(text=self.area.name)
        self.embed.set_image(url=self.static_map)

    def generate_text(self, objs, template):
        text = ""
        for obj in objs:
            entry = template.get(obj)
            if len(text) + len(entry) >= 2048:
                break
            text += entry

        if len(objs) == 0:
            text = self.bot.locale["empty_board"]
            self.static_map = ""

        self.embed_details(text)
    
    def standard_dict(self):
        for k, v in self.standard_format.items():
            if k not in self.board.keys():
                self.board[k] = v
    
    async def get(self):
        await self.get_objs()
        await self.generate_embed()

        return self.embed

#######################################################################################
# Grunt BOARD
#######################################################################################

class Grunt:
    def __init__(self, bot, gid, start, end, stop):
        self.id = gid
        self.start = start
        self.end = end
        self.stop = stop

        self.mons = []
        for mid in bot.available_grunts[gid]:
            mids = mid.split("_")
            self.mons.append(Mon(bot, mon_id=mids[0], form=mids[1]))
    
    async def create_emotes(self):
        for mon in self.mons:
            await mon.get_emote()

class GruntBoard(Board):
    def __init__(self, bot, board):
        super().__init__(bot, board)
        self.grunts = []
        self.available_grunts = bot.available_grunts

        self.standard_format = {
            "channel_id": "",
            "message_id": "",
            "title": self.bot.locale["grunts"],
            "area": "",
            "wait": 2,
            "mons": [],
            "static_map": False
        }
        self.standard_dict()

    async def get_objs(self):
        gids = {}
        for mon in self.board["mons"]:
            for gid, data in self.bot.available_grunts.items():
                if mon in [int(m.split("_")[0]) for m in data]:
                    gids[gid] = data
        grunts = await self.bot.queries.execute("active_grunts", sql_fence=self.area.sql_fence, extra=",".join(gids.keys()))
        for pid, name, image, lat, lon, start, end, gid in grunts:
            stop = Stop(pid, lat, lon, name, image)
            grunt = Grunt(self.bot, gid, start, end, stop)
            await grunt.create_emotes()
            self.grunts.append(grunt)

    async def generate_embed(self):
        self.bot.templates.grunt_board()
        template =  self.bot.templates.template
        if self.board["static_map"]:
            self.static_map = await self.bot.static_map.grunt(self.grunts)
        else:
            self.static_map = ""
        self.generate_text(self.grunts, template)


#######################################################################################
# STAT BOARD
#######################################################################################

class StatBoard(Board):
    def __init__(self, bot, board):
        super().__init__(bot, board)
        self.all_stats = []
        self.templates = {
            "default": "{emote} {lang}"
        }

        self.standard_format = {
            "channel_id": "",
            "message_id": "",
            "title": self.bot.locale["stats"],
            "area": "",
            "wait": 2,
            "type": []
        }
        self.standard_dict()

    def gen(self, stat, template, lang, emote=""):
        t = template.format(emote=emote, lang=lang)
        return t.format(x=self.vals[stat][0][0])

    async def get_stats(self):
        mon_block = ""
        gym_block = ""
        stop_block = ""
        text = ""
        stats = ["gym_amount", "raid_active", "egg_active"]
        self.vals = {}
        for stat in self.all_stats:
            if stat in self.board["type"]:
                stats.append(stat)

        for stat in stats:
            val = await self.bot.queries.execute(stat, sql_fence=self.area.sql_fence)
            self.vals[stat] = val

        for stat in stats:    
            if "mon" in stat:
                continue

            elif stat == "gym_amount":
                g = self.gen(stat, self.templates["default"], self.bot.locale["total_gyms"], self.bot.custom_emotes["gym_white"]) + "\n"
            elif stat == "raid_active":
                g = self.gen(stat, self.templates["default"], self.bot.locale["active_raids"], self.bot.custom_emotes["raid"])
                if "egg_active" in stats:
                    g += " | " + self.bot.locale["eggs"].format(x=self.vals["egg_active"][0][0]) + "\n"
                    stats.remove("egg_active")
            elif stat == "egg_active":
                g = self.gen(stat, self.templates["default"], self.bot.locale["active_eggs"], self.bot.custom_emotes["raid"]) + "\n"
            gym_block += g
        text = mon_block + "\n" + gym_block + "\n" + stop_block
        self.embed_details(text)

#######################################################################################
# HUNDO BOARD
#######################################################################################

class HundoBoard(Board):
    def __init__(self, bot, board):
        super().__init__(bot, board)
        self.mons = []

    async def get_objs(self):
        hundos = await self.bot.queries.get_active_hundos(self.bot.config, self.area.sql_fence)
        for mid, form, atk, defe, sta in hundos:
            mon = Mon(self.bot, mid, form=form)
            self.mons.append(mon)

    async def generate_embed(self):
        self.bot.templates.hundo_board()
        template = self.bot.templates.template
        self.static_map = await self.bot.static_map.hundo(self.mons)
        self.generate_text(self.mons, template)

#######################################################################################
# QUEST BOARD
#######################################################################################

class Reward():
    def __init__(self, bot, rtype, item, stop):
        if rtype in ["item", "mon"]:
            self.type = rtype
        else:
            self.type = None
        
        self.bot = bot
        self.item = item
        self.stop = stop
    
    async def create_emote(self):
        await self.item.get_emote()

class QuestBoard(Board):
    def __init__(self, bot, board):
        super().__init__(bot, board)
        self.rewards = []

        self.standard_format = {
            "channel_id": "",
            "message_id": "",
            "title": self.bot.locale["raids"],
            "area": "",
            "wait": 2,
            "mons": [],
            "items": []
        }
        self.standard_dict()

    async def get_objs(self):
        quests = await self.bot.queries.execute("active_quests", sql_fence=self.area.sql_fence)

        for quest_json, quest_text, lat, lon, stop_name, stop_id in quests:
            quest_json = json.loads(quest_json)

            if self.bot.config.db_scan_schema == "rdm":
                mon_id = quest_json[0]["info"].get("pokemon_id", None)
                item_id = quest_json[0]["info"].get("item_id", None)
            elif self.bot.config.db_scan_schema == "mad":
                item_id = quest_json[0]["item"]["item"]
                mon_id = quest_json[0]["pokemon_encounter"]["pokemon_id"]
            
            r_item = None
            for item in self.board["items"]:
                if item_id == item.id:
                    r_item = item
                    rtype = "item"
                    break
            for mon in self.board["mons"]:
                if mon_id == mon.id:
                    r_item = mon
                    rtype = "item"
                    break

            if r_item is not None:
                reward = Reward(self.bot, rtype, r_item, Stop(stop_id, lat, lon, stop_name, img=None))
                await reward.create_emote()
                self.rewards.append(reward)

    async def generate_embed(self):
        self.bot.templates.quest()
        template =  self.bot.templates.template
        self.static_map = await self.bot.static_map.quest(self.rewards)
        self.generate_text(self.rewards, template)
    
    def _get_embed_one_reward(self):
        rewards = self.board["mons"] + self.board["items"]
        if len(rewards) == 1:
            self.embed.set_thumbnail(url=rewards[0].img)
            if self.board.get("title", self.bot.locale["quests"]) == self.bot.locale["quests"]:
                self.board["title"] = rewards[0].name + " " + self.bot.locale["quests"]

    async def generate_empty_embed(self):
        self._get_embed_one_reward()
        loading, load_gif = get_loading_footer(self.bot, self.bot.locale['loading_quests'], self.area.name)
        self.embed.description = ""
        self.embed.title = self.board["title"]
        self.embed.set_footer(text=loading, icon_url=load_gif)

    async def delete_emotes(self):
        deleted = []
        for reward in self.rewards:
            if reward.item.dp_emote is not None and reward.item.id not in deleted:
                await reward.item.dp_emote.delete()
                deleted.append(reward.item.id)