import copy
from datetime import timedelta

import discord
import requests
import traceback2
from discord.ext import commands, tasks
from dotenv import load_dotenv
import os
import re
import time
from tqdm import tqdm
import json

# 環境変数読込
load_dotenv(verbose=True)
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

# Client作成
bot = commands.Bot("!", self_bot=True, intents=discord.Intents.default())

debug = False
dump_all = False

# データ
channel_ids = {
    "plugin": 961782195767365732,
    "theme": 961782176062509117
} if not debug else {
    "plugin": 1066087899449274479,
    "theme": 1066087924904509523
}

# 正規表現
js_pattern = re.compile(r"https?://[\w!?/+\-_~;.,*&@#$%()'[\]]+\.js")
json_pattern = re.compile(r"https?://[\w!?/+\-_~;.,*&@#$%()'[\]]+\.json")
js_line_pattern = re.compile(r"(\n.*?Install.*?https?://[\w!?/+\-_~;.,*&@#$%()'[\]]+\.js>?.*?)\n")  # リンクを<>で囲んでる場合に注意
json_line_pattern = re.compile(r"(\n.*?Install.*?https?://[\w!?/+\-_~;.,*&@#$%()'[\]]+\.json>?.*?)\n")  # 前後の\n両方とるととりすぎなので先頭のみ含める
preview_pattern = re.compile(r"((__)?Preview(__)?\s*:(__)?)\s*")
image_pattern = re.compile(r"(https?://[\w!?/+\-_~;.,*&@#$%()'[\]]+\.(png|jpg))")  # ()で囲むとそこのみが返されてしまうので全体も囲って戻り値のタプル[0]で取得する
video_pattern = re.compile(r"(https?://[\w!?/+\-_~;.,*&@#$%()'[\]]+\.(mp4|mov))")
wrapped_url_pattern = re.compile(r"<(https?://[\w!?/+\-_~;.,*&@#$%()'[\]]+)>")
emoji_pattern = re.compile(r"<a?:.+?:\d{18}>")
title_pattern = re.compile(r"^\*\*.*?\n\n")
title2_pattern = re.compile(r"^\*\*.*?\n")
command_pattern = re.compile(r"</(.+?):1>")
desc_pattern1 = re.compile(r"{name:[a-zA-Z_]+,.*?description:([a-zA-Z_]+)")  # <一般的なパターン> 1~2文字の略された変数で、その変数の指す値をとりに行く
desc_pattern2 = re.compile(r'version:"([0-9.]+)",.*?description:["\'](.*?)["\']')  # ""で文字列が直接入っているパターン(より絞れる)
desc_pattern3 = re.compile(r'{name:"[a-zA-Z_]+",.*?description:["\'](.*?)["\']')  # ""で文字列が直接入っているパターン2(versionがない場合もあるので/コマンドがひっかる場合もあるので注意)
desc_pattern4 = re.compile(r'description:\s*["\'](.*?)["\']')  # minifyされていないコード
variable_pattern = rf'=["\'](.*?)["\'],'
version_pattern = re.compile(r'version:\s*["\']([0-9.]+)["\']')
version_pattern2 = re.compile(r"{name:[a-zA-Z_]+,.*?version:([a-zA-Z_]+)")
version_pattern_raw = re.compile(r'[0-9.]+')

# 独自設定
exclude_addons = {
    "plugin": [
        "https://plugins.panties.moe/plugins/EnableStaging.js",
        "https://raw.githubusercontent.com/6days9weeks/EnableStaging/mistress/dist/EnableStaging.js"
    ],
    "theme": []
}
include_addons = {
    "plugin": [
        "https://raw.githubusercontent.com/xenos1337/enmity-plugins/main/ReactDevTools/dist/ReactDevTools.js",
        "https://raw.githubusercontent.com/m4fn3/FixVoiceMessageCrash/master/dist/FixVoiceMessageCrash.js"
    ],
    "theme": []
}

# メッセージキャッシュ
cached = {}  # message_id: timestamp


# GitHubに更新を反映
def push_changes(addon_type, log="No Log"):
    t = str(time.time())

    with open(f"{addon_type}s_update.txt", "w") as f:
        f.write(t)

    os.system("git add .")
    os.system(f'git commit -m "{log}"')
    os.system("git push")


def pull_changes():
    if not debug:
        os.system("git pull")


@bot.event  # 起動時
async def on_ready():
    print(f"[*] Logged in as {bot.user}")
    pull_changes()
    for addon_type in ["plugin", "theme"]:
        if dump_all:
            await dump_all(addon_type)
        async for message in bot.get_channel(channel_ids[addon_type]).history(limit=None):
            cached[message.id] = message.created_at
    if not debug:
        loop.start()


@bot.event  # 送信検知
async def on_message(message):
    # dumpの時は必ず変更があるので常に更新してpushする
    if message.channel.id == channel_ids["plugin"]:
        cached[message.id] = message.created_at  # 指定チャンネルでの送信はtimestampをキャッシュしておく
        if list(set(js_pattern.findall(message.content))):
            await add("plugin", message)
    elif message.channel.id == channel_ids["theme"]:
        cached[message.id] = message.created_at
        if list(set(json_pattern.findall(message.content))):
            await add("theme", message)


# @bot.event
# async def on_message_edit(message_old, message):  # キャッシュない場合利用不可(事前に全メッセージ読み込みしてもダメ)
#     if message_old.content != message.content:  # テキストの変更時のみ
#         if message.channel.id == channel_ids["plugin"]:
#             if list(set(js_pattern.findall(message.content))):
#                 await add("plugin", message, True)
#         elif message.channel.id == channel_ids["theme"]:
#             if list(set(json_pattern.findall(message.content))):
#                 await add("theme", message, True)

# メッセージ取得
async def get_message(channel_id, message_id):
    messages = [message async for message in bot.get_channel(channel_id).history(after=cached[message_id] - timedelta(seconds=1), before=cached[message_id] + timedelta(seconds=1))]
    return messages[0] if messages else None


@bot.event  # 編集検知
async def on_raw_message_edit(payload):
    if "content" in payload.data:  # embed更新などでも呼ばれるので
        if payload.channel_id == channel_ids["plugin"]:
            # message = await bot.get_channel(payload.channel_id).fetch_message(payload.message_id) # bot専用
            # fetch_messageはbot専用なのでtimestampで絞ってキャッシュ外のメッセージの取得に代用
            if message := await get_message(payload.channel_id, payload.message_id):
                if list(set(js_pattern.findall(message.content))):
                    await add("plugin", message, True)
        elif payload.channel_id == channel_ids["theme"]:
            if message := await get_message(payload.channel_id, payload.message_id):
                if list(set(json_pattern.findall(message.content))):
                    await add("theme", message, True)


# 1時間ごとに更新を確認する
@tasks.loop(hours=1)
async def loop():
    pull_changes()
    for addon_type in ["plugin", "theme"]:
        check_update(addon_type)


# URLからダウンロードして情報を解析する
def fetch(addon_type, download_url):
    if addon_type == "plugin":
        plugin = {}

        plugin_name = download_url.split("/")[-1].replace(".js", "")
        plugin["url"] = download_url
        headers = {"Cache-Control": "no-cache", "Pragma": "no-cache"}
        try:
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
        except:
            return None

    elif addon_type == "theme":
        headers = {'Accept': 'application/json', "Cache-Control": "no-cache", "Pragma": "no-cache"}
        try:
            r = requests.get(download_url, headers=headers)
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

    return []


# messageから説明,画像,動画データを抽出
def extract_preview(message, addon_type):
    download_url_pattern = js_line_pattern if addon_type == "plugin" else json_line_pattern

    description = message.content
    exclude = list(set(download_url_pattern.findall(message.content)))
    for t in exclude:  # Install:を削除
        description = description.replace(t, "")
    # 説明文から画像/動画のURLを抽出
    image_urls = [i[0] for i in image_pattern.findall(description)]
    video_urls = [i[0] for i in video_pattern.findall(description)]
    # embeds = [e.to_dict() for e in message.embeds]  # 埋め込みで表示される画像/動画
    # embed_images = [e["url"] for e in embeds if e["type"] == "image"]
    # embed_videos = [e["url"] for e in embeds if e["type"] == "video"]
    for url in image_urls + video_urls:  # 画像/動画のURLを削除
        description = description.replace(url, "")
    description = description.replace("\n>>", "\n").replace("\n>", "\n")  # > で始まるやつを消す
    for url in wrapped_url_pattern.findall(description):  # url が <> で囲まれている場合外す
        description = description.replace(f"<{url}>", url)
    for emoji in emoji_pattern.findall(description):  # <> 型の絵文字を削除
        description = description.replace(emoji, "")
    if (title_pattern.search(description)) is None and (res := title2_pattern.search(description)):  # 一行目の**addon名**のあとに改行がない場合は\nを追加してあげる
        description = description.replace(f"{res.group()}", f"{res.group()}\n")
    description = description.replace("**", "")  # **を削除
    for command in command_pattern.findall(description):  # /command を削除
        description = description.replace(f"</{command}:1>", f"`/{command}`")
    for p in preview_pattern.findall(description):  # Preview:を削除
        description = description.replace(p[0], "")
    description = description.strip(" ").strip("\n")  # 先頭末尾の不要な\nを削除 (\n )
    meta = {
        "description": description,
        "images": [a.url for a in message.attachments if a.url.endswith((".png", ".jpg"))] + image_urls,
        "videos": [a.url for a in message.attachments if a.url.endswith((".mov", ".mp4"))] + video_urls,
    }
    return meta


# messageから新規追加
async def add(addon_type, message, is_edit=False):
    try:
        download_url_pattern = js_pattern if addon_type == "plugin" else json_pattern
        result = list(set(download_url_pattern.findall(message.content)))
        download_url = result[0]
        if download_url in exclude_addons["plugin"]:
            return
        with open(f"{addon_type}s.json", "r", encoding="utf-8") as f:
            data = json.load(f)
        if res := fetch(addon_type, download_url):
            data[res[0]] = res[1]
            meta = extract_preview(message, addon_type)
            with open(f"{addon_type}s/{res[0]}.json", "w", encoding="utf-8") as f:
                json.dump(meta, f, ensure_ascii=False, indent=2)

            with open(f"{addon_type}s.json", "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
            with open(f"{addon_type}s_formatted.json", "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            push_changes(addon_type, f"[{'Edit' if is_edit else 'Add'}] {res[0]} ({addon_type})")
    except:
        print(traceback2.format_exc())


# 全てをダンプする
async def dump_all(addon_type):
    try:
        data = {}
        channel = bot.get_channel(channel_ids[addon_type])
        messages = []
        async for message in channel.history(limit=None):
            messages.append(message)

        for message in tqdm(messages):
            link_pattern = js_pattern if addon_type == "plugin" else json_pattern
            if result := list(set(link_pattern.findall(message.content))):
                download_url = result[0]
                if download_url in exclude_addons[addon_type]:
                    continue
                if res := fetch(addon_type, download_url):
                    data[res[0]] = res[1]
                    meta = extract_preview(message, addon_type)
                    with open(f"{addon_type}s/{res[0]}.json", "w", encoding="utf-8") as f:
                        json.dump(meta, f, ensure_ascii=False, indent=2)

        # 独自追加
        for url in include_addons[addon_type]:
            if res := fetch(addon_type, url):
                data[res[0]] = res[1]

        with open(f"{addon_type}s.json", "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        with open(f"{addon_type}s_formatted.json", "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        push_changes(addon_type, f"[Dump] {addon_type}")
    except:
        print(traceback2.format_exc(()))


# 既存のアドオンの更新を確認して情報を更新する
def check_update(addon_type):
    with open(f"{addon_type}s.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    data_old = copy.deepcopy(data)  # コピー後のデータも変わってしまうのを防ぐ
    names = data_old.keys()
    updated = []
    for name in tqdm(names):
        download_url = data[name]["url"]
        if res := fetch(addon_type, download_url):
            name_, meta = res
            # descやverは削除されていても前はあった場合は昔のを残しておく
            if ("description" not in meta) and ("description" in data[name_]):
                meta["description"] = data[name_]["description"]
            if ("version" not in meta) and ("version" in data[name_]):
                meta["version"] = data[name_]["version"]
            data[name_] = meta
            if data_old[name] != meta:
                updated.append(name)
    if data_old != data:
        with open(f"{addon_type}s.json", "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        with open(f"{addon_type}s_formatted.json", "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        push_changes(addon_type, f"[Update] {','.join(updated)} ({addon_type})")
        return True
    else:
        return False


bot.run(os.getenv("TOKEN"), bot=False)
