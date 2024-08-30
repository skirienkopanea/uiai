from langchain_openai import OpenAIEmbeddings
from langchain_chroma import Chroma
import tempfile
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
from load_vs import load_vs

#TODO: Use a Local HTTP Server to Serve Files
#TODO: use collection for filepaths instead of passing all of them as context
#TODO: replace yields in qa for with context so that messages and logs get stored in the right order
#TODO: remove repeated lines of code in answer
# TODO: Make KB load like TEMP load and make qa vectorstore retrieval like single file
# TODO: Export chat history, save chats, resume chats.
# import streamlit as st
# import streamlit.components.v1 as components
# p = open("plot.html")
# components.html(p.read())
#TODO: support graphs, csv, tables
#TODO: rag for single uploaded file
#TODO: echo but with specified format i.e. json formatter, graph
#TODO: use embbeding model as setting param
#TODO: remove temp chroma db
#TODO: use external vectorstore i.e. pinecone

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

# Define the path to the settings file
settings_path = 'settings.json'

# Load settings from the file
with open(settings_path, 'r') as file:
    settings = json.load(file)

user_settings_path = 'user_settings.json'

# Load settings from the file
with open(user_settings_path, 'r') as file:
    user_settings = json.load(file)
verbose = user_settings.get('verbose', False)
avatar = {"system": '📢', "user": '🧑', "assistant": '🤖'}
st.sidebar.title("Settings")
verbose = st.sidebar.checkbox('Show logs', user_settings.get('verbose', False))
st.sidebar.header("Document Search")
uploaded_file = st.sidebar.file_uploader("Choose a file", type=["txt"])#, "docx", "doc", "pdf", "pptx", "ppt", "html", "md", "eml"])

# Check if a file is uploaded
rag_file_context_only = None
filename = None
apply_file = False
temp_file_path = None #Update settings file store it in file session and pass it to get answer()
temp_dir = None

if 'last_uploaded_file_info' not in st.session_state:
    st.session_state.last_uploaded_file_info = None
    st.session_state.file_uploaded = False
    st.session_state.temp_file_path = None


if uploaded_file is not None:
    st.session_state.file_uploaded = True
    filename = uploaded_file.name
    current_file_info = (filename, uploaded_file.size)

    # Update the session state with the current file's info
    st.session_state.last_uploaded_file_info = current_file_info

    rag_file_context_only = st.sidebar.checkbox("Only use this file as context", value=True)
if st.sidebar.button('Update Database'):
    apply_file = True
    if rag_file_context_only is not True: rag_file_context_only = False
    if uploaded_file is not None and rag_file_context_only:
        if temp_dir is not None:
            temp_dir.cleanup()
        # Create a temporary directory to save the uploaded file
        temp_dir = tempfile.TemporaryDirectory()    
        # Define the file path
        temp_file_path = os.path.join(temp_dir.name, uploaded_file.name)
        # Save the uploaded file to the temporary directory
        with open(temp_file_path, "wb") as f:
            f.write(uploaded_file.getvalue())
        
        if verbose:
            role = "system"
            text = f"""File uploaded to {temp_file_path}"""
            st.session_state.messages.append({"role": role, "info": text})
        st.session_state.temp_file_path = temp_file_path
k = st.sidebar.number_input('Paragraph search count', min_value=1, max_value=7,value=user_settings.get('k', 4))
st.sidebar.markdown("----")

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
        
        db_file_path = settings["db_path"]
        if os.path.exists(db_file_path) and os.path.isfile(db_file_path):
                    os.remove(db_file_path)
                    if verbose:
                        yield(f"\n\nFile '{db_file_path}' has been removed.")
        else:
            if verbose:
                yield(f"\n\nDirectory '{db_file_path}' does not exist.")

    
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
  

# Sidebar inputs with prefilled values from settings
#kb_root_path = st.sidebar.text_input('Knowledge Base Root', settings.get('kb_root_path', './data/KnowledgeBase'))
# Add a button to the sidebar
openai_api_key = st.sidebar.text_input('OpenAI API Key', user_settings.get('OPENAI_API_KEY', os.environ["OPENAI_API_KEY"]), type='password')

st.sidebar.header("Outlook Data")
if os.environ["OPENAI_API_KEY"] is None: os.environ["OPENAI_API_KEY"] = user_settings["OPENAI_API_KEY"]
email_address = st.sidebar.text_input('Email Address', user_settings.get('email_address', 'sergio.kirienko@inycom.es'))
email_folder = st.sidebar.text_input('Email Folder', user_settings.get('email_folder', 'Inbox'))
email_count = st.sidebar.number_input('Email Count', min_value=0, value=user_settings.get('email_count', 50))
appointment_count = st.sidebar.number_input('Appointment Count', min_value=0, value=user_settings.get('appointment_count', 5))
# Create a dictionary with the updated settings
updated_settings = {
    "rag_file_context_only": rag_file_context_only,
    "k": k,
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

###-- Button logic

if st.sidebar.button('Load Outlook Data'):
    with concurrent.futures.ThreadPoolExecutor() as executor:
        load_outlook("assistant")
        # let each output to chat declare its own message append

###--Initalise chat

# Function to render a message
def render_message(message):

    #avatar=st.image(f'path_to_image')
    with st.chat_message(message["role"],avatar=avatar.get(message['role'])):
        if "image" in message:
            st.image(message["image"], use_column_width=True)
        if "video" in message:
            st.video(message["video"])
        if "df" in message:
            st.write(message["df"])
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

# Initialize chat history
if "messages" not in st.session_state:
    st.session_state.messages = []

# Display chat messages from history
for message in st.session_state.messages:
    render_message(message)

if len(st.session_state.messages) == 0:
    with st.chat_message("assistant",avatar=avatar.get("assistant")):
        response = st.write_stream(response_generator())
        st.session_state.messages.append({"role": "assistant", "content": response})

# Load Vectorstore before asking for user input
  
if rag_file_context_only and apply_file and st.session_state.file_uploaded:
    role = "assistant"
    with st.chat_message(role,avatar=avatar.get(role)):
        text = f"""Okay, I will use {filename} as the only context for my answers."""
        st.write_stream(response_generator(text))
        st.session_state.messages.append({"role": role, "content": text})
    try:
        load_vs(st.session_state.temp_file_path,verbose,settings["vs_temp_path"],"file-contents")
    except Exception as e:
        st.exception(e)
        
if rag_file_context_only is False and apply_file and rag_file_context_only is not None:
    role = "assistant"
    with st.chat_message(role,avatar=avatar.get(role)):
        text = f"""Okay, I will use all the files in the knowledge base for my answers.
        Knoweledge base: {settings["kb_root_path"]}"""
        st.write_stream(response_generator(text))
        st.session_state.messages.append({"role": role, "content": text})
        st.session_state.temp_file_path = None
    try:
        load_vs(settings["kb_root_path"],verbose,settings["vs_path"],"file-contents")
    except Exception as e:
        st.exception(e)

# React to user input
if prompt := st.chat_input("What do you need to know?"):
    
    # Display user message in chat message container
    with st.chat_message("user",avatar=avatar.get("user")):
        st.markdown(prompt)
    # Add user message to chat history
    st.session_state.messages.append({"role": "user", "content": prompt})

    # Call qa.apy method
    # Split qa script in vectorstore load, and qa only
    print(st.session_state.temp_file_path)
    if rag_file_context_only and st.session_state.temp_file_path is not None:
        get_answer(prompt,verbose,k,persist_directory=settings["vs_temp_path"],avatar=avatar,temp_file_path=st.session_state.temp_file_path)
    else:
        persist_directory=settings["vs_path"]
        get_answer(prompt,verbose,k,persist_directory=persist_directory,avatar=avatar)