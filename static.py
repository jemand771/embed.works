import re

EXTRACTOR_COLOR = dict(
    Instagram="#CE0071",
    Reddit="#FF5700",
    TikTok="#FF0050",
    TwitchClips="#6441A5",
    Twitter="#1DA1F2",
    YouTube="#FF0000",
)

# user agent regex blatantly stolen from https://github.com/FixTweet/FixTweet
# https://github.com/FixTweet/FixTweet/blob/bc7e680a0b41fd762c1ba9028090a007ce97a41e/src/constants.ts#L17-L18
BOT_UA_REGEX = re.compile(
    r"bot|facebook|embed|got|firefox/92|firefox/38|curl|wget|go-http|yahoo|generator|whatsapp|preview|link|proxy"
    "|vkshare|images|analyzer|index|crawl|spider|python|cfnetwork|node"
)
