import copy
import discord
import requests
from discord.ext import commands, tasks
from dotenv import load_dotenv
import os
import re
import time
import traceback2
from tqdm import tqdm
import json

load_dotenv(verbose=True)
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

bot = commands.Bot("!", self_bot=True, intents=discord.Intents.default())

plugin_channel_id = 961782195767365732
theme_channel_id = 961782176062509117

# 正規表現
js_pattern = re.compile(r"https?://[\w!?/+\-_~;.,*&@#$%()'[\]]+\.js")
json_pattern = re.compile(r"https?://[\w!?/+\-_~;.,*&@#$%()'[\]]+\.json")
desc_pattern1 = re.compile(r"{name:[a-zA-Z_]+,.*?description:([a-zA-Z_]+)")  # <一般的なパターン> 1~2文字の略された変数で、その変数の指す値をとりに行く
desc_pattern2 = re.compile(r'version:"([0-9.]+)",.*?description:["\'](.*?)["\']')  # ""で文字列が直接入っているパターン(より絞れる)
desc_pattern3 = re.compile(r'{name:"[a-zA-Z_]+",.*?description:["\'](.*?)["\']')  # ""で文字列が直接入っているパターン2(versionがない場合もあるので/コマンドがひっかる場合もあるので注意)
desc_pattern4 = re.compile(r'description:\s*["\'](.*?)["\']')  # minifyされていないコード
variable_pattern = rf'=["\'](.*?)["\'],'
version_pattern = re.compile(r'version:\s*["\']([0-9.]+)["\']')
version_pattern2 = re.compile(r"{name:[a-zA-Z_]+,.*?version:([a-zA-Z_]+)")
version_pattern_raw = re.compile(r'[0-9.]+')

custom_plugins = ["https://raw.githubusercontent.com/xenos1337/enmity-plugins/main/ReactDevTools/dist/ReactDevTools.js"]
blacklisted = ["https://plugins.panties.moe/plugins/EnableStaging.js"]


def push_updates(is_fetch, plugin_updated=False, theme_updated=False):
    t = str(time.time())

    if not plugin_updated and not theme_updated:  # 更新無し
        return

    if plugin_updated:
        with open("plugins_update.txt", "w") as f:
            f.write(t)
    if theme_updated:
        with open("themes_update.txt", "w") as f:
            f.write(t)

    mode = "Fetch" if is_fetch else "Dump"
    print(f"-----pushing--[test]---{is_fetch}")
    # os.system("git add .")
    # os.system(f'git commit -m "{mode} - {t}"')
    # os.system("git push")


@bot.event
async def on_ready():
    print(f"[*] Logged in as {bot.user}")
    loop.start()

    # plugin_updated = fetch_plugins()
    # theme_updated = fetch_themes()
    # push_updates(True, plugin_updated, theme_updated)

    # await dump_plugins()
    # await dump_themes()
    # push_updates(False, True, True)

    # t = str(time.time())
    # with open("plugins_update.txt", "w") as f:
    #     f.write(t)
    # with open("themes_update.txt", "w") as f:
    #     f.write(t)


@bot.event
async def on_message(message):
    plugin_channel_id = 1059902945224826900
    theme_channel_id = 1059902961741992026
    try:
        # dumpの時は必ず変更があるので常に更新してpushする
        if message.channel.id == plugin_channel_id:
            if list(set(js_pattern.findall(message.content))):
                await dump_plugins()
                push_updates(False, True, False)
        elif message.channel.id == theme_channel_id:
            if list(set(json_pattern.findall(message.content))):
                await dump_themes()
                push_updates(False, False, True)
    except:
        print("[x] Error on meeesage")
        print(traceback2.format_exc())


@tasks.loop(hours=1)
async def loop():
    try:
        plugin_updated = fetch_plugins()
        theme_updated = fetch_themes()
        push_updates(True, plugin_updated, theme_updated)
    except:
        print("[x] Error loop")
        print(traceback2.format_exc())


# 情報を抽出する
def parse_plugin(download_url):
    plugin = {}

    plugin_name = download_url.split("/")[-1].replace(".js", "")
    plugin["url"] = download_url
    headers = {"Cache-Control": "no-cache", "Pragma": "no-cache"}
    r = requests.get(download_url, headers=headers)

    if len(r.text) <= 20 or ("<h1>404</h1>" in r.text and "<!DOCTYPE html>" in r.text):  # invalid or 404
        return None

    if res := desc_pattern1.findall(r.text):  # descriptionに対応する変数名を取得
        res = re.findall(res[0] + variable_pattern, r.text)  # 変数名に対応する値を取得
        plugin["description"] = res[0]
        # バージョン解析 - 同様に
        if res := version_pattern2.findall(r.text):
            res = re.findall(res[0] + variable_pattern, r.text)
            plugin["version"] = res[0]
    elif res := desc_pattern2.findall(r.text):
        # まとめて取得
        plugin["version"] = res[0][0]
        plugin["description"] = res[0][1]
    elif res := desc_pattern3.findall(r.text):
        plugin["description"] = res[0]
    elif res := desc_pattern4.findall(r.text):
        plugin["description"] = res[0]

    if "version" not in plugin:
        if res := version_pattern.findall(r.text):  # ""でバージョンが書いてあるパターン(2,3で普通はとれる)
            plugin["version"] = res[0]

    return [plugin_name, plugin]


def parse_theme(download_url):
    headers = {'Accept': 'application/json', "Cache-Control": "no-cache", "Pragma": "no-cache"}
    r = requests.get(download_url, headers=headers)
    try:
        theme = {}
        res = r.json()
        theme["url"] = download_url
        if "description" in res:
            theme["description"] = res["description"]
        # if "authors" in res:
        #     theme["authors"] = res["authors"]
        if "version" in res:
            if version_pattern_raw.fullmatch(res["version"]):  # 適当な文字列を入れているふざけたやつが含まれるので除く！
                theme["version"] = res["version"]
        return [res["name"], theme]
    except:
        return None


# メッセージをループしてリストを取得+それぞれの情報を取得して上書き
async def dump_plugins():
    plugins = {}
    plugin_channel = bot.get_channel(plugin_channel_id)
    messages = []
    async for message in plugin_channel.history(limit=None):
        messages.append(message)

    for message in tqdm(messages):
        if result := list(set(js_pattern.findall(message.content))):
            download_url = result[0]
            if download_url in blacklisted:
                continue
            if res := parse_plugin(download_url):
                plugins[res[0]] = res[1]

    # 独自追加
    for url in custom_plugins:
        if res := parse_plugin(url):
            plugins[res[0]] = res[1]

    with open("plugins.json", "w", encoding="utf-8") as f:
        json.dump(plugins, f, ensure_ascii=False)
    with open("plugins_formatted.json", "w", encoding="utf-8") as f:
        json.dump(plugins, f, ensure_ascii=False, indent=2)


async def dump_themes():
    themes = {}
    theme_channel = bot.get_channel(theme_channel_id)
    messages = []
    async for message in theme_channel.history(limit=None):
        messages.append(message)

    for message in tqdm(messages):
        result = list(set(json_pattern.findall(message.content)))
        if result:
            download_url = result[0]
            if res := parse_theme(download_url):
                themes[res[0]] = res[1]

    with open("themes.json", "w", encoding="utf-8") as f:
        json.dump(themes, f, ensure_ascii=False)
    with open("themes_formatted.json", "w", encoding="utf-8") as f:
        json.dump(themes, f, ensure_ascii=False, indent=2)


# それぞれの情報を取得して更新
def fetch_plugins():
    with open("plugins.json", "r", encoding="utf-8") as f:
        plugins = json.load(f)
    plugins_old = copy.deepcopy(plugins)
    keys = plugins.keys()
    for name in tqdm(keys):
        download_url = plugins[name]["url"]
        if res := parse_plugin(download_url):  # 利用できなくなっている場合はとりあえず上書きせず飛ばす
            name_, plugin = res
            if name != name_:  # 名前が変更された場合
                plugins.pop(name)  # 前のを削除
                plugins[name_] = plugin  # 追加
            else:
                # descやverは削除されていても前はあった場合は昔のを残しておく
                if ("description" not in plugin) and ("description" in plugins[name_]):
                    plugin["description"] = plugins[name_]["description"]
                if ("version" not in plugin) and ("version" in plugins[name_]):
                    plugin["version"] = plugins[name_]["version"]
                plugins[name_] = plugin

    if plugins_old != plugins:
        with open("plugins.json", "w", encoding="utf-8") as f:
            json.dump(plugins, f, ensure_ascii=False)
        with open("plugins_formatted.json", "w", encoding="utf-8") as f:
            json.dump(plugins, f, ensure_ascii=False, indent=2)
        return True
    else:
        return False


def fetch_themes():
    with open("themes.json", "r", encoding="utf-8") as f:
        themes = json.load(f)
    themes_old = copy.deepcopy(themes)
    keys = themes.keys()
    for name in tqdm(keys):
        download_url = themes[name]["url"]
        if res := parse_theme(download_url):
            name_, theme = res
            if name != name_:  # 名前が変更された場合
                themes.pop(name)  # 前のを削除
                themes[name_] = theme  # 追加
            else:
                # descやverは削除されていても前はあった場合は昔のを残しておく
                if ("description" not in theme) and ("description" in themes[name_]):
                    theme["description"] = themes[name_]["description"]
                if ("version" not in theme) and ("version" in themes[name_]):
                    theme["version"] = themes[name_]["version"]
                themes[name_] = theme

    if themes_old != themes:
        with open("themes.json", "w", encoding="utf-8") as f:
            json.dump(themes, f, ensure_ascii=False)
        with open("themes_formatted.json", "w", encoding="utf-8") as f:
            json.dump(themes, f, ensure_ascii=False, indent=2)
        return True
    else:
        return False


async def dump_all():
    dump_plugin = True
    dump_theme = True

    if dump_plugin:
        print("[*] Dumping plugins...")
        await dump_plugins()

    if dump_theme:
        print("[*] Dumping themes...")
        await dump_themes()

    print("[o] Successfully dumped!")


def fetch_all():
    fetch_plugin = True
    fetch_theme = True

    if fetch_plugin:
        print("[*] Fetching plugins...")
        fetch_plugins()

    if fetch_theme:
        print("[*] Fetching themes...")
        fetch_themes()

    print("[o] Successfully fetched!")


bot.run(os.getenv("TOKEN"), bot=False)
