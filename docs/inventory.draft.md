# Inventory draft (auto-generated)

Scanned 2026-09-06 00:01 from this Mac. Copy rows you keep into inventory.md and fill in room and decision.

| Host | Advertised as | Looks like | Protocol | Control path |
|---|---|---|---|---|
| 1457768-01-G--B7S21065J05303.local. | 1457768-01-G--B7S21065J05303 | Tesla Powerwall / Gateway | Wi-Fi | local TEDAPI + cloud |
| 2N001H984176.local. | aca9c0d8-1f8d-5524-ae2c-19ca40139bf1 | Spotify Connect | Wi-Fi | local |
| 3425BEC06C79.local. | 1965BD605A768BB6-025CBF5DF6127EF1; 7611642E9F04419B | Matter device (operational) | Matter over Wi-Fi/Thread | local |
| 52850397-d731-72eb-7501-b6e15967bd92.local. | 52850397-d731-72eb-7501-b6e15967bd92; Google-Home-Mini-52850397d73172eb7501b6e15 | Google Cast / Nest | Wi-Fi | local for cast, cloud for Nest devices |
| 573d1b86-f13d-ab6a-869a-2a22f827a460.local. | 573d1b86-f13d-ab6a-869a-2a22f827a460; 8D9AB57E6EC24AAC20CA9F712C5CE4C7; Google-H | Google Cast / Nest | Wi-Fi | local for cast, cloud for Nest devices |
| 61bc3a7b-f4e4-e173-b526-641d37effa12.local. | Smart-TV-61bc3a7bf4e4e173b526641d37effa12 | Google Cast / Nest | Wi-Fi | local for cast, cloud for Nest devices |
| 67686363-9e43-0cdf-f13d-2963f3b88ca9.local. | 67686363-9e43-0cdf-f13d-2963f3b88ca9; Google-Home-Mini-676863639e430cdff13d2963f | Google Cast / Nest | Wi-Fi | local for cast, cloud for Nest devices |
| Android.local. | SpotifyConnect | Spotify Connect | Wi-Fi | local |
| BRWE86F38349B27.local. | Brother MFC-L3770CDW series | Printer | Wi-Fi | local |
| Bedroom TV | Bedroom TV | Android TV / Google TV | Wi-Fi | local remote protocol |
| obi1.local. | obi1 [2c:cf:67:39:0b:e3] | Linux host | Wi-Fi/Ethernet | ssh |
| temi-mbp.local. | 9E11BB95-D6CF-4CF0-BAAA-6D68184030E0; CA274C23904B@Temitope’s MacBook Pro; Temit | AirPlay | Wi-Fi | local |
| tsc-mac-mini.local. | EE7F17C9AAAD@tsc-mac-mini; tsc-mac-mini | AirPlay | Wi-Fi | local |

## SSDP / UPnP responders

| IP | Server | Location |
|---|---|---|
| 192.168.86.62 | ac:fdm:ssdp | http://192.168.86.62:18910/info?cn=47A5-F3C1-884D-1121&ctrlType=lan&deviceName=Anycubic+Kobra+3+Max&env=prod&ip=192.168.86.62&modelId=20026&modelName=Anycubic+Kobra+3+Max&token=REDACTED&zone=global |
| 192.168.86.1 |  | http://192.168.86.1:5000/rootDesc.xml |
| 192.168.86.64 |  | http://192.168.86.64:8060/ |
| 192.168.86.64 |  | http://192.168.86.64:8060/dial/dd.xml |
| 192.168.86.65 | Linux/4.14.76+, UPnP/1.0, Portable SDK for UPnP devices |  |
| 192.168.86.65 | Linux/4.14.76+, UPnP/1.0, Chromecast/1.6.18 |  |

## Not discoverable this way (add by hand)

- Z-Wave devices: only visible once a Z-Wave stick is running. List from the old hub's app.
- Zigbee devices on the Hue bridge: list via the bridge API once paired (tools/hue_inventory.py, later).
- Ring, Brilliant, Wink, Google Nest cloud devices: list from their apps.
