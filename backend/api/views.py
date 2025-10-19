from django.shortcuts import render

# Create your views here.
from rest_framework.views import APIView
from rest_framework.response import Response

class HelloView(APIView):
    def get(self, request):
        return Response({"message": "Hello from Django!"})

# import os
# from groq import Groq
# from dotenv import load_dotenv

# load_dotenv(dotenv_path=".env")
# client = Groq(api_key=os.getenv("GROQ_API_KEY"))

# class ChatbotView(APIView):
#     def post(self, request):
#         user_message = request.data.get("message", "")
#         if not user_message:
#             return Response({"error": "No message provided"}, status=400)

#         completion = client.chat.completions.create(
#             model="openai/gpt-oss-120b",
#             messages=[
#                 {"role": "system", "content": "You are a helpful assistant."},
#                 {"role": "user", "content": user_message},
#             ],
#         )

#         reply = completion.choices[0].message.content
#         return Response({"reply": reply})


import os
import json
import datetime
from dotenv import load_dotenv
from rest_framework.views import APIView
from rest_framework.response import Response

import re
from prompts.flows import get_prompt_for_flow
from chat.router import maybe_parse_tool_call, execute_tool

from google import genai
from google.genai import types

load_dotenv(dotenv_path=".env")

client = genai.Client()

def convert_to_gemini_contents(messages):
    contents = []
    for m in messages:
        role = m["role"]
        if role == "assistant":
            role = "model"
        contents.append(
            types.Content(
                role=role,
                parts=[types.Part(text=m["content"])]
            )
        )
    return contents

class ChatbotView(APIView):
    def post(self, request):
        data = request.data
        flow = data.get("flow", "general_info")
        messages = data.get("messages", [])
        #--------------------------------------------------------
        # If conversation just started, show the menu deterministically
        #--------------------------------------------------------
        if not messages:
            menu = (
                "Hi, this is DentalBot, your virtual assistant! How can I help today?\n"
                "1) Book appointment\n"
                "2) Change appointment\n"
                "3) General inquiry\n"
            )
            return Response({"reply": menu})
        #--------------------------------------------------------
        system_prompt = get_prompt_for_flow(flow)

        completion = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=convert_to_gemini_contents(messages),
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=0.1,
                top_p=0.9,
                max_output_tokens=400,
            ),
        )
        assistant_text = completion.text

        # collect all assistant messages (chain-of-thought / intermediate replies)
        assistant_chain = [assistant_text]

        # Chain of Thought loop
        while True:
            print("Assistant reply:", assistant_text)
            tool_req = maybe_parse_tool_call(assistant_text)
            print("Tool Chain:", tool_req)
            if not tool_req:
                break

            system_prompt = get_prompt_for_flow(tool_req["tool"])
            tool_result = execute_tool(tool_req["tool"], tool_req["parameters"])
            print("Tool result:", tool_result)

            tool_result_json = json.dumps(
                tool_result,
                default=lambda o: o.isoformat() if isinstance(o, (datetime.date, datetime.datetime)) else str(o),
            )

            messages = messages + [
                {"role": "assistant", "content": assistant_text},
                {"role": "user", "content": f"TOOL_RESULT: {tool_result_json}"},
            ]

            followup = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=convert_to_gemini_contents(messages),
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    temperature=0.1,
                    top_p=0.9,
                    max_output_tokens=1000,
                ),
            )

            assistant_text = followup.text
            assistant_chain.append(assistant_text)

        return Response({
            "reply": assistant_text,
            "assistant_chain": [{"role": "assistant", "content": t} for t in assistant_chain],
            "messages": messages,
        })
