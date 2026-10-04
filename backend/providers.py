"""One configuration switch for either LiveKit Inference or direct OpenAI."""
import os


def cloud_configured():
    return bool(os.getenv('LIVEKIT_URL','').startswith('wss://') and
                os.getenv('LIVEKIT_API_KEY') not in {None,'','devkey'} and os.getenv('LIVEKIT_API_SECRET'))


def provider():
    selected=os.getenv('VOICE_PROVIDER','auto').strip().lower()
    if selected=='auto': return 'livekit' if cloud_configured() else 'openai'
    if selected not in {'livekit','openai'}: raise ValueError('VOICE_PROVIDER must be auto, livekit, or openai')
    return selected


def configured():
    return cloud_configured() if provider()=='livekit' else bool(os.getenv('OPENAI_API_KEY'))
