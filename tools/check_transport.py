"""Verify real local LiveKit data/audio transport. No model API or microphone."""
import asyncio
import uuid
from livekit import api, rtc


async def main():
    room_name='transport-check-'+uuid.uuid4().hex[:8]
    a,b=rtc.Room(),rtc.Room()
    data_received=asyncio.Event()
    track_received=asyncio.Event()
    samples_received=asyncio.Event()
    read_task=None
    source=None

    @b.on('data_received')
    def data(packet):
        if packet.data==b'effigov transport check': data_received.set()

    @b.on('track_subscribed')
    def track(track,publication,participant):
        nonlocal read_task
        if track.kind==rtc.TrackKind.KIND_AUDIO:
            track_received.set()
            async def read():
                stream=rtc.AudioStream(track)
                try:
                    async for event in stream:
                        if event.frame.samples_per_channel>0:
                            samples_received.set()
                            return
                finally:
                    await stream.aclose()
            read_task=asyncio.create_task(read())

    def token(identity):
        return api.AccessToken('devkey','secret').with_identity(identity).with_grants(api.VideoGrants(room_join=True,room=room_name)).to_jwt()

    try:
        await a.connect('ws://127.0.0.1:7880',token('sender'))
        await b.connect('ws://127.0.0.1:7880',token('receiver'))
        await a.local_participant.publish_data(b'effigov transport check',reliable=True)
        await asyncio.wait_for(data_received.wait(),10)
        source=rtc.AudioSource(24000,1)
        track=rtc.LocalAudioTrack.create_audio_track('synthetic-audio',source)
        options=rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_MICROPHONE)
        await a.local_participant.publish_track(track,options)
        await asyncio.wait_for(track_received.wait(),10)
        for _ in range(50):
            await source.capture_frame(rtc.AudioFrame(data=b'\0'*960,sample_rate=24000,num_channels=1,samples_per_channel=480))
        await asyncio.wait_for(samples_received.wait(),10)
        print('PASS: two real LiveKit participants connected; data delivered; synthetic audio received.')
    finally:
        if read_task:
            read_task.cancel()
            await asyncio.gather(read_task,return_exceptions=True)
        if source: await source.aclose()
        await a.disconnect();await b.disconnect()
        async with api.LiveKitAPI(url='ws://127.0.0.1:7880',api_key='devkey',api_secret='secret') as lk:
            await lk.room.delete_room(api.DeleteRoomRequest(room=room_name))


if __name__=='__main__': asyncio.run(main())
