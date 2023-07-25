import copy
import datetime
from datetime import timedelta
from typing import List, Union
import selfcord
import requests
import traceback2
from selfcord.ext import commands, tasks
from dotenv import load_dotenv
import os
import re
import time
from tqdm import tqdm
import json
import demjson
from discord_webhook import DiscordWebhook

# 環境変数読込
load_dotenv(verbose=True)
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

# Client作成
bot = commands.Bot("!", self_bot=True)

# 設定
debug = False
do_dump_all = False
get_last_updated = True

# データ
channel_ids = {
    "plugin": 961782195767365732,
    "theme": 961782176062509117
}
# } if not debug else {
#     "plugin": 1066087899449274479,
#     "theme": 1066087924904509523
# }

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
desc_pattern1 = re.compile(r"{name:[a-zA-Z0-9$_]+,.*?description:([a-zA-Z0-9$_]+)")  # <一般的なパターン> 1~2文字の略された変数で、その変数の指す値をとりに行く
desc_pattern2 = re.compile(r'{name:"[a-zA-Z_]+",.*?description:(?:"(.*?)"|\'(.*?)\')')  # <特殊なパターン> 直接文字列が指定されている
desc_pattern3 = re.compile(r'description:\s*(?:"(.*?)"|\'(.*?)\')')  # <超特殊なパターン> minifyされていない場合
variable_pattern = r'=["\'](.*?)["\'],'  # TODO: 最後の,は必要か不明
variable_pattern_list = r'=(\[.*?\]),'
version_pattern1 = re.compile(r"{name:[a-zA-Z0-9$_]+,.*?version:([a-zA-Z0-9$_]+)")
version_pattern2 = re.compile(r'{name:"[a-zA-Z_]+",.*?version:"([0-9.]+)"')
version_pattern_simple = re.compile(r'version:\s*["\']([0-9.]+)["\']')
version_pattern_raw = re.compile(r'[0-9.]+')
color_pattern1 = re.compile(r"{name:[a-zA-Z0-9$_]+,.*?color:([a-zA-Z0-9$_]+)")
color_pattern2 = re.compile(r'{name:"[a-zA-Z_]+",.*?color:"([0-9a-fA-F#]+)"')
author_pattern1 = re.compile(r"{name:[a-zA-Z0-9$_]+,.*?authors:([a-zA-Z0-9$_]+)")
author_pattern2 = re.compile(r'{name:"[a-zA-Z_]+",.*?authors:(\[.*?\])')
raw_gh_pattern = re.compile(r'https?://raw\.githubusercontent\.com/(?P<user>[\w_\-]+)/(?P<repo>[\w_\-]+)/(?P<branch>[\w_\-]+)/(?P<path>.*)')

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
        "https://raw.githubusercontent.com/m4fn3/FixVoiceMessageCrash/master/dist/FixVoiceMessageCrash.js",
        "https://raw.githubusercontent.com/m4fn3/TrackEdit/master/dist/TrackEdit.js",
        "https://raw.githubusercontent.com/acquitelol/enmity-utility-patches/main/dist/UtilityPatches.js",
        "https://raw.githubusercontent.com/acquitelol/vendetta-compat/main/dist/VendettaCompat.js",
        "https://raw.githubusercontent.com/m4fn3/FixConnecting/master/dist/FixConnecting.js"
    ],
    "theme": []
}

# メッセージキャッシュ
cached = {}  # message_id: timestamp


# GitHubに更新を反映
async def push_changes(addon_type: str, log: str = "No Log"):
    if not debug:
        t = str(time.time())

        with open(f"{addon_type}s_update.txt", "w") as f:
            f.write(t)

        os.system("git add .")
        os.system(f'git commit -m "{log}"')
        os.system("git push")

        wh_url = ""
        if addon_type == "plugin":
            wh_url = os.environ["WH_PLUGIN"]
        elif addon_type == "theme":
            wh_url = os.environ["WH_THEME"]
        webhook = DiscordWebhook(url=wh_url, content='update!')
        webhook.execute()


def pull_changes():
    if not debug:
        os.system("git pull")


@bot.event  # 起動時
async def on_ready() -> None:
    """
    when discord.py is ready
    """
    print(f"[*] Logged in as {bot.user}")
    pull_changes()
    for addon_type in ["plugin", "theme"]:
        if do_dump_all:
            await dump_all(addon_type)
        async for message in bot.get_channel(channel_ids[addon_type]).history(limit=None):
            cached[message.id] = message.created_at
    if not debug and not loop.is_running():
        loop.start()


@bot.event  # 送信検知
async def on_message(message: selfcord.Message) -> None:
    """
    detect new messages in the channel of either plugins or themes and add them to the database
    :param message: a message we received
    :return:
    """
    # dumpの時は必ず変更があるので常に更新してpushする
    if message.channel.id == channel_ids["plugin"]:
        cached[message.id] = message.created_at  # 指定チャンネルでの送信はtimestampをキャッシュしておく
        if list(set(js_pattern.findall(message.content))):
            await upsert("plugin", message)
    elif message.channel.id == channel_ids["theme"]:
        cached[message.id] = message.created_at
        if list(set(json_pattern.findall(message.content))):
            await upsert("theme", message)


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
async def get_message(channel_id: int, message_id: int) -> Union[selfcord.Message, None]:
    """
    get the specific message with channel id & message id
    :param channel_id:
    :param message_id:
    :return: the message if it exists
    """
    messages = [message async for message in bot.get_channel(channel_id).history(after=cached[message_id] - timedelta(seconds=1), before=cached[message_id] + timedelta(seconds=1))]
    return messages[0] if messages else None


@bot.event  # 編集検知
async def on_raw_message_edit(payload: selfcord.RawMessageUpdateEvent) -> None:
    """
    detect edits of messages in either plugins or themes channel to update detailed plugin descriptions
    :param payload:
    """
    if "content" in payload.data:  # embed更新などでも呼ばれるので
        if payload.channel_id == channel_ids["plugin"]:
            # message = await bot.get_channel(payload.channel_id).fetch_message(payload.message_id) # bot専用
            # fetch_messageはbot専用なのでtimestampで絞ってキャッシュ外のメッセージの取得に代用
            if message := await get_message(payload.channel_id, payload.message_id):
                if list(set(js_pattern.findall(message.content))):
                    await upsert("plugin", message, True)
        elif payload.channel_id == channel_ids["theme"]:
            if message := await get_message(payload.channel_id, payload.message_id):
                if list(set(json_pattern.findall(message.content))):
                    await upsert("theme", message, True)


# 1時間ごとに更新を確認する
@tasks.loop(hours=1)
async def loop() -> None:
    """
    Check updates of all addons every hour
    """
    # pull remote changes before we make changes
    pull_changes()
    # check updates respectively
    for addon_type in ["plugin", "theme"]:
        await check_update(addon_type)


# JavaScript形式の連想配列をプロパティ名を囲ってjson形式に変換
def format_author_array(raw: str) -> Union[list, None]:
    """
    Convert js-style dict to valid JSON format
    :param raw:
    :return:
    """
    try:
        # load js-style dict which keys doesn't have quotes
        data = demjson.decode(raw)
        # extract only name and id field (some has unique keys here)
        data = [{"name": u["name"], "id": u["id"]} for u in data]
    except:
        print("-- format author error")
        print(traceback2.format_exc())
        return None
    else:
        return data


# $が変数名に使われていると困るのでエスケープする
def escape_regex(t: str) -> str:
    """
    escape specific characters to be used in regex
    :param t: regex
    :return: escaped regex
    """
    return t.replace("$", r"\$")


def get_addon_name_from_url(addon_type: str, url: str) -> str:
    if addon_type == "plugin":
        return url.split("/")[-1].replace(".js", "")
    elif addon_type == "theme":
        return url.split("/")[-1].replace(".json", "")


# URLからダウンロードして情報を解析する
def fetch(addon_type, download_url, old_meta=None, message_id=None) -> Union[List[Union[str, dict]], None]:
    """
    fetch an raw addon code and parse the necessary data
    :param addon_type: plugin or theme
    :param download_url: install url of an addon
    :param old_meta: (optional) old metadata of an addon
    :param message_id: message id of the original post
    :return: [addon_name, addon_data] (return None if it fails to download/parse the code)
    """
    if addon_type == "plugin":
        plugin = {}
        # download the plugin
        plugin_name = download_url.split("/")[-1].replace(".js", "")
        plugin["url"] = download_url
        headers = {"Cache-Control": "no-cache", "Pragma": "no-cache"}
        try:
            r = requests.get(download_url, headers=headers)

            # ignore plugins that return invalid code
            if len(r.text) <= 20 or ("<h1>404</h1>" in r.text and "<!DOCTYPE html>" in r.text):  # invalid or 404
                if old_meta:
                    return [plugin_name, old_meta]
                return None

            # get last updated time
            if get_last_updated:
                if "Last-Modified" in r.headers:  # 確認済み: github release link / selfcord attachment link
                    plugin["last_update"] = int(time.mktime(datetime.datetime.strptime(r.headers["Last-Modified"], "%a, %d %b %Y %H:%M:%S GMT").timetuple()))
                elif r.url.startswith("https://raw.githubusercontent.com/"):
                    try:
                        match = raw_gh_pattern.fullmatch(r.url)
                        resp = requests.get(
                            f"https://api.github.com/repos/{match.group('user')}/{match.group('repo')}/commits?path={match.group('path')}&page=1&per_page=1",
                            headers={'Authorization': 'token ' + os.environ["GH_TOKEN"]}
                        )
                        data = resp.json()
                        timestamp = data[0]["commit"]["committer"]["date"]
                    except:
                        print("--- regex error ---")
                        print(data)
                        print(traceback2.format_exc())
                    else:
                        plugin["last_update"] = int(time.mktime(datetime.datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%S%z").timetuple()))
                        # print(plugin["last_update"])

            # get description, version, author and color using regular expressions
            if res := desc_pattern1.findall(r.text):  # descriptionに対応する変数名を取得
                res = re.findall(escape_regex(res[0]) + variable_pattern, r.text)  # 変数名に対応する値を取得
                if res:
                    plugin["description"] = res[0]
                    if res := version_pattern1.findall(r.text):  # versionも同様に
                        res = re.findall(escape_regex(res[0]) + variable_pattern, r.text)
                        if res:
                            plugin["version"] = res[0]
                    if res := color_pattern1.findall(r.text):  # colorも同様に
                        res = re.findall(escape_regex(res[0]) + variable_pattern, r.text)
                        if res:
                            plugin["color"] = res[0]
                    if res := author_pattern1.findall(r.text):  # authorも同様に
                        res = re.findall(escape_regex(res[0]) + variable_pattern_list, r.text)
                        if res and (author := format_author_array(res[0])):
                            plugin["author"] = author
            elif res := desc_pattern2.findall(r.text):  # descriptionを直接取得
                plugin["description"] = res[0][0]  # 何故か(desc,"")の形になるので[0]でとる <- キャプチャ無しグルーピング(?: )が機能してない?
                if res := version_pattern2.findall(r.text):  # versionも同様に
                    plugin["version"] = res[0]
                if res := color_pattern2.findall(r.text):  # colorも同様に
                    plugin["color"] = res[0]
                if res := author_pattern2.findall(r.text):  # authorも同様に
                    if author := format_author_array(res[0]):
                        plugin["author"] = author
            elif res := desc_pattern3.findall(r.text):  # descriptionを直接取得
                plugin["description"] = res[0][0]

            if "version" not in plugin:  # rare case
                if res := version_pattern_simple.findall(r.text):  # ""でバージョンが書いてあるパターン(2,3で普通はとれる)
                    plugin["version"] = res[0]

            # save the message id of the original post
            if message_id:
                plugin["message_id"] = message_id

            # restore missing fields with old data if any
            if old_meta:
                keys = ["description", "version", "color", "author", "last_update", "message_id"]
                for k in keys:
                    if (k not in plugin) and (k in old_meta):
                        plugin[k] = old_meta[k]

            return [plugin_name, plugin]
        except:
            print("------ Error in parsing a plugin -----------")
            print(download_url)
            print(traceback2.format_exc())
            if old_meta:
                return [plugin_name, old_meta]
            return None

    elif addon_type == "theme":
        # download the theme
        headers = {'Accept': 'application/json', "Cache-Control": "no-cache", "Pragma": "no-cache"}
        try:
            r = requests.get(download_url, headers=headers)
            theme = {}
            res = r.json()
            theme["url"] = download_url
            # get description, version and author using regular expressions
            if "description" in res:
                theme["description"] = res["description"]
            if "authors" in res:
                theme["author"] = res["authors"]
            if "color" in res:
                theme["color"] = res["color"]
            if "version" in res:
                if version_pattern_raw.fullmatch(res["version"]):  # 適当な文字列を入れているふざけたやつが含まれるので除く！
                    theme["version"] = res["version"]

            # save the message id of the original post
            if message_id:
                theme["message_id"] = message_id

            # restore missing fields with old data if any
            if old_meta:
                keys = ["description", "version", "color", "author", "message_id"]
                for k in keys:
                    if (k not in theme) and (k in old_meta):
                        theme[k] = old_meta[k]

            return [res["name"], theme]
        except:
            if old_meta:
                return [get_addon_name_from_url(addon_type, download_url), old_meta]
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
async def upsert(addon_type: str, message: selfcord.Message, is_edit: bool = False) -> None:
    """
    add or update the plugin with a message
    :param addon_type: either plugin or theme
    :param message: a message that includes addon information
    :param is_edit:
    """
    # is_editがFalseの場合は新規追加 (on_messageより)
    # is_editがTrueの場合は更新 (on_raw_message_editより)
    try:
        download_url_pattern = js_pattern if addon_type == "plugin" else json_pattern
        result = list(set(download_url_pattern.findall(message.content)))
        download_url = result[0]
        if download_url in exclude_addons["plugin"]:  # 除外リストにある場合は除く
            return
        with open(f"{addon_type}s.json", "r", encoding="utf-8") as f:
            data = json.load(f)
        # 新規追加でない場合は昔のデータを復元用に取得して渡す
        addon_name = get_addon_name_from_url(addon_type, download_url)
        params = {}
        if addon_name in data:
            params["old_meta"] = data[addon_name]
        if res := fetch(addon_type, download_url, message_id=message.id, **params):
            data[res[0]] = res[1]
            meta = extract_preview(message, addon_type)
            # 詳細説明を書き込む
            with open(f"{addon_type}s/{res[0]}.json", "w", encoding="utf-8") as f:
                json.dump(meta, f, ensure_ascii=False, indent=2)
            # 基本情報を書き込む
            with open(f"{addon_type}s.json", "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
            with open(f"{addon_type}s_formatted.json", "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            await push_changes(addon_type, f"[{'Edited' if is_edit else 'New'}] {res[0]} ({addon_type})")
    except:
        print(traceback2.format_exc())


# 全てをダンプする
async def dump_all(addon_type: str):
    """
    dump all addons and force it to override existing data
    :param addon_type:
    :return:
    """
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
                # dump_allは既存のデータを上書きして全取得しなおすことに意味があるのでold_metaは不要
                if res := fetch(addon_type, download_url, message_id=message.id):
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
        await push_changes(addon_type, f"[Dump] {addon_type}")
    except:
        print(traceback2.format_exc(()))


# 既存のアドオンの更新を確認して情報を更新する
async def check_update(addon_type: str):
    """
    check updates of all addons of the specific addon type
    :param addon_type: either plugin or theme
    :return: if there were updates
    """
    with open(f"{addon_type}s.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    data_old = copy.deepcopy(data)  # コピー後のデータも変わってしまうのを防ぐ
    names = data_old.keys()
    updated = []
    for name in tqdm(names):
        download_url = data[name]["url"]
        if res := fetch(addon_type, download_url, data[name]):
            name_, meta = res
            data[name_] = meta
            if data_old[name] != meta:  # 何らかの変更があった場合は更新リストに追加
                updated.append(name)

    # 独自追加に新規のものがないか確認
    for url in include_addons[addon_type]:
        name = get_addon_name_from_url(addon_type, url)
        if name not in names:
            if res := fetch(addon_type, url):
                data[res[0]] = res[1]
                updated.append(name)

    if data_old != data:
        with open(f"{addon_type}s.json", "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        with open(f"{addon_type}s_formatted.json", "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        await push_changes(addon_type, f"[Update] {','.join(updated)} ({addon_type})")
        return True
    else:
        return False


bot.run(os.getenv("TOKEN"))
