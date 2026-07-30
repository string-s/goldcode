"""Provider-neutral LLM adapters used outside the real-time decision loop."""

import json
import os
import shlex
import subprocess
import urllib.request


class CommandProvider:
    def __init__(self, command, timeout=30):
        self.command = shlex.split(command)
        self.timeout = timeout

    def propose(self, prompt):
        result = subprocess.run(
            self.command,
            input=prompt,
            text=True,
            capture_output=True,
            timeout=self.timeout,
            check=True,
        )
        return result.stdout


class OpenAICompatibleProvider:
    def __init__(self, api_key, model, base_url, timeout=30):
        self.api_key = api_key
        self.model = model
        self.url = base_url.rstrip("/") + "/chat/completions"
        self.timeout = timeout

    def propose(self, prompt):
        payload = json.dumps({
            "model": self.model,
            "temperature": 0,
            "max_tokens": 300,
            "messages": [
                {"role": "system", "content": (
                    "You optimise a game strategy using evidence. Return only a JSON object "
                    "containing approved numeric parameter overrides. Never return code.")},
                {"role": "user", "content": prompt},
            ],
        }).encode("utf-8")
        request = urllib.request.Request(
            self.url,
            data=payload,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            body = json.loads(response.read().decode("utf-8"))
        return body["choices"][0]["message"]["content"]


def provider_from_env():
    command = os.environ.get("WOLF_LLM_COMMAND")
    if command:
        return CommandProvider(command)
    api_key = os.environ.get("WOLF_LLM_API_KEY")
    model = os.environ.get("WOLF_LLM_MODEL")
    if api_key and model:
        return OpenAICompatibleProvider(
            api_key=api_key,
            model=model,
            base_url=os.environ.get("WOLF_LLM_BASE_URL", "https://api.openai.com/v1"),
            timeout=float(os.environ.get("WOLF_LLM_TIMEOUT_SECONDS", "30")),
        )
    return None
