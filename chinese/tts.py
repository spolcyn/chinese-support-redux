# Copyright © 2012 Roland Sieker <ospalh@gmail.com>
# Copyright © 2012 Thomas TEMPÉ <thomas.tempe@alysse.org>
# Copyright © 2017 Pu Anlai <https://github.com/InspectorMustache>
# Copyright © 2019 Oliver Rice <orice@apple.com>
# Copyright © 2017-2021 Joseph Lorimer <joseph@lorimer.me>
# Inspiration: Tymon Warecki
# License: GNU AGPL, version 3 or later; http://www.gnu.org/copyleft/agpl.html

from requests.models import HTTPError
from .aws import AWS4Signer
from .main import config

from os.path import basename, exists, join
from re import sub
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError

import requests
from aqt import mw
from gtts import gTTS
from gtts.tts import gTTSError

requests.packages.urllib3.disable_warnings()


class AudioDownloader:
    def __init__(self, text, source='google|zh-CN'):
        self.text = text
        self.service, self.lang = source.split('|')
        self.path = self.get_path()
        self.func = {
            'google': self.get_google,
            'baidu': self.get_baidu,
            'aws': self.get_aws,
            'azure': self.get_azure,
        }.get(self.service)

    def get_path(self):
        filename = '{}_{}_{}.mp3'.format(
            self.sanitize(self.text), self.service, self.lang
        )
        return join(mw.col.media.dir(), filename)

    def sanitize(self, s):
        return sub(r'[/:*?"<>|]', '', s)

    def download(self):
        if exists(self.path):
            return basename(self.path)

        if not self.func:
            raise NotImplementedError(self.service)

        self.func()

        return basename(self.path)

    def get_azure(self):
        try:
            azure_api_key = config["tts"]["azure"]["api_key"] # type: ignore
            azure_region = config["tts"]["azure"]["region"] # type: ignore
        except KeyError as e:
            raise RuntimeError(f"Failed to get Azure API key from config") from e

        data = ('<speak xmlns="http://www.w3.org/2001/10/synthesis" '
                        'xmlns:mstts="http://www.w3.org/2001/mstts" '
                        'xmlns:emo="http://www.w3.org/2009/10/emotionml" version="1.0" '
                        'xml:lang="zh-CN"><voice name="zh-CN-XiaochenNeural"><prosody '
                        f'rate="1%" pitch="0%">{self.text}</prosody></voice></speak>').encode("UTF-8")
        base_url = f"https://{azure_region}.tts.speech.microsoft.com/cognitiveservices/v1"
        request = Request(base_url, data=data)

        request.add_header("Ocp-Apim-Subscription-Key", azure_api_key)
        request.add_header("Content-Type", "application/ssml+xml")
        request.add_header("X-Microsoft-OutputFormat", "audio-16khz-128kbitrate-mono-mp3")
        request.add_header('User-Agent', 'curl')

        try:
            response = urlopen(request, timeout=5)
        except HTTPError as exc:
            raise RuntimeError(f"HTTPError {exc.code}: {exc.reason} (headers: {exc.headers})") from exc


        if response.code != 200:
            raise ValueError('{}: {}: {}'.format(response.code, response.msg, response.reason))

        with open(self.path, 'wb') as audio:
            audio.write(response.read())

    def get_google(self):
        tts = gTTS(self.text, lang=self.lang, tld='cn')
        try:
            tts.save(self.path)
        except gTTSError as e:
            print('gTTS Error: {}'.format(e))

    def get_baidu(self):
        query = {
            'lan': self.lang,
            'ie': 'UTF-8',
            'text': self.text.encode('utf-8'),
        }

        url = 'http://tts.baidu.com/text2audio?' + urlencode(query)
        request = Request(url)
        request.add_header('User-Agent', 'Mozilla/5.0')
        response = urlopen(request, timeout=5)

        if response.code != 200:
            raise ValueError('{}: {}: {}'.format(response.code, response.msg, response.reason))

        with open(self.path, 'wb') as audio:
            audio.write(response.read())

    def get_aws(self):
        signer = AWS4Signer(service='polly')
        signer.use_aws_profile('chinese_support_redux')

        url = 'https://polly.%s.amazonaws.com/v1/speech' % (signer.region_name)
        query = {
            'OutputFormat': 'mp3',
            'Text': self.text,
            'VoiceId': self.lang,
        }

        response = requests.post(url, json=query, auth=signer)

        if response.status_code != 200:
            raise ValueError(
                'Polly Request Failed: Error Code {}'.format(
                    response.status_code
                )
            )

        with open(self.path, 'wb') as audio:
            audio.write(response.content)
