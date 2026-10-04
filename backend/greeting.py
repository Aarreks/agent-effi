"""Prepare the constant greeting before calls so it needs no live model round trip."""
import asyncio
import hashlib
import logging
import os
from pathlib import Path
import wave
import aiohttp
from dotenv import load_dotenv
from livekit import rtc
from livekit.agents import inference

GREETING="Hi, I'm Effi. Are you reporting a new issue or checking an existing case?"


def cache_path():
    model=os.getenv('LIVEKIT_TTS_MODEL','fishaudio/s2.1-pro')
    voice=os.getenv('LIVEKIT_TTS_VOICE','fa4c9eb3dccc4806b382b40d61c6b10a')
    fingerprint=hashlib.sha256((GREETING+'|'+model+'|'+voice).encode()).hexdigest()[:20]
    return Path('data/greetings')/(fingerprint+'.wav')


def cached_audio():
    path=cache_path()
    if not path.exists():return None
    try:
        with wave.open(str(path),'rb') as audio:
            if audio.getsampwidth()!=2 or audio.getnchannels()!=1 or audio.getnframes()<1:return None
    except (wave.Error,EOFError,OSError):return None
    async def frames():
        with wave.open(str(path),'rb') as audio:
            rate=audio.getframerate();chunk=max(1,rate//50)
            while data:=audio.readframes(chunk):
                yield rtc.AudioFrame(data=data,sample_rate=rate,num_channels=1,samples_per_channel=len(data)//2)
    return frames()


async def prepare():
    from .providers import provider,configured
    if provider()!='livekit' or not configured():return
    if cached_audio() is not None:
        print('Greeting audio is ready locally.')
        return
    path=cache_path();path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_suffix('.tmp')
    try:
        async with asyncio.timeout(20),aiohttp.ClientSession() as http:
            model=inference.TTS(model=os.getenv('LIVEKIT_TTS_MODEL','fishaudio/s2.1-pro'),
                                voice=os.getenv('LIVEKIT_TTS_VOICE','fa4c9eb3dccc4806b382b40d61c6b10a'),http_session=http)
            try:
                with wave.open(str(temporary),'wb') as audio:
                    audio.setnchannels(1);audio.setsampwidth(2);audio.setframerate(model.sample_rate)
                    async with model.synthesize(GREETING) as stream:
                        async for event in stream:audio.writeframes(bytes(event.frame.data))
                temporary.replace(path)
            finally:await model.aclose()
        print('Greeting audio prepared with the configured voice.')
    except Exception as exc:
        logging.getLogger('effigov.greeting').warning('Greeting preparation unavailable (%s); calls will use live speech synthesis.',type(exc).__name__)


if __name__=='__main__':
    load_dotenv('.env')
    asyncio.run(prepare())
