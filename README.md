# AddonManagerDatabase
Addon database for [AddonManager](https://github.com/m4fn3/AddonManager)

updater_v2.py is running on my server to check updates of all addons every hour automatically.

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
### To-Do
- Manually added addons won't get included in check_updates and only in dump_all as of now (editing plugins.json will reflect it)
