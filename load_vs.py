import gc
from io import StringIO
import mimetypes
import inspect
import sys
from colorama import Fore, Back, Style, init
import shutil
import os
import json
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import WebBaseLoader, DirectoryLoader, TextLoader, CSVLoader
from langchain_chroma import Chroma
from openai import OpenAI
from langchain_openai import OpenAIEmbeddings
import warnings
from datetime import datetime
from db_agent import sqlquery
from question_graph import generate_graph
import pandas as pd
import streamlit as st
import re



# to do: make only rag assistant in other script 
# this script only for RAG, replace vectorstoredb for large scale db

#TODO: use online vectorstore
#TODO: change CSV for SQL uploader
#TODO: upload sap commissions documentation
#TODO: upload sap commissions db schema
#TODO: make the possibility to send emails
#TODO: optimize rag (rag by filepath, rag by file summary, rag by file contents, rag by other metadata?)

settings_path = 'settings.json'
user_settings_path = 'user_settings.json'
settings = {}


# Open the file and load the JSON data
with open(settings_path, 'r') as file:
    settings = json.loads(file.read())
with open(user_settings_path, 'r') as file:
    settings.update(json.loads(file.read()))


if os.environ["OPENAI_API_KEY"] is None: os.environ["OPENAI_API_KEY"] = settings["OPENAI_API_KEY"]

def load_kb_vs(file_path,verbose,avatar={"system": '📢',"user": '🧑',"assistant": '🤖'},role="system"):

    if not verbose:
        warnings.filterwarnings("ignore")
    
    persist_directory = settings["vs_path"]

    
    # Same model for both vs
    if True:
        model = OpenAIEmbeddings(model="text-embedding-3-small")
        print("Deleting ",persist_directory)
        if not os.path.exists(persist_directory):
            os.makedirs(persist_directory)

        if os.path.exists(persist_directory) and os.path.isdir(persist_directory):
            shutil.rmtree(persist_directory)
            if verbose:
                text = f"Directory '{persist_directory}' and all its contents have been removed."
                st.info(text)
                st.session_state.messages.append({"role": role, "info": text})            
                
        else:
            if verbose:
                text = f"Directory '{persist_directory}' does not exist or is not a directory."
                st.info(text)
                st.session_state.messages.append({"role": role, "info": text})

    # Loader for KB
    if True :
        root = settings["kb_root_path"]
        loader = DirectoryLoader(root, glob=["**/*.docx","**/*.txt","**/*.pdf","**/*.sql"],
                                exclude=["Bad Apples/*"],
                                recursive=True)
        docs = loader.load()
        if verbose:
            text = f"Documents loaded"
            st.info(text)
            st.session_state.messages.append({"role": role, "info": text})
            
        
        # Here, we first split at paragraph level,
        # if the chunk size exceeds, it will move onto the next separator, at sentence level,
        # if it still exceeds, it will move onto the next separators.
        # FOR CSV is better to use SQL
        text_splitter = RecursiveCharacterTextSplitter(
        separators=["\n\n","\n", ",", " "],
        chunk_size = 500,
        chunk_overlap = 100,
        is_separator_regex=False
        )

        if verbose:
            text = f"Text splitter loaded"
            st.info(text)
            st.session_state.messages.append({"role": role, "info": text})

        # Walk through all directories and subdirectories
        for dirpath, dirnames, filenames in os.walk(root):
            for filename in filenames:
                if filename.endswith('.csv'):
                    # Construct the full path to the file
                    file_path = os.path.join(dirpath, filename)
                    loader = loader = CSVLoader(file_path, encoding="windows-1252")
                    csv_docs = loader.load()
                    docs = docs + csv_docs
                    
        if verbose:
            text = f"CSV loaded"
            st.info(text)
            st.session_state.messages.append({"role": role, "info": text})
        for doc in docs:
            doc.metadata["source"] = doc.metadata["source"].replace("./","").replace("/","\\")
        
        splits = text_splitter.split_documents(docs)

        if verbose:
            text = f"Splits loaded"
            st.info(text)
            st.session_state.messages.append({"role": role, "info": text})

        
        # Embed
        # This is our way to index the chunks for retrieval
        # You have to check in your openai API subscription which embedding models you have available.
        # You should already have saved the environment variable OPENAI_API_KEY in your system.
 
    vectorstoredb = Chroma.from_documents(persist_directory=persist_directory, documents=splits, embedding=model)

    role = "assistant"
    text = f"Vectorstore loaded"
    st.success(text)
    st.session_state.messages.append({"role": role, "success": text})
    gc.collect() 

def load_temp_vs(file_path,verbose,persist_directory,avatar={"system": '📢',"user": '🧑',"assistant": '🤖'},role="system"):

    if not verbose:
        warnings.filterwarnings("ignore")
    
    # Same model for both vs
    if True:
        model = OpenAIEmbeddings(model="text-embedding-3-small")
        print("Deleting ",persist_directory)
        if not os.path.exists(persist_directory):
            os.makedirs(persist_directory)
            text = f"Directory '{persist_directory}' created."
            st.info(text)
            st.session_state.messages.append({"role": role, "info": text})   

        if os.path.exists(persist_directory) and os.path.isdir(persist_directory):
            shutil.rmtree(persist_directory)
            if verbose:
                text = f"Directory '{persist_directory}' and all its contents have been removed."
                st.info(text)
                st.session_state.messages.append({"role": role, "info": text})            
                
        else:
            if verbose:
                text = f"Directory '{persist_directory}' does not exist or is not a directory."
                st.info(text)
                st.session_state.messages.append({"role": role, "info": text})

    if True:
        print("TEXT LOADER FILE",file_path)
        loader = TextLoader(file_path)
        docs = loader.load()
        if verbose:
            text = f"Document loaded"
            st.info(text)
            st.session_state.messages.append({"role": role, "info": text})
            
        
        # Here, we first split at paragraph level,
        # if the chunk size exceeds, it will move onto the next separator, at sentence level,
        # if it still exceeds, it will move onto the next separators.
        # FOR CSV is better to use SQL
        text_splitter = RecursiveCharacterTextSplitter(
        separators=["\n\n","\n", ",", " "],
        chunk_size = 500,
        chunk_overlap = 100,
        is_separator_regex=False
        )

        if verbose:
            text = f"Text splitter loaded"
            st.info(text)
            st.session_state.messages.append({"role": role, "info": text})
        
        for doc in docs:
            doc.metadata["source"] = doc.metadata["source"].replace("./","").replace("/","\\")

        splits = text_splitter.split_documents(docs)
    
        if verbose:
            text = f"Splits loaded"
            st.info(text)
            st.session_state.messages.append({"role": role, "info": text})
    
    vectorstoredb = Chroma.from_documents(persist_directory=persist_directory, documents=splits, embedding=model)
    role = "assistant"
    text = f"Vectorstore loaded"
    st.success(text)
    st.session_state.messages.append({"role": role, "success": text})
    gc.collect()
