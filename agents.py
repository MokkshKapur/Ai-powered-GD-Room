import google.generativeai as genai

# Configure Gemini once
genai.configure(api_key="")  # Replace with your real key

# Load model only once
model = genai.GenerativeModel("gemini-1.5-flash")

# Define your AI agent personas
AGENTS = [
    {"name": "Riya", "persona": "Optimistic tech enthusiast"},
    {"name": "Kabir", "persona": "Balanced economist"},
    {"name": "Anaya", "persona": "Critical social thinker"},
]


# Generate one agent's reply using Gemini
def generate_agent_response(agent, topic, history):
    last_turns = "\n".join(history[-6:])

    prompt = f"""
You are {agent['name']}, a {agent['persona']}.
You are participating in a group discussion on the topic:
"{topic}"

Based on this recent conversation:
{last_turns}

Respond thoughtfully in 2-3 sentences.
"""
    # Call Gemini
    try:
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        return f"(Error generating response: {e})"
