from flask import Flask, request, jsonify
import firebase_admin
from firebase_admin import credentials, auth, firestore, storage
import random
import datetime
import uuid
from google.cloud import speech, texttospeech
from google.cloud import language_v1 # NEW: Import the Natural Language library
import tempfile
import os
import google.generativeai as genai

# --- Initialization ---
app = Flask(__name__)
GEMINI_API_KEY = "AIzaSyAXfJypU4UclvvKiq2QmCH_XlFCwChIy1o" 
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

# --- Firebase & Google Cloud Setup ---
try:
    cred = credentials.Certificate("serviceAccountKey.json")
    # You MUST specify the storage bucket URL when initializing
    firebase_admin.initialize_app(cred, {
        'storageBucket': 'genai-472705.appspot.com' # CORRECTED: Bucket names end with appspot.com
    })
    db = firestore.client()
    bucket = storage.bucket()
    print("--- Firebase connection successful ---")
except Exception as e:
    print(f"--- Firebase connection FAILED: {e} ---")

# Initialize Google Cloud AI clients
speech_client = speech.SpeechClient()
tts_client = texttospeech.TextToSpeechClient()
language_client = language_v1.LanguageServiceClient() # NEW: Initialize the Natural Language client


# --- Helper Functions ---
def generate_anonymous_username():
    """Generates a random anonymous username."""
    adjectives = ["Cosmic", "Quiet", "Silent", "Wandering", "Gentle", "Hidden"]
    nouns = ["River", "Moon", "Comet", "Oracle", "Pebble", "Star"]
    return f"{random.choice(adjectives)}{random.choice(nouns)}{random.randint(100, 999)}"


# --- ============================== ---
# --- USER & PUBLIC DIARY ENDPOINTS  ---
# --- ============================== ---

@app.route('/signup', methods=['POST'])
def signup():
    """Creates the user profile in Firestore after frontend creates auth user."""
    data = request.get_json()
    email = data.get('email')
    uid = data.get('uid')

    if not email or not uid:
        return jsonify({"error": "Email and UID are required."}), 400

    try:
        anon_username = generate_anonymous_username()
        user_data = {
            "email": email,
            "anonymous_username": anon_username,
            "uid": uid,
            "created_at": datetime.datetime.utcnow()
        }
        db.collection('users').document(uid).set(user_data)
        return jsonify({"message": "User profile created successfully!", "uid": uid, "username": anon_username}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route('/posts', methods=['GET'])
def get_posts():
    """Fetches all posts for the Public Diary."""
    try:
        posts_ref = db.collection('posts').order_by('timestamp', direction=firestore.Query.DESCENDING).limit(50)
        posts = [doc.to_dict() for doc in posts_ref.stream()]
        return jsonify(posts), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/posts', methods=['POST'])
def create_post():
    """Creates a new diary post AND analyzes its sentiment."""
    data = request.get_json()
    uid = data.get('uid')
    username = data.get('username')
    content = data.get('content')

    if not uid or not username or not content:
        return jsonify({"error": "User ID, username, and content are required."}), 400

    # --- NEW: Sentiment Analysis Step ---
    sentiment_score = 0.0
    sentiment_magnitude = 0.0
    try:
        document = language_v1.Document(content=content, type_=language_v1.Document.Type.PLAIN_TEXT)
        sentiment = language_client.analyze_sentiment(document=document).document_sentiment
        sentiment_score = sentiment.score
        sentiment_magnitude = sentiment.magnitude
        print(f"Sentiment analyzed: Score={sentiment_score}, Magnitude={sentiment_magnitude}")
    except Exception as e:
        print(f"Could not analyze sentiment: {e}")
        # If sentiment analysis fails, we still save the post, just without the scores.

    post_data = {
        "author_uid": uid,
        "author_username": username,
        "content": content,
        "timestamp": datetime.datetime.utcnow(),
        "sentiment_score": sentiment_score,         # NEW: Save the score
        "sentiment_magnitude": sentiment_magnitude  # NEW: Save the magnitude
    }
    
    try:
        db.collection('posts').add(post_data)
        return jsonify({"message": "Post created and analyzed successfully!"}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# --- =========================== ---
# --- ECHO CHAMBER ENDPOINTS      ---
# --- =========================== ---

@app.route('/echoes', methods=['POST'])
def create_echo():
    """Handles the full Echo Chamber audio processing pipeline."""
    if 'audio' not in request.files:
        return jsonify({"error": "No audio file provided"}), 400

    audio_file = request.files['audio']
    uid = request.form.get('uid')

    if not uid:
        return jsonify({"error": "User ID is required"}), 400

    temp_filename = None
    try:
        # 1. Save ORIGINAL audio to a cross-platform temporary file
        file_suffix = ".mp3" if audio_file.filename.lower().endswith(".mp3") else ".wav"
        with tempfile.NamedTemporaryFile(delete=False, suffix=file_suffix) as temp_audio_file:
            audio_file.save(temp_audio_file)
            temp_filename = temp_audio_file.name

        # 2. Transcribe using Google Speech-to-Text
        with open(temp_filename, "rb") as f:
            audio_data = f.read()
        
        audio = speech.RecognitionAudio(content=audio_data)

        # Dynamically set the encoding based on file type
        if file_suffix == ".mp3":
            config = speech.RecognitionConfig(
                encoding=speech.RecognitionConfig.AudioEncoding.MP3,
                sample_rate_hertz=16000,
                language_code="en-US"
            )
        else: # Assume WAV
            config = speech.RecognitionConfig(
                encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
                sample_rate_hertz=44100,
                language_code="en-US"
            )

        response = speech_client.recognize(config=config, audio=audio)
        
        if not response.results:
            return jsonify({"error": "Could not understand audio. The audio might be silent or in an unsupported format."}), 400
        transcript = response.results[0].alternatives[0].transcript

        # 3. Generate ANONYMOUS voice using Google Text-to-Speech
        synthesis_input = texttospeech.SynthesisInput(text=transcript)
        voice = texttospeech.VoiceSelectionParams(language_code="en-US", ssml_gender=texttospeech.SsmlVoiceGender.NEUTRAL)
        audio_config = texttospeech.AudioConfig(audio_encoding=texttospeech.AudioEncoding.MP3)
        response = tts_client.synthesize_speech(input=synthesis_input, voice=voice, audio_config=audio_config)
        anonymized_audio_content = response.audio_content

        # 4. Upload ANONYMOUS audio to Firebase Storage
        unique_filename = f"echoes/{uuid.uuid4()}.mp3"
        blob = bucket.blob(unique_filename)
        blob.upload_from_string(anonymized_audio_content, content_type='audio/mpeg')
        blob.make_public()
        
        # 5. Save metadata to Firestore
        echo_data = {
            "author_uid": uid,
            "audio_url": blob.public_url,
            "transcript": transcript,
            "glimmer_count": 0,
            "timestamp": datetime.datetime.utcnow()
        }
        db.collection('echoes').add(echo_data)

        return jsonify({"message": "Echo created successfully!", "url": blob.public_url}), 201

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    
    finally:
        # 6. Clean up the temporary file
        if temp_filename and os.path.exists(temp_filename):
            os.remove(temp_filename)

@app.route('/echoes', methods=['GET'])
def get_echoes():
    """Fetches all echoes for the galaxy display."""
    try:
        echoes_ref = db.collection('echoes').order_by('timestamp', direction=firestore.Query.DESCENDING).limit(100)
        echoes = []
        for doc in echoes_ref.stream():
            echo_data = doc.to_dict()
            echo_data['id'] = doc.id
            echoes.append(echo_data)
        return jsonify(echoes), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/echoes/<echo_id>/glimmer', methods=['POST'])
def add_glimmer(echo_id):
    """Increments the glimmer count for an echo."""
    try:
        echo_ref = db.collection('echoes').document(echo_id)
        echo_ref.update({"glimmer_count": firestore.Increment(1)})
        return jsonify({"message": "Glimmer added!"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    
# --- ============================== ---
# --- NEW: THE EMPATHY ENGINE        ---
# --- ============================== ---

@app.route('/posts/<post_id>/recommendation', methods=['GET'])
def get_recommendation(post_id):
    """
    Finds a supportive and relevant post for a user who has just submitted a negative post.
    This is the core of the Empathy Engine.
    """
    try:
        # 1. Fetch the user's negative post
        # Note: In a real app, we'd get the post from the DB. For speed, we'll get content from the request.
        negative_content = request.args.get('content')
        if not negative_content:
            return jsonify({"error": "Original post content is required."}), 400

        # 2. Fetch a list of recent, highly POSITIVE posts from the database
        positive_posts_ref = db.collection('posts').where('sentiment_score', '>', 0.7).order_by('sentiment_score', direction=firestore.Query.DESCENDING).limit(10)
        positive_posts = [doc.to_dict() for doc in positive_posts_ref.stream()]

        if not positive_posts:
            return jsonify({"recommendation": "No suitable positive posts found right now."}), 200

        # 3. Use the Gemini model to find the best match
        # We create a clean list of just the content for the AI
        positive_texts = [f"Post {i+1}: {post['content']}" for i, post in enumerate(positive_posts)]
        
        prompt = f"""
        You are an empathetic AI assistant for a mental wellness app. Your task is to find the most supportive and relevant post to recommend to a user who is feeling down.

        Here is the user's sad post:
        "{negative_content}"

        Here is a list of available positive posts from other users:
        {chr(10).join(positive_texts)}

        Analyze the user's sad post and the list of positive posts. Which single post from the list is the most helpful, relevant, and non-judgmental recommendation? 
        Respond with ONLY the number of the post you choose (e.g., "Post 3"). Do not add any other words or explanation.
        """
        
        response = model.generate_content(prompt)
        
        # 4. Extract the chosen post and return it
        chosen_post_text = response.text.strip() # e.g., "Post 3"
        chosen_index = int(chosen_post_text.split(" ")[1]) - 1
        
        recommended_post = positive_posts[chosen_index]

        return jsonify({"recommendation": recommended_post}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    app.run(debug=True, port=5001, use_reloader=True, reloader_type="stat")

