import requests
import re
version_pattern = re.compile(r'version:\s*["\']([0-9.]+)["\']')
r = requests.get("https://raw.githubusercontent.com/6days9weeks/EnableStaging/mistress/dist/EnableStaging.js")
res = version_pattern.findall(r.text)
print(res)