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
import gc



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
model = OpenAIEmbeddings(model="text-embedding-3-small")

def qa(q,verbose,persist_directory=settings["vs_path"],avatar={"system": '📢',"user": '🧑',"assistant": '🤖'},role="assistant",temp_file_path=None):
    vectorstoredb = Chroma(persist_directory=persist_directory,embedding_function=model)

    if not verbose:
        warnings.filterwarnings("ignore")
    # Full path to the log file
    current_timestamp = datetime.now()

    # Format the timestamp to be friendly for Windows file names
    process_id = current_timestamp.strftime("%Y-%m-%d_%H-%M")

    def log_chat(process_id,string):
        log_chat = settings["chat_path"]
        # Ensure the directory exists
        if not os.path.exists(log_chat):
            os.makedirs(log_chat)
            if verbose:
                text = f"\n\nDirectory '{log_chat}' created."
                st.info(text)
                st.session_state.messages.append({"role": role, "info": text})
        
        file_path = os.path.join(log_chat,process_id + ".txt")

        # Check if the file exists
        if not os.path.exists(file_path):
            # Create the chat txt file
            with open(file_path, 'w') as file:
                file.write("")

        with open(file_path, 'a', errors="ignore") as file:
            file.write(string + "\n")  # Add a new line after the text
        return None

    log_chat(process_id,q)

    # Load data
    root = settings["kb_root_path"]

    # Post-processing
    def context_docs(docs):
        return "\n\n".join(doc.page_content for doc in docs)
    def source_docs(docs):
        return "\n\n".join(f"{doc.metadata["source"]}:\n" + doc.page_content for doc in docs)

    # Helper functions
    def log_api_call(process_id,query,model,system_prompt,user_prompt,response):
        log_path = settings["log_path"]
        # Ensure the directory exists
        if not os.path.exists(log_path):
            os.makedirs(log_path)
            if verbose:
                text = f"Directory '{log_path}' created."
                st.info(text)
                st.session_state.messages.append({"role": role, "info": text})

        
        file_path = os.path.join(log_path,process_id + ".txt")

        # Check if the file exists
        if not os.path.exists(file_path):
            # Create the log.txt file
            with open(file_path, 'w') as file:
                file.write("")

        with open(file_path, 'a', errors="ignore") as file:
            file.write(
                "\n".join([
                    "Query: " + str(query), 
                    "Model: " + str(model), 
                    "System prompt: " + str(system_prompt), 
                    "User prompt: " + str(user_prompt), 
                    "Response: " + str(response)
                ]) + "\n\n"
            )  # Add a new line after the text
        return None

    # Query ROUTING
    ## Returns JSON dictionary with question relationships
    # 
    def get_questions(query):
        questions = ""
        model = "gpt-4o"
        system_prompt = """You are a question categorization machine. You'll receive a prompt and you have to identify
    how to split it in questions/actions with the following categories (and id's):
        Email/Attachment search (0),
        Calendar/Appointment search (1),
        File/Directory search (2),
        List file/folder names inside found directory (3),
        Print entire file contents without modifications to console (4),
        Play Video (5),
        Show image (6),
        Play audio (7),
        Question about specific knowledge from the file(8),
        Questions from online source (9),
        Questions without specified online source nor file source (10),
        Open local html file (11),
        Print subset data of file contents to console (12),        
        
    Your answer must be an array in JSON format containing for each question/action the attributes: "question", "question_id", "category", "category_id", "input_from", "output_to".
        "question_id" is an increment by 1 id starting at 0.
        "output_to" and "input_from" are a single integer that refers to "question_id" or null if they don't refer to any question id.
        Questions from these categories cant have a null "input_from":
            "List file/folder names inside found directory",
            "Print to console",
            "Question about specific knowledge from the file"
    You'll split the prompt into question/action such that there are no duplicate "question".
    The questions with following categories must take input from a "File/Directory search" question. So make sure to create a "File/Directory search" type question as input source for questions with these categories:
        List file/folder names inside found directory (3),
        Print entire file contents without modifications to console (4),
        Question about specific knowledge from the file(8),
        Print subset data of file contents to console (12),
        Play Video (5),
        Show image (6),
        Play audio (7),
        Open local html file (11),
    For "Questions from online source" (9), keep any mentioned online source in the question text.
    Keep the original language used in the question.
    """
        user_prompt = f"Prompt: {query}"
        try:
            client = OpenAI()

            response = client.chat.completions.create(
            model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ]
            )

            result = response.choices[0].message.content
            log_api_call(process_id,query,model,system_prompt,user_prompt,result)
        except Exception as e:
            if verbose:
                text = f"An error occurred at {inspect.currentframe().f_code.co_name} with query: {query}"
                st.exception(e)
                st.error(text)
                st.session_state.messages.append({"role": role, "error": text, "exception":e})

        return json.loads(result.replace("```json","").replace("```",""))

    # Takes a question string and returns a question string rewritten
    def clean_question(query):
        result = query
        model = "gpt-4o-mini"
        system_prompt = """You are a question formatting machine for a Q&A RAG application.
        You will take a prompt input and you need to output only the essence of the question,
            simplifying it as much as possible and ignoring any context from the prompt that may affect the similarity score of the output answer for the retrieval of document information.
    """
        user_prompt = f"Question: {query}"
        try:
            client = OpenAI()

            response = client.chat.completions.create(
            model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ]
            )

            result = response.choices[0].message.content
            log_api_call(process_id,query,model,system_prompt,user_prompt,result)
        except Exception as e:
            if verbose:
                
                text = f"An error occurred at {inspect.currentframe().f_code.co_name} with query: {query}"
                
                st.exception(e)
                st.error(text)
                st.session_state.messages.append({"role": role, "error": text, "exception":e})

                    
        return result

    # Takes a string or a list of strings supposedly containing paths and returns a list of paths that exist (in the entire system)
    def clean_path(question,input):
        
        result = "0"
        paths = []
        model = "gpt-4o-mini"
        system_prompt = f"""You are a path finder machine.
    Find the paths relevant to the user prompt. Your answer must only contain the paths separated by "?".
    If there are no paths, just reply with "0"."""
        user_prompt = f"User prompt: {question + "\n" + str(input).replace("\\\\","/")}"
        
        try:
            client = OpenAI()

            response = client.chat.completions.create(
            model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ]
            )

            result = response.choices[0].message.content
            log_api_call(process_id,question,model,system_prompt,user_prompt,result)
        except Exception as e:
            if verbose:
                
                text = f"An error occurred at {inspect.currentframe().f_code.co_name} with query: {query}"
                
                st.exception(e)
                st.error(text)
                st.session_state.messages.append({"role": role, "error": text, "exception":e})
                    
        
        if result == "0": return []
        else:
            for path in result.split("?"):
                if os.path.exists(path):
                    paths.append(path)
        return paths

    # Question PROCESSING
    ## Category 2 File/Directory Search: Returns lists of paths inside knowledge base root
    def get_relevant_file_or_directory(query,root):
        # Returns all paths from root directory that will be passed as context
        def list_all_files_and_dirs(root):
            result = [root]
            
            for dirpath, dirnames, filenames in os.walk(root):
                # Append the directory itself
                result.append(dirpath)
                
                # Append all files in the current directory
                for filename in filenames:
                    result.append(os.path.join(dirpath, filename))
                
                if not dirnames and not filenames:
                    result.append(dirpath)
            
            return result
        paths = ""
        model = "gpt-4o-mini"
        system_prompt = f"""You are a path finder machine.
    From the list of paths provided, find the requested file or folder paths according to the question. 
    Your answer must only contain the relevant paths separated by "?".
    Paths: {str(list_all_files_and_dirs(root)).replace("\\\\","/")}"""
        user_prompt = f"Question: {query}"
        try:
            client = OpenAI()

            response = client.chat.completions.create(
            model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ]
            )

            result = response.choices[0].message.content
            log_api_call(process_id,query,model,system_prompt,user_prompt,result)
        except Exception as e:
            if verbose:
                
                text = f"An error occurred at {inspect.currentframe().f_code.co_name} with query: {query}"
                
                st.exception(e)
                st.error(text)
                st.session_state.messages.append({"role": role, "error": text, "exception":e})
                    
        return result.split("?")

    ## Category 3 Read directory contents
    def read_directory(query,path):

        if os.path.exists(path):    
            if os.path.isdir(path):    
                result = ""
                dirs = []
                files = []

                for item in os.listdir(path):
                    item_path = os.path.join(path, item)
                    if os.path.isdir(item_path):
                        dirs.append(item)
                    else:
                        files.append(item)
                for dir in dirs:
                    result += dir + "\n"
                for file in files:
                    result += file + "\n"
            else:
                result = path + "\n"
        else:
            result = path
            
        log_api_call(process_id,query,"os",f'for item in os.listdir({path})','print',result)
        return result

    ## Category 4 Read file from path... Use words[:500]  to get top 500 words for summary
    def read_file(query,input):
        result = ""
        if os.path.exists(input):
            with open(input, "r", errors="ignore") as file:
            # Reading from a file
                result = file.read()[:500]
        else:
            result = input
        log_api_call(process_id,query,"os",f'with open("{input}", "r", errors="ignore")','file.read()[:500]',result)
        return result
    
    ## Category 5 Play video
    def play_video(query,input):
        extension = input.split(".")[-1]
        recognized_extensions = ["mp4", "ogg", "webm"]
        if extension in recognized_extensions:
            try:
                st.video(input)
                st.session_state.messages.append({"role": role, "video": input})
            except Exception as e:
                st.exception(e)
            log_api_call(process_id,query,"os",f'st.video("{input}")','st.video',input)
        else:
            text = f"""{input} does not have recognized video extension ({extension}).
            The recognized extensions are: {", ".join(recognized_extensions)}."""
            st.warning(text)
            st.session_state.messages.append({"role": role, "warning": text})
        return input
    
        ## Category 6 show image
    def show_image(query,input):
        extension = input.split(".")[-1]
        recognized_extensions = [  "jpg",
                                "jpeg", 
                                "png", 
                                "gif", 
                                "bmp", 
                                "tiff", ".tif", 
                                "webp", 
                                "svg", 
                                "heic", ".heif", 
                                "raw", 
                                "ico"]
        if extension in recognized_extensions:
            try:
                st.image(input,use_column_width=True)
                st.session_state.messages.append({"role": role, "image": input})
            except Exception as e:
                st.exception(e)
            log_api_call(process_id,query,"os",f'st.image("{input}")','st.image',input)
        else:
            text = f"""{input} does not have recognized image extension ({extension}).
            The recognized extensions are: {", ".join(recognized_extensions)}."""
            st.warning(text)
            st.session_state.messages.append({"role": role, "warning": text})
        return input
    ## Category 7 Play audio
    def play_audio(query,input):
        extension = input.split(".")[-1]
        recognized_extensions = ["wav", "mp3", "ogg"]
        if extension in recognized_extensions:
            try:
                st.audio(input)
                st.session_state.messages.append({"role": role, "audio": input})
            except Exception as e:
                st.exception(e)
            log_api_call(process_id,query,"os",f'st.audio("{input}")','st.audio',input)
        else:
            text = f"""{input} does not have recognized audio extension ({extension}).
            The recognized extensions are: {", ".join(recognized_extensions)}."""
            st.warning(text)
            st.session_state.messages.append({"role": role, "warning": text})
        return input
    
    ## Category 5 Play video
    def open_html(query,input):
        extension = input.split(".")[-1]
        recognized_extensions = ["htm","html"]
        if extension in recognized_extensions:
            try:
                # Read the HTML file
                with open(input, 'r', encoding='utf-8') as file:
                    html_content = file.read()

                # Display the HTML content in Streamlit
                st.components.v1.html(html_content, height=600, scrolling=True)
                st.session_state.messages.append({"role": role, "html": input})
            except Exception as e:
                st.exception(e)
            log_api_call(process_id,query,"os",f'with open("{input}")','open html',input)
        else:
            text = f"""{input} does not have recognized html extension ({extension}).
            The recognized extensions are: {", ".join(recognized_extensions)}."""
            st.warning(text)
            st.session_state.messages.append({"role": role, "warning": text})
        return input
    
    ## Category 7 Summarize file
    def summarize_file(query,path):

        file_contents = read_file(query,path) # In case of no file the context is returned
        model = "gpt-4o-mini"
        system_prompt = f"""Summarize the contents of the file as concesiely as possible or as specified in the context."""
        user_prompt = f"Context: {query}\nFile contents: {file_contents}"
        try:
            client = OpenAI()

            response = client.chat.completions.create(
            model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ]
            )

            result = response.choices[0].message.content
            log_api_call(process_id,query,model,system_prompt,user_prompt,result)
        except Exception as e:
            if verbose:
                
                text = f"An error occurred at {inspect.currentframe().f_code.co_name} with query: {query}"
                
                st.exception(e)
                st.error(text)
                st.session_state.messages.append({"role": role, "error": text, "exception":e})
                    
        return result

    ## Category 0 Search Emails
    def search_email(query,input):

        if input is not None:
            query =  query + "\nContext: " + input

        output = sqlquery(query)
        return output

    # Category 8 or 12 filter RAG with path file
    def knowledge_from_file(query,path):

        header = ""
        context = str(path) # is not a path but a string input

        if isinstance(path,str):
            extension = path.split('.')[-1]
        else:
            extension = "",
        # Clean query and clean path has to be done outside, because im probably gonna append the contents of the path that are not paths to the query and keep the paths variable just for paths
        
        

        if extension == "csv":
            
            with open(path, "r") as file:
            # Reading from a file
                header = file.readline()
            system_prompt = f"""Answer the question about the contents of the CSV file with the following header: {header}"""
            # substitute retireved_docs with sql upload and sql agent
            retrieved_docs = vectorstoredb.similarity_search(query,k=3,filter={'source':str(path).replace("./","").replace("/","\\")})
            
        else:
            system_prompt = f"""Answer the question about the contents of the file. Don't use outside information.
        If the path or the context from the file are empty say "Couldn't match any info based on your query. Try to type your query differently".
        Be as concise as possible and use the language used in the question."""

            retriever = vectorstoredb.as_retriever(
                search_type="similarity_score_threshold",
                search_kwargs={'score_threshold': 0.01,
                            "k":3,
                            'filter': {'source':str(path).replace("./","").replace("/","\\")}})
            
            retrieved_docs = retriever.invoke(query)

        context = context_docs(retrieved_docs)
        if len(context) == 0:
            context = str(path)
            
            text = f"Warning: Context file \"{path[:100]}\" couldn't match any info based on your query. Try to type your query differently."
            st.warning(text)
            st.session_state.messages.append({"role": role, "warning": text})
        
        model = "gpt-4o-mini"

        user_prompt = f"Question: {query}\nContents: {context}"
        try:
            client = OpenAI()

            response = client.chat.completions.create(
            model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ]
            )

            result = response.choices[0].message.content
            log_api_call(process_id,query,model,system_prompt,user_prompt,result)
        except Exception as e:
            if verbose:
                
                text = f"An error occurred at {inspect.currentframe().f_code.co_name} with query: {query}"
                
                st.exception(e)
                st.error(text)
                st.session_state.messages.append({"role": role, "error": text, "exception":e})
                    
        return result

    ## Category 9 online source 
    def knowledge_from_online_source(query,path):

        #query = clean_question(query)

        model = "gpt-4o-mini" #check this
        system_prompt = f"""Answer the question using, if specified, the online source.
        The answer must include at the end the online source(s) used for the answer.
        The answer and the source paraghs must not come with any further explanation, be as concise as possible.
        Keep the original language used in the question."""
        user_prompt = f"Question: {query}"
        try:
            client = OpenAI()

            response = client.chat.completions.create(
            model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ]
            )

            result = response.choices[0].message.content
            log_api_call(process_id,query,model,system_prompt,user_prompt,result)
        except Exception as e:
            if verbose:
                
                text = f"An error occurred at {inspect.currentframe().f_code.co_name} with query: {query}"
                
                st.exception(e)
                st.error(text)
                st.session_state.messages.append({"role": role, "error": text, "exception":e})
                    
        return result

    # Category 10 unspecified source
    def knowledge_from_online_source_or_all_files(query,input):
        
        query = clean_question(query)

        # Instead of json the context must include a source path and ask chat gpt to return the source path used or "gpt kb"
        system_prompt = f"""Answer the question using the context info. If the context info is not enough to provide an answer, you can use other sources of information.
        The answer must include at the end the file path or online source(s) of the context used for the answer. The answer and the source paraghs must not come with any further explanation, be as concise as possible.
        """
        if input is not None:
            context_with_source = input
        else:
            retriever = vectorstoredb.as_retriever(
                search_type="similarity_score_threshold",
                search_kwargs={'score_threshold': 0.01,
                            "k":5}
                            )
            
            retrieved_docs = retriever.invoke(query)
            context_with_source = source_docs(retrieved_docs) #with source version
            
        model = "gpt-4o-mini" # Check this

        user_prompt = f"Question: {query}\nContext:\n{context_with_source}"
        try:
            client = OpenAI()

            response = client.chat.completions.create(
            model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ]
            )

            result = response.choices[0].message.content
            log_api_call(process_id,query,model,system_prompt,user_prompt,result)
        except Exception as e:
            if verbose:
                
                text = f"An error occurred at {inspect.currentframe().f_code.co_name} with query: {query}"
                
                st.exception(e)
                st.error(text)
                st.session_state.messages.append({"role": role, "error": text, "exception":e})
                    
        return result

    # SQL statement generation must always search for the schema tables first relevants to the query

    def query_path_loop_category_execution_helper(query,func):
        # Query path loop will always output str in the loop, it may not do it in the first assignment
        query["output"]  = ""

        #query is pass by reference so assigning query["output"] will be reflected outside the function
        # paths might be paths or context info already appended to the query, so we just check for existing paths

        # If input is not a path but actual context, it's already been added to the query as context.
        # But it wouldn't execute the path loop, so we execute it independently for a single instance.
        if isinstance(query["input"], str):
            if os.path.exists(query["input"]):
                # paths is a single path (rare, this shouldnt happen)
                query["output"] = func(query["question"],query["input"])
                return query["output"]
                
            else:
                paths = clean_path(query["question"],query["input"])
                if len(paths) > 0:
                    query["input"] = paths
                else:
                    # it's not a path, but it is a string, so just use it as context
                    query["output"] = func(query["question"],query["input"])
                
        if isinstance(query["input"],list):
            for path in query["input"]:
                
                if os.path.exists(path):
                    
                    if os.path.isdir(path) and func.__name__ != "read_directory":
                        
                        # Iterate over all files in the directory
                        for entry in os.listdir(path):
                            entry_path = os.path.join(path, entry)
                            
                            # Check if it is a file (and not a directory)
                            if os.path.isfile(entry_path):
                                query["output"] += "\n" + entry_path + ":\n" + func(query["question"],entry_path) + "\n"
                            if os.path.isdir(entry_path):
                                query["output"] += entry_path + "\n"
                    else:
                        # It's a single file or it's read_dir (which can take either file or directory)
                        query["output"] += "\n" + path + ":\n" + func(query["question"],path)
                else:
                    # It's not a file so it must be context
                    query["output"] += func(query["question"] + "\nInput Context: " + path,"")
                query["output"] += "\n"
        
        if query["input"] is None:
            query["output"] += func(query["question"],query["input"])
        if query["output"] == "":
            query["output"] == query["input"] # in case of failure just forward input
        return query["output"]
        # Outputs string

    if temp_file_path is not None:
        query = {}
        # Knowledge from file
        query["question"]=q
        query["input"]=temp_file_path
        
        result = knowledge_from_file(q,temp_file_path)
    
        yield "\n\n" + result.replace("\n","\n\n")
        log_chat(process_id,result)
        if verbose: yield "\n\n```json\n" + str(query) + "\n```\n\n"
        return
    else:
        print("No file path",temp_file_path) 
        st.write()
    
    questions = get_questions(q)
    image_name = q + process_id
    image_name = image_name[:50]
    if verbose:
        image_path = generate_graph(questions,image_name)
        st.image(image_path)
        st.session_state.messages.append({"role": role, "image": image_path})
        
    ## Loop through all subquestions
    for query in questions:
        query["output"] = None
        query["output_type"] = None
        query["input"] = None
        query["input_type"] = None

    for query in questions:
        if query["input_from"] is not None:
            query["input"] = questions[query["input_from"]]["output"]
            query["input_type"] = questions[query["input_from"]]["output_type"]

        # File/Directory search
        if query["category_id"] == 2:
            if query["input_from"] is not None:
                if isinstance(query["input"], str) or isinstance(query["input"], list):
                    if os.path.exists(str(query["input"])):
                        query["output"] = [query["input"]]
                    else:
                        paths = clean_path(query["question"],query["input"])
                        if len(paths) > 0:
                            query["output"] = paths
                        else:
                            # it's not a path, but it is a string, so just forward it
                            query["output"] = str(query["input"])
            else:
                query["output"] = get_relevant_file_or_directory(query["question"],root)
            if query["output_to"] is None:
                for path in query["output"]:
                    """printlist.append({
                        "content":path
                        ,"role":"assistant"
                        })"""
                    yield "\n\n" + path + "\n"
                    log_chat(process_id,path)
                    # Outputs List of paths only when it's a standalone question
            

        # Search email
        if query["category_id"] in (0,1): 
            output = search_email(query["question"],query["input"])
            query["output"] = "\n\n".join(output)
            if query["output_to"] is None:
                # Create DataFrame from rows and column names
                for csv_string in output:
                    csv_data = StringIO(csv_string)
                    df = pd.read_csv(csv_data)
                    st.write(df)
                    st.session_state.messages.append({"role": role, "df": df})
                    log_chat(process_id,csv_string)

        # Read directory
        if query["category_id"] == 3:
            if query["input"] is None:
                query["input"] = get_relevant_file_or_directory(query["question"],root)
                query["input_type"] = type(query["input"]).__name__

            result = query_path_loop_category_execution_helper(query,read_directory)
                
            if query["output_to"] is None:
                yield "\n\n" + result.replace("\n","\n\n")
                log_chat(process_id,result)

        # Read content from file or context
        if query["category_id"] == 4: 
            result = query_path_loop_category_execution_helper(query,read_file)
            if query["output_to"] is None:
                """printlist.append({
                        "content":result
                        ,"role":"assistant"
                        })"""
                yield "\n\n" + result.replace("\n","\n\n")
                log_chat(process_id,result)

        if query["category_id"] == 5: 
            query_path_loop_category_execution_helper(query,play_video)

        if query["category_id"] == 6: 
            query_path_loop_category_execution_helper(query,show_image)

        if query["category_id"] == 7: 
            query_path_loop_category_execution_helper(query,play_audio)

        if query["category_id"] == 11: 
            query_path_loop_category_execution_helper(query,open_html)
            
        
        # Summarize file
        if query["category_id"] == 7:
            result = query_path_loop_category_execution_helper(query,summarize_file)
            if query["output_to"] is None:
                """printlist.append({
                        "content":result
                        ,"role":"assistant"
                        })"""
                yield "\n\n" + result.replace("\n","\n\n")
                log_chat(process_id,result)

        # Knowledge from file
        if query["category_id"] in (8,12):
            result = query_path_loop_category_execution_helper(query,knowledge_from_file)
            if query["output_to"] is None:
                """printlist.append({
                        "content":result
                        ,"role":"assistant"
                        })"""
                yield "\n\n" + result.replace("\n","\n\n")
                log_chat(process_id,result)

        # Knowledge from online source
        if query["category_id"] == 9:
            result = query_path_loop_category_execution_helper(query,knowledge_from_online_source)
            if query["output_to"] is None:
                """printlist.append({
                        "content":result
                        ,"role":"assistant"
                        })"""
                yield "\n\n" + result.replace("\n","\n\n")
                log_chat(process_id,result)

        # Knowledge from rag or online
        if query["category_id"] == 10:
            result = query_path_loop_category_execution_helper(query,knowledge_from_online_source_or_all_files)
            if query["output_to"] is None:
                """printlist.append({
                        "content":result
                        ,"role":"assistant"
                        })"""
                yield "\n\n" + result.replace("\n","\n\n")
                log_chat(process_id,result)

        query["output_type"] = type(query["output"]).__name__
        if(verbose):
            """printlist.append({
                        "json":query
                        ,"role":"system"
                        })"""
            yield "\n\n```json\n" + str(query) + "\n```\n\n"

def get_answer(prompt,verbose,persist_directory=settings["vs_path"],avatar={"system": '📢',"user": '🧑',"assistant": '🤖'},role="assistant",temp_file_path=None):

    role = "assistant"
    with st.chat_message("assistant",avatar=avatar.get("assistant")):
        response = st.write_stream(qa(prompt,verbose,persist_directory,avatar=avatar,temp_file_path=temp_file_path))
        st.session_state.messages.append({"role": role, "content": response})
    gc.collect()