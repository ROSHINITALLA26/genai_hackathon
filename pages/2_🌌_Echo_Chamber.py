import streamlit as st
import requests
import streamlit.components.v1 as components
from streamlit_webrtc import webrtc_streamer, WebRtcMode, AudioProcessorBase
from streamlit_extras.switch_page_button import switch_page
import json
import av
import queue # NEW: Import the queue library for reliable audio capture

# --- Security Guard ---
st.set_page_config(layout="wide", initial_sidebar_state="auto")
if 'user' not in st.session_state or st.session_state.user is None:
    st.warning("You must be logged in to access this page.")
    if st.button("Go to Login"):
        switch_page("Login")
    st.stop()

# --- Backend URL ---
BACKEND_URL = "http://127.0.0.1:5001"

# --- NEW: Upgraded Audio Processing Logic using a Queue ---
class AudioRecorder(AudioProcessorBase):
    def __init__(self) -> None:
        # We create a queue to hold the audio frames. This is thread-safe.
        self.audio_queue = queue.Queue()

    def recv(self, frame: av.AudioFrame) -> av.AudioFrame:
        # Put all incoming audio frames into the queue to prevent them from being dropped.
        self.audio_queue.put(frame.to_ndarray().tobytes())
        return frame

# --- Page Content ---
st.title("🌌 The Echo Chamber")
st.markdown("Click on a star to listen to an anonymous echo. Add your own voice to the galaxy below.")

# --- Fetch All Echoes from Backend ---
try:
    response = requests.get(f"{BACKEND_URL}/echoes")
    if response.status_code == 200:
        echoes_data = response.json()
    else:
        echoes_data = []
        st.error("Could not fetch echoes from the server.")
except requests.exceptions.ConnectionError:
    echoes_data = []
    st.error("Could not connect to the backend. Is it running?")

# --- Create the Interactive Galaxy Component ---
galaxy_html = f"""
<!DOCTYPE html>
<html>
<head>
<style>
    body {{ margin: 0; }}
    #galaxy {{ position: relative; width: 100%; height: 500px; background: #000015; border-radius: 15px; overflow: hidden; }}
    .star {{ position: absolute; width: 15px; height: 15px; background-color: white; border-radius: 50%; box-shadow: 0 0 10px white; cursor: pointer; transition: transform 0.3s ease; }}
    .star:hover {{ transform: scale(1.5); }}
    .playing {{ animation: pulse 1.5s infinite; }}
    @keyframes pulse {{ 0% {{ transform: scale(1.2); }} 50% {{ transform: scale(1.6); }} 100% {{ transform: scale(1.2); }} }}
</style>
</head>
<body><div id="galaxy"></div>
<script>
    const echoes = {json.dumps(echoes_data)};
    const galaxy = document.getElementById('galaxy');
    let currentlyPlaying = null;
    echoes.forEach(echo => {{
        const star = document.createElement('div');
        star.className = 'star';
        star.style.left = `${{Math.random() * 95 + 2}}%`;
        star.style.top = `${{Math.random() * 95 + 2}}%`;
        const audio = new Audio(echo.audio_url);
        star.onclick = () => {{
            if (currentlyPlaying && currentlyPlaying !== audio) {{ currentlyPlaying.pause(); document.querySelector('.playing')?.classList.remove('playing'); }}
            if (audio.paused) {{ audio.play(); star.classList.add('playing'); currentlyPlaying = audio; }}
            else {{ audio.pause(); audio.currentTime = 0; star.classList.remove('playing'); currentlyPlaying = null; }}
        }};
        audio.onended = () => {{ star.classList.remove('playing'); currentlyPlaying = null; }};
        galaxy.appendChild(star);
    }});
</script>
</body></html>
"""
components.html(galaxy_html, height=510)

st.markdown("---")

# --- UI for Adding a New Echo ---
st.header("Add Your Voice to the Galaxy")
st.info("Click 'Start' to record, then 'Stop' when you are finished.")

webrtc_ctx = webrtc_streamer(
    key="audio-recorder",
    mode=WebRtcMode.SENDONLY,
    audio_processor_factory=AudioRecorder,
    media_stream_constraints={"video": False, "audio": True},
)

# This block runs AFTER the user clicks "Stop"
if not webrtc_ctx.state.playing and webrtc_ctx.audio_processor:
    audio_processor = webrtc_ctx.audio_processor
    
    # Check if there is any audio in our queue
    if not audio_processor.audio_queue.empty():
        st.info("Recording complete. Releasing your echo...")

        # Pull all audio frames from the queue and combine them into one file
        audio_frames = []
        while not audio_processor.audio_queue.empty():
            audio_frames.append(audio_processor.audio_queue.get())
        
        combined_audio_bytes = b"".join(audio_frames)

        with st.spinner("Processing your voice..."):
            try:
                files = {{'audio': ('echo.wav', combined_audio_bytes, 'audio/wav')}}
                payload = {{'uid': st.session_state.user['localId']}}
                
                response = requests.post(f"{{BACKEND_URL}}/echoes", files=files, data=payload)
                
                if response.status_code == 201:
                    st.success("Your echo has been released!")
                    st.balloons()
                    # We need to clear the queue to prevent resubmission on the next rerun
                    while not audio_processor.audio_queue.empty():
                        audio_processor.audio_queue.get()
                    st.rerun()
                else:
                    st.error("Failed to release your echo.")
                    st.json(response.json())
            except requests.exceptions.ConnectionError:
                st.error("Could not connect to the backend.")
