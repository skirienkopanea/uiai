import pythoncom
import time
import streamlit as st
import json
import os
from load_emails import load_emails
import shutil
import concurrent.futures
from qa import get_answer
import random

# TODO: Open emails: 
# TODO: Export chat history, save chats, resume chats.
# import streamlit as st
# import streamlit.components.v1 as components
# p = open("plot.html")
# components.html(p.read())
#TODO: support graphs, csv, tables
#TODO: rag for single uploaded file
#TODO: echo but with specified format i.e. json formatter, graph

def response_generator(response=None):
    if response is None: response = random.choice(
        [
            "Hello there! How can I assist you today?",
            "Hi, human! Is there anything I can help you with?",
            "Do you need help?",
        ]
    )
    for word in response.split():
        yield word + " "
        time.sleep(0.1)

st.set_page_config(page_title="🤖🔗 SAP Bot")
st.title('🤖🔗 SAP Bot')

st.sidebar.header("Settings")
# Define the path to the settings file
settings_path = 'settings.json'

# Load settings from the file
with open(settings_path, 'r') as file:
    settings = json.load(file)

user_settings_path = 'user_settings.json'

# Load settings from the file
with open(user_settings_path, 'r') as file:
    user_settings = json.load(file)

verbose = st.sidebar.checkbox('Show logs', user_settings.get('verbose', False))


avatar = {
        "system": '📢',
        "user": '🧑',
        "assistant": '🤖'
    }


def load_outlook(role="assistant",avatar=avatar):
    with st.chat_message(role,avatar=avatar.get(role)):
        st.write_stream(response_generator("Loading Outlook data..."))
        st.session_state.messages.append({"role": role, "content": "Loading Outlook data..."})

    def remove_folders():
        directory_path = settings["email_path"]
        if os.path.exists(directory_path) and os.path.isdir(directory_path):
                    shutil.rmtree(directory_path)
                    if verbose:
                        yield(f"\n\nDirectory '{directory_path}' and all its contents have been removed.")
        else:
            if verbose:
                yield(f"\n\nDirectory '{directory_path}' does not exist.")
        
        file_path = settings["db_path"]
        if os.path.exists(file_path) and os.path.isfile(file_path):
                    os.remove(file_path)
                    if verbose:
                        yield(f"\n\nFile '{file_path}' has been removed.")
        else:
            if verbose:
                yield(f"\n\nDirectory '{file_path}' does not exist.")

    
    role = "system"
    if verbose:
        with st.chat_message(role,avatar=avatar.get(role)):
            response = st.write_stream(remove_folders)
            st.session_state.messages.append({"role": role, "content": response})
    else:
        st.write_stream(remove_folders)
    
    try:
        pythoncom.CoInitialize()  # Initialize COM library in the current thread
        role = "system"
        if verbose:
            with st.chat_message(role,avatar=avatar.get(role)):
                response = st.write_stream(load_emails)
                st.session_state.messages.append({"role": role, "content": response})
        else:
            st.write_stream(load_emails)
        role = "system"
        with st.chat_message(role,avatar=avatar.get(role)):
            st.success("Outlook loaded")
            st.session_state.messages.append({"role": role, "success": "Outlook loaded"})    
    except Exception as e:
        role = "system"
        with st.chat_message(role,avatar=avatar.get(role)):
            st.exception(e)
    finally:
        pythoncom.CoUninitialize()  # Uninitialize COM library
  
# Function to render a message
def render_message(message):

    #avatar=st.image(f'path_to_image')
    with st.chat_message(message["role"],avatar=avatar.get(message['role'])):
        if "image" in message:
            st.image(message["image"], use_column_width=True, caption=message["image"])
        if "video" in message:
            st.video(message["video"])
        if "html" in message:
            # Read the HTML file
                with open(message["html"], 'r', encoding='utf-8') as file:
                    html_content = file.read()
                # Display the HTML content in Streamlit
                st.components.v1.html(html_content, height=600, scrolling=True)
        if "audio" in message:
            st.audio(message["audio"])
        if "code" in message:
            st.code(message["code"],language=message["language"])
        if "warning" in message:
            st.warning(message["warning"])
        if "error" in message:
            st.error(message["error"])
        if "info" in message:
            st.info(message["info"])
        if "success" in message:
            st.success(message["success"])
        if "exception" in message:
            st.exception(message["exception"])
        if "json" in message:
            st.json(message["json"])
        if "content" in message:
            st.markdown(message["content"])

# Sidebar inputs with prefilled values from settings
#kb_root_path = st.sidebar.text_input('Knowledge Base Root', settings.get('kb_root_path', './data/KnowledgeBase'))
# Add a button to the sidebar
openai_api_key = st.sidebar.text_input('OpenAI API Key', user_settings.get('OPENAI_API_KEY', ''), type='password')
if os.environ["OPENAI_API_KEY"] is None: os.environ["OPENAI_API_KEY"] = user_settings["OPENAI_API_KEY"]
email_address = st.sidebar.text_input('Email Address', user_settings.get('email_address', 'sergio.kirienko@inycom.es'))
email_folder = st.sidebar.text_input('Email Folder', user_settings.get('email_folder', 'Inbox'))
email_count = st.sidebar.number_input('Email Count', min_value=0, value=user_settings.get('email_count', 50))
appointment_count = st.sidebar.number_input('Appointment Count', min_value=0, value=user_settings.get('appointment_count', 5))
# Create a dictionary with the updated settings
updated_settings = {
    "verbose": verbose,
    "email_address": email_address,
    "email_folder": email_folder,
    "email_count": email_count,
    "appointment_count": appointment_count,
    "OPENAI_API_KEY": openai_api_key
}

# Write the updated settings to the JSON file whenever a value changes
def update_settings():
    with open(user_settings_path, 'w') as file:
        json.dump(updated_settings, file, indent=4)

# Check if any of the sidebar inputs have changed and update the settings file
if st.session_state.get('updated_settings', None) != updated_settings:
    st.session_state['updated_settings'] = updated_settings
    update_settings()

# Initialize chat history
if "messages" not in st.session_state:
    st.session_state.messages = []
    # Welcome message
    with st.chat_message("assistant",avatar=avatar.get("assistant")):
        response = st.write_stream(response_generator())
        # But dont log it to history, it disappears after first message.
# Display chat messages from history
for message in st.session_state.messages:
    render_message(message)

# React to user input
if prompt := st.chat_input("What do you need to know?"):
    
    # Display user message in chat message container
    with st.chat_message("user",avatar=avatar.get("user")):
        st.markdown(prompt)
    # Add user message to chat history
    st.session_state.messages.append({"role": "user", "content": prompt})

    # Call qa.apy method
    # Split qa script in vectorstore load, and qa only
    
    get_answer(prompt,verbose,avatar=avatar)

if st.sidebar.button('Load Outlook Data'):
    with concurrent.futures.ThreadPoolExecutor() as executor:
        load_outlook("assistant")
        # let each output to chat declare its own message append