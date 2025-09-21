import streamlit as st
import pyrebase
import requests
from streamlit_extras.switch_page_button import switch_page  # if you use switch_page

# --- Firebase config ---
firebase_config = {
    "apiKey": st.secrets["firebase_config"]["apiKey"],
    "authDomain": st.secrets["firebaseb_config"]["authDomain"],
    "databaseURL": st.secrets["firebase_config"]["databaseURL"],
    "projectId": st.secrets["firebase_config"]["projectId"],
    "storageBucket": st.secrets["firebase_config"]["storageBucket"],
    "messagingSenderId": st.secrets["firebase_config"]["messagingSenderId"],
    "appId": st.secrets["firebase_config"]["appId"]
}

# --- Initialize Firebase ---
try:
    firebase = pyrebase.initialize_app(firebase_config)
    auth_client = firebase.auth()
except Exception:
    pass

# --- Backend URL ---
BACKEND_URL = "http://127.0.0.1:5001"  # replace with actual public URL



# --- Page Setup ---
st.set_page_config(layout="wide")
st.title("Welcome to Aether ✨")

# --- Logic ---
# First, check if the user is already logged in.
if 'user' in st.session_state and st.session_state.user is not None:
    st.success("You are already logged in.")
    if st.button("Go to the App Homepage"):
        switch_page("app")
else:
    # If not logged in, show the login/signup options.
    st.markdown("Please log in or sign up to continue.")
    choice = st.selectbox("Login or Signup", ["Login", "Signup"])
    email = st.text_input("Email")
    password = st.text_input("Password", type="password")

    if choice == "Login":
        if st.button("Login"):
            with st.spinner("Logging you in..."):
                try:
                    # Attempt to sign in with Firebase Auth
                    user = auth_client.sign_in_with_email_and_password(email, password)
                    # Save user details to the session state
                    st.session_state.user = user
                    # Navigate to the main app page
                    switch_page("app")
                except Exception as e:
                    st.error("Login failed. Please check your credentials.")

    else:  # Signup
        if st.button("Create Account"):
            with st.spinner("Creating your account..."):
                try:
                    # Step 1: Create the user in Firebase Authentication.
                    # This is the only place a new user is created in Auth.
                    user = auth_client.create_user_with_email_and_password(email, password)
                    uid = user['localId']  # Get the unique ID for the new user.
                    
                    # Step 2: Call your backend to create the user profile in Firestore.
                    signup_payload = {"email": email, "uid": uid}
                    response = requests.post(f"{BACKEND_URL}/signup", json=signup_payload)

                    if response.status_code == 201:
                        st.success("Account created! Logging you in...")
                        # Step 3: Automatically log the new user in.
                        st.session_state.user = auth_client.sign_in_with_email_and_password(email, password)
                        switch_page("app")
                    else:
                        st.error(f"Backend profile creation failed: {response.json().get('error')}")
                        # Important: If the backend fails, delete the user from Auth to prevent a "ghost" account.
                        id_token = user['idToken']
                        auth_client.delete_user_account(id_token)
                
                except Exception as e:
                    st.error("Could not create account. The email might already be in use.")