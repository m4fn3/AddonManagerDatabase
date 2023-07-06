# AddonManagerDatabase
Addon database for [AddonManager](https://github.com/m4fn3/AddonManager)

## How it works
`updater_v2.py` is running on my server to check updates of all addons every hour automatically.

The updater also detect new posts and message editing in #plugins and #themes channel of official Enmity server to keep database updated.   

Basic information of addons are stored in plugins(themes).json. Readable version can be found in plugins(themes)_formatted.json

The detailed description of addons (fetched from the release post in official Enmity server) can be found in plugins(themes)/[AddonName].json 

## Host
1. Creat `.env` with following keys
   - TOKEN : Token of Discord 
   - GH_TOKEN : Api key of GitHub
   - WH_PLUGIN : Webhook url to notice updates of plugins
   - WH_THEME : Webhook url to notice updates of themes
2. Create a fork of this repo (Write permission to the repo is required to make it work) 
3. `python -m pip install -r requirements.txt`
4. `python updater_v2.py`

## Notes
### Specification
- It will retain previously fetched info if it fails to get the necessary information
- If dump_all is executed, all data will be overwritten by the fetched information at that time
### Known Issues
- The file name of the addon and the actual name is supposed to be the same name and it may not work correctly if not.

### Commits
Commits start with following string are automatically made by the updater.
- [New] - Added a newly released addon
- [Edit] - Detailed addon description is edited (the posted message in either #plugins or #themes got updated)
- [Update] - Addon got updated to new version
- [Dump] - Dumped all addons with the dump_all function