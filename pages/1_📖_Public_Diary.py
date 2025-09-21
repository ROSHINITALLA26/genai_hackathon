import streamlit as st
import requests
from streamlit_extras.switch_page_button import switch_page
import datetime # Used for displaying timestamps nicely

# --- The "Security Guard" ---
# This block of code is essential for every page except the Login page.
# It checks if the user is logged in before showing any content.
st.set_page_config(layout="wide", initial_sidebar_state="auto")
if 'user' not in st.session_state or st.session_state.user is None:
    st.warning("You must be logged in to access this page.")
    if st.button("Go to Login"):
        switch_page("Login")
    st.stop() # Prevents the rest of the page from running

# --- Page Content ---
BACKEND_URL = "http://127.0.0.1:5001"

st.title("📖 Public Diary")
st.markdown("Share what's on your mind. All posts are anonymous.")

# --- Post Creation Section ---
# This section sends data to your backend's POST /posts endpoint.
with st.form("new_post_form", clear_on_submit=True):
    new_post_content = st.text_area("Write your entry:", height=150, placeholder="What's on your mind today?")
    submitted = st.form_submit_button("Post to Diary")

    if submitted and new_post_content:
        # NOTE: For the hackathon, we send the UID. The backend looks up the anonymous username.
        # This is more secure and efficient.
        payload = {
            "uid": st.session_state.user['localId'],
            "username": "Anonymous", # The backend will replace this with the real one
            "content": new_post_content
        }
        try:
            response = requests.post(f"{BACKEND_URL}/posts", json=payload)
            if response.status_code == 201:
                st.success("Your entry has been posted!")
            else:
                st.error(f"Failed to post. The server said: {response.text}")
        except requests.exceptions.ConnectionError:
            st.error("Could not connect to the backend. Is your backend server running?")
    elif submitted:
        st.warning("You can't post an empty entry.")

st.markdown("---")

# --- Display Posts Section ---
# This section fetches data from your backend's GET /posts endpoint.
st.subheader("Recent Entries from the Community")
try:
    response = requests.get(f"{BACKEND_URL}/posts")
    if response.status_code == 200:
        posts = response.json()
        if not posts:
            st.info("The diary is empty. Be the first to share something!")
        
        # Display each post
        for post in posts:
            with st.container():
                # Display the author's anonymous username
                st.markdown(f"**{post.get('author_username', 'Anonymous')}**")
                
                # Display the post content
                st.write(post.get('content'))
                
                # Display placeholder for reactions and comments
                st.markdown("`❤️` `✨` `🫂` `💬`")
                st.markdown("<hr>", unsafe_allow_html=True)
    else:
        st.error("Could not fetch posts from the server.")
except requests.exceptions.ConnectionError:
    st.error("Could not connect to the backend. Is it running?")