import os
import streamlit as st
import openai
from openai import AssistantEventHandler
from typing_extensions import override
import json
from datetime import datetime
from dotenv import load_dotenv

# Initialize the OpenAI client
load_dotenv()
api_key = os.getenv("OPENAI_API_KEY")
client = openai.Client(api_key=api_key)

# Define the assistant ID; create one if it doesn't exist
assistant_id = os.getenv("ASSISTANT_ID")
assistant = client.beta.assistants.retrieve(assistant_id)

def generate_letter(chat_history):
    prompt = f"""
    here is a conversation between a patient and a doctor, write a letter to a doctor summarizing the patients condition 
    and come to a conclusion on what the cause is and what are the further steps:
    :
    {chat_history}
    """

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "You are an AI doctor and you are writing this to another doctor who has medical knowledge. Your task is to carefully analyze patient - doctor interaction and write a diagnosis letter and a conclusion what you think the cause is,  and furthur steps."},
            {"role": "user", "content": prompt}
        ],
        max_tokens=3000  # Increased token limit for more detailed response
    )

    return response.choices[0].message.content.strip()

def end_chat():
    # Retrieve all messages from the thread
    messages = client.beta.threads.messages.list(thread_id=st.session_state.thread_id)

    # Format the chat history
    chat_history = []
    text_history = ""
    for msg in reversed(messages.data):  # messages are returned in reverse chronological order
        content = msg.content[0].text.value if msg.content else ""
        chat_history.append({
            "role": msg.role,
            "content": content
        })
        text_history += f"{msg.role.capitalize()}: {content}\n\n"

    # Create filenames with timestamp
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    json_filename = f"chat_history_{timestamp}.json"
    text_filename = f"letter_{timestamp}.txt"

    letter = generate_letter(text_history)

    # Write the chat history to a JSON file
    with open(json_filename, 'w') as f:
        json.dump(chat_history, f, indent=2)

    # Write the letter to a text file
    with open(text_filename, 'w') as f:
        f.write(letter)

    st.session_state.chat_ended = True
    st.session_state.letter_filename = text_filename
    return f"Chat ended. History exported to {json_filename} and letter exported to {text_filename}"

class EventHandler(AssistantEventHandler):
    @override
    def on_event(self, event):
        if event.event == 'thread.run.requires_action':
            run_id = event.data.id
            self.handle_requires_action(event.data, run_id)

    @override
    def on_text_delta(self, delta, snapshot):
        if delta.value:
            st.session_state.assistant_response += delta.value
        st.session_state.response_container.markdown(st.session_state.assistant_response)

    @override
    def on_text_done(self, text):
        st.session_state.chat_history.append(("assistant", st.session_state.assistant_response))
        if "Chat ended" in st.session_state.assistant_response:
            st.session_state.chat_ended = True
        st.session_state.assistant_response = ""

    def handle_requires_action(self, run, run_id):
        tool_calls = run.required_action.submit_tool_outputs.tool_calls
        tool_outputs = []
        for tool_call in tool_calls:
            if tool_call.function.name == "end_chat":
                output = end_chat()
                tool_outputs.append({"tool_call_id": tool_call.id, "output": output})
                st.session_state.chat_ended = True

        client.beta.threads.runs.submit_tool_outputs(
            thread_id=st.session_state.thread_id,
            run_id=run_id,
            tool_outputs=tool_outputs
        )

# Streamlit session initialization
if 'chat_history' not in st.session_state:
    st.session_state.chat_history = []
if 'assistant_response' not in st.session_state:
    st.session_state.assistant_response = ""
if 'thread_id' not in st.session_state:
    thread = client.beta.threads.create()
    st.session_state.thread_id = thread.id
if 'chat_ended' not in st.session_state:
    st.session_state.chat_ended = False
if 'letter_filename' not in st.session_state:
    st.session_state.letter_filename = None

def display_chat_history():
    for role, content in st.session_state.chat_history:
        with st.chat_message(role):
            st.markdown(content)

st.title("Health AI ChatBot")

# Display chat history
display_chat_history()

# Create a container for the assistant's response
if 'response_container' not in st.session_state:
    st.session_state.response_container = st.empty()

if st.session_state.chat_ended:
    st.info("Chat session has ended. A diagnosis letter has been generated.")
    if st.button("View Generated Letter"):
        if st.session_state.letter_filename and os.path.exists(st.session_state.letter_filename):
            with open(st.session_state.letter_filename, 'r') as file:
                letter_content = file.read()
            st.text_area("Generated Letter", letter_content, height=300)
        else:
            st.error("Letter file not found.")
    if st.button("Start New Conversation"):
        # Reset the session state for a new conversation
        st.session_state.chat_history = []
        st.session_state.assistant_response = ""
        thread = client.beta.threads.create()
        st.session_state.thread_id = thread.id
        st.session_state.chat_ended = False
        st.session_state.letter_filename = None
        st.rerun()
else:
    # User input
    if prompt := st.chat_input("Enter your message"):
        # Add user message to chat history and display it
        st.session_state.chat_history.append(("user", prompt))
        with st.chat_message("user"):
            st.markdown(prompt)

        # Send message to assistant
        client.beta.threads.messages.create(
            thread_id=st.session_state.thread_id,
            role="user",
            content=prompt
        )

        # Stream the assistant's response
        with st.chat_message("assistant"):
            st.session_state.response_container = st.empty()
            with client.beta.threads.runs.stream(
                    thread_id=st.session_state.thread_id,
                    assistant_id=assistant.id,
                    event_handler=EventHandler(),
                    temperature=0
            ) as stream:
                stream.until_done()

        # Check if the chat has ended
        if "Chat ended" in st.session_state.assistant_response:
            st.session_state.chat_ended = True
            st.info("Chat session has ended. A diagnosis letter has been generated.")

        # Rerun the app to update the chat history display
        st.rerun()