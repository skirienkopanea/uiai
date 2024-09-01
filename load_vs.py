from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction
from colorama import Fore, Back, Style, init
import shutil
import os
import json
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import DirectoryLoader, TextLoader, CSVLoader
from langchain_unstructured import UnstructuredLoader
from unstructured.cleaners.core import clean_extra_whitespace
from langchain_openai import OpenAIEmbeddings
import warnings
from db_agent import sqlquery
from question_graph import generate_graph
import pandas as pd
import streamlit as st
import re
import openai
from chromadb import PersistentClient
from chromadb.db.base import UniqueConstraintError  
from langchain_community.document_loaders import TextLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter

settings_path = 'settings.json'
user_settings_path = 'user_settings.json'
settings = {}

# Open the file and load the JSON data
with open(settings_path, 'r') as file:
    settings = json.loads(file.read())
with open(user_settings_path, 'r') as file:
    settings.update(json.loads(file.read()))

if os.environ["OPENAI_API_KEY"] is None: os.environ["OPENAI_API_KEY"] = settings["OPENAI_API_KEY"]

model = OpenAIEmbeddings(model=settings["embbedings_model"])

if 'chroma_client' not in st.session_state:
    st.session_state.collection_name = None
    st.session_state.chroma_client = None

def delete_collection(persist_directory,verbose,chroma_client=st.session_state.chroma_client, collection_name=st.session_state.collection_name):
    try:
        chroma_client.delete_collection(collection_name)
        print(f"Collection {collection_name} deleted successfully.")
    except Exception as e:
        raise Exception(f"Unable to delete collection: {e}")
    try:
        remove_directory(persist_directory,verbose)
    except Exception as e:
        raise Exception(f"Unable to remove collection fklder: {e}") 

def create_collection(chroma_client, collection_name,embedding_function):
    
    collection = chroma_client.create_collection(name=collection_name, embedding_function=embedding_function)
    return collection

def get_embedding(text, model="text-embedding-3-small"):
    response = openai.embeddings.create(input=[text], model=model)
    return response.data[0].embedding

def remove_directory(persist_directory,verbose,role="assistant"):
    if not os.path.exists(persist_directory):
        os.makedirs(persist_directory)
        text = f"Directory '{persist_directory}' created."
        st.info(text)
        st.session_state.messages.append({"role": role, "info": text})   

    if os.path.exists(persist_directory) and os.path.isdir(persist_directory):
        for item in os.listdir(persist_directory):
            item_path = os.path.join(persist_directory, item)
            if os.path.isdir(item_path):
                shutil.rmtree(item_path)
                print(item_path)
                if verbose:
                    text = f"Directory '{item_path}' and all its contents have been removed."
                    st.info(text)
                    st.session_state.messages.append({"role": role, "info": text})              
            
    else:
        if verbose:
            text = f"Directory '{persist_directory}' does not exist or is not a directory."
            st.info(text)
            st.session_state.messages.append({"role": role, "info": text})

def get_docs(file_path,verbose,role="assistant"):

    if os.path.isfile(file_path):
        loader = UnstructuredLoader(
        file_path,
        post_processors=[clean_extra_whitespace],
    )

        docs = loader.load()
        if verbose:
            text = f"Document loaded"
            st.info(text)
            st.session_state.messages.append({"role": role, "info": text})
    
    elif os.path.isdir(file_path):
        root = file_path
        loader = DirectoryLoader(root, glob=["**/*.docx","**/*.html","**/*.pdf","**/*.sql","**/*.ppt"],
                                exclude=["*Images/*"],
                                recursive=True)
        docs = loader.load()
        if verbose:
            text = f"Knoweledge base loaded"
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
        metadata_for_chromadb = {
        #'points': json.dumps(doc.metadata['points']),
        #'system': doc.metadata['system'],
        #'layout_width': doc.metadata['layout_width'],
        #'layout_height': doc.metadata['layout_height'],
        'source': doc.metadata["source"].replace("./","").replace("\\","/")
}
        doc.metadata = metadata_for_chromadb

    splits = text_splitter.split_documents(docs)
    
    if verbose:
        text = f"Splits loaded"
        st.info(text)
        st.session_state.messages.append({"role": role, "info": text})

    docs = {
        "ids": [str(i) for i in range(len(splits))],
        "embeddings":  [get_embedding(split.page_content) for split in splits],
        "metadatas" : [split.metadata for split in splits],
        "documents": [split.page_content for split in splits]
    }
    return docs
    
def load_vs(file_path,verbose,persist_directory,collection_name,avatar={"system": '📢',"user": '🧑',"assistant": '🤖'},role="system"):
    if 'chroma_client' not in st.session_state:
        st.session_state.collection_name = None
        st.session_state.chroma_client = None

    if not verbose:
        warnings.filterwarnings("ignore")
    
    if st.session_state.chroma_client is not None and st.session_state.collection_name is not None:
        try:
            delete_collection(persist_directory,verbose,st.session_state.chroma_client,st.session_state.collection_name)
            text = f"Deleted {st.session_state.collection_name} collection."
            st.info(text)
            st.session_state.messages.append({"role": role, "info": text})
        except Exception as e:
            text = "Collection not deleted because it doesn't exist"
            st.warning(text)
            st.session_state.messages.append({"role": role, "warning": text})

    # Specify the directory for persisting the ChromaDB data
    chroma_client = PersistentClient(path=persist_directory)
    st.session_state.chroma_client = chroma_client

    st.session_state.collection_name = collection_name

    model = OpenAIEmbeddingFunction(api_key=os.environ.get('OPENAI_API_KEY'), model_name=settings["embbedings_model"])

    try:
        collection = create_collection(chroma_client, collection_name,model)
    except UniqueConstraintError as e:
        
        st.error(e)
        st.session_state.messages.append({"role": role, "error": e})
        delete_collection(persist_directory,verbose,chroma_client,collection_name)
        st.session_state.collection_name = None # In case it crashes it should know that it doesnt exist
        text = f"Deleted {collection_name} collection."
        st.info(text)
        st.session_state.messages.append({"role": role, "info": text})
        collection = create_collection(chroma_client, collection_name,model)
        
    if verbose:
        text=(f"Collection {collection_name} created successfully.")
        st.info(text)
        st.session_state.messages.append({"role": role, "info": text})

    try:
        if os.path.isdir(file_path): title_collection = create_collection(chroma_client, "file-names",model)
    except UniqueConstraintError as e:
        
        st.error(e)
        st.session_state.messages.append({"role": role, "error": e})
        if os.path.isdir(file_path): delete_collection(persist_directory,verbose,chroma_client,"file-names")
        st.session_state.collection_name = None # In case it crashes it should know that it doesnt exist
        text = f"Deleted file-names collection."
        st.info(text)
        st.session_state.messages.append({"role": role, "info": text})
        title_collection = create_collection(chroma_client, "file-names",model)
        
    if verbose:
        text=(f"Collection file-names created successfully.")
        st.info(text)
        st.session_state.messages.append({"role": role, "info": text})

    # load directory vs load file
    docs = get_docs(file_path,verbose)
    
    collection.add(
        ids=docs["ids"],
        embeddings=docs["embeddings"],
        metadatas=docs["metadatas"],
        documents=docs["documents"]
    )
    
    paths = []
    print(file_path)
    if os.path.isdir(file_path):
        for root, dirs, files in os.walk(file_path):
            for file in files:
                file_path = os.path.join(root, file)
                paths.append(file_path)
                print(file_path)

    title_collection.add(
        ids=paths,
        embeddings=[get_embedding(path) for path in paths]
    ) 
    
    if verbose:
        role = "assistant"
        text = f"Embeddings Added"
        st.info(text)
        st.session_state.messages.append({"role": role, "info": text})
    
    role = "assistant"
    text = f"Database updated"
    st.success(text)
    st.session_state.messages.append({"role": role, "success": text})
    print("Database updated")