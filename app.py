import streamlit as st
from streamlit_extras.switch_page_button import switch_page
import requests

# --- Page Configuration ---
st.set_page_config(
    page_title="Aether Feed",
    page_icon="✨",
    layout="wide",
    initial_sidebar_state="auto"
)

# --- The "Security Guard" ---
# This is the most important part. It checks if a user is logged in.
# If not, it stops the page from loading and shows a link to the login page.
if 'user' not in st.session_state or st.session_state.user is None:
    st.warning("Please log in to access the application.")
    if st.button("Go to Login"):
        switch_page("Login")
    st.stop()

# --- Load Custom CSS for the Instagram-style feed ---
def load_css(file_name):
    try:
        with open(file_name) as f:
            st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)
    except FileNotFoundError:
        st.error("style.css file not found. Please create it in the main project folder.")

load_css("style.css")

# --- Backend URL ---
BACKEND_URL = "http://127.0.0.1:5001"

# --- Sidebar with User Info and Logout Button ---
with st.sidebar:
    # Securely display the anonymous username fetched during login
    if 'user_profile' in st.session_state and st.session_state.user_profile:
        welcome_name = st.session_state.user_profile.get('anonymous_username', 'Anonymous')
        st.success(f"Logged in as {welcome_name}")
    
    if st.button("Logout"):
        st.session_state.user = None
        st.session_state.user_profile = None # Clear the user's profile on logout
        switch_page("Login")

# --- Main Page Content ---
st.title("Aether Feed")

# --- Form for Creating a New Post ---
with st.form("new_post_form", clear_on_submit=True):
    new_post_content = st.text_area("What's on your mind?", placeholder="Share a thought with the community...")
    submitted = st.form_submit_button("Post")

    if submitted and new_post_content:
        # We only need to send the user's secure UID. 
        # The backend will look up their anonymous name to prevent impersonation.
        payload = { "uid": st.session_state.user['localId'], "content": new_post_content }
        try:
            response = requests.post(f"{BACKEND_URL}/posts", json=payload)
            if response.status_code == 201:
                st.success("Your post is live!")
            else:
                st.error(f"Failed to post: {response.text}")
        except requests.exceptions.ConnectionError:
            st.error("Could not connect to the backend. Is it running?")
    elif submitted:
        st.warning("Post cannot be empty.")

st.markdown("---")

# --- Live Feed Display from the Database ---
try:
    # Fetch all posts from the backend
    response = requests.get(f"{BACKEND_URL}/posts")
    if response.status_code == 200:
        posts = response.json()
        if not posts:
            st.info("The feed is empty. Be the first to share something!")
        
        # This div is the container for our styled feed
        st.markdown('<div class="post-feed">', unsafe_allow_html=True)
        
        for post in posts:
            author = post.get('author_username', 'Anonymous')
            content = post.get('content', '')
            
            # Inject HTML and CSS to create the styled "post card"
            st.markdown(f"""
                <div class="post-card">
                    <div class="post-author">{author}</div>
                    <div class="post-content">{content}</div>
                    <div class="post-reactions">❤️ ✨ 🫂 💬</div>
                </div>
            """, unsafe_allow_html=True)
            
        st.markdown('</div>', unsafe_allow_html=True)
        
    else:
        st.error("Could not fetch posts from the server.")
except requests.exceptions.ConnectionError:
    st.error("Could not connect to the backend.")

