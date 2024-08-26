import pythoncom
import time
import streamlit as st
import json
import os
from load_emails import load_emails
import shutil
import concurrent.futures
from qa import get_answer

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


def load_outlook():
    printlist = []
    directory_path = settings["email_path"]
    if os.path.exists(directory_path) and os.path.isdir(directory_path):
                shutil.rmtree(directory_path)
                if verbose: printlist.append(
                    {
                    "info":f"Directory '{directory_path}' and all its contents have been removed."
                    ,"role":"system"
                    })
    else:
         if verbose: printlist.append(
                    {
                    "warning":f"Directory '{directory_path}' does not exist."
                    ,"role":"system"
                    })
    
    file_path = settings["db_path"]
    if os.path.exists(file_path) and os.path.isfile(file_path):
                os.remove(file_path)
                if verbose: printlist.append(
                    {
                    "info":f"File '{file_path}' has been removed."
                    ,"role":"system"
                    })
    else:
         if verbose: printlist.append(
                    {
                    "warning":f"Directory '{file_path}' does not exist."
                    ,"role":"system"
                    })
    try:
        pythoncom.CoInitialize()  # Initialize COM library in the current thread
        email_logs = load_emails()
        if verbose:
            printlist = printlist + email_logs
    except Exception as e:
        return [{
                    "exception":e
                    ,"role":"system"
                    }]
    finally:
        pythoncom.CoUninitialize()  # Uninitialize COM library
    
    printlist.append(
                    {
                    "success":f"Outlook data loaded!"
                    ,"role":"system"
                    })
    
    return printlist
  
# Function to render a message
def render_message(message):

    #avatar=st.image(f'path_to_image')
    with st.chat_message(message["role"],avatar=avatar.get(message['role'])):
        if "image" in message:
            st.image(message["image"], use_column_width=True)
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
if st.sidebar.button('Load Outlook Data'):
    #st.session_state.messages.append({"role": "system", "warning": "Hey!!"})
    #st.session_state.messages.append({"role": "system", "content": "hello"})

    with concurrent.futures.ThreadPoolExecutor() as executor:
        future = executor.submit(load_outlook)
        result = future.result()
    for res in result:
        st.session_state.messages.append(res)
    
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
    responses = get_answer(prompt,verbose)


    for response in responses:
        render_message(response)
# Add assistant response to chat history
        st.session_state.messages.append(response)