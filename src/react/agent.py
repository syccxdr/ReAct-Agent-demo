from vertexai.generative_models import GenerativeModel 
from src.tools.serp import search as google_search
from src.tools.wiki import search as wiki_search
from vertexai.generative_models import Part 
from src.utils.io import write_to_file
from src.config.logging import logger
from src.config.setup import config
from src.llm.gemini import generate
import os
from src.llm.providers.kimi import KimiClient
from src.utils.io import read_file
from pydantic import BaseModel
from typing import Callable
from pydantic import Field 
from typing import Union
from typing import List 
from typing import Dict 
from enum import Enum
from enum import auto
import json
import time
from src.react.tracer import Tracer


Observation = Union[str, Exception]

PROMPT_TEMPLATE_PATH = "./data/input/react.txt"
OUTPUT_TRACE_PATH = "./data/output/trace.txt"

class Name(Enum):
    """
    Enumeration for tool names available to the agent.
    """
    WIKIPEDIA = auto()
    GOOGLE = auto()
    CALC = auto()
    FILE_READ = auto()
    FILE_WRITE = auto()
    NONE = auto()

    def __str__(self) -> str:
        """
        String representation of the tool name.
        """
        return self.name.lower()


class Choice(BaseModel):
    """
    Represents a choice of tool with a reason for selection.
    """
    name: Name = Field(..., description="The name of the tool chosen.")
    reason: str = Field(..., description="The reason for choosing this tool.")


class Message(BaseModel):
    """
    Represents a message with sender role and content.
    """
    role: str = Field(..., description="The role of the message sender.")
    content: str = Field(..., description="The content of the message.")


class Tool:
    """
    A wrapper class for tools used by the agent, executing a function based on tool type.
    """

    def __init__(self, name: Name, func: Callable[[str], str]):
        """
        Initializes a Tool with a name and an associated function.
        
        Args:
            name (Name): The name of the tool.
            func (Callable[[str], str]): The function associated with the tool.
        """
        self.name = name
        self.func = func

    def use(self, query: str) -> Observation:
        """
        Executes the tool's function with the provided query.

        Args:
            query (str): The input query for the tool.

        Returns:
            Observation: Result of the tool's function or an error message if an exception occurs.
        """
        try:
            return self.func(query)
        except Exception as e:
            logger.error(f"Error executing tool {self.name}: {e}")
            return str(e)


class Agent:
    """
    Defines the agent responsible for executing queries and handling tool interactions.
    """

    def __init__(self, model: GenerativeModel) -> None:
        """
        Initializes the Agent with a generative model, tools dictionary, and a messages log.

        Args:
            model (GenerativeModel): The generative model used by the agent.
        """
        self.model = model
        self.tools: Dict[Name, Tool] = {}
        self.messages: List[Message] = []
        self.query = ""
        self.max_iterations = 5
        self.current_iteration = 0
        self.template = self.load_template()
        # Observability and counters
        self.tracer = Tracer("./data/output/trace.jsonl")
        self.api_calls = 0
        self.token_in = 0
        self.token_out = 0
        self._recent_signatures: List[str] = []

    def load_template(self) -> str:
        """
        Loads the prompt template from a file.

        Returns:
            str: The content of the prompt template file.
        """
        return read_file(PROMPT_TEMPLATE_PATH)

    def register(self, name: Name, func: Callable[[str], str]) -> None:
        """
        Registers a tool to the agent.

        Args:
            name (Name): The name of the tool.
            func (Callable[[str], str]): The function associated with the tool.
        """
        self.tools[name] = Tool(name, func)

    def trace(self, role: str, content: str) -> None:
        """
        Logs the message with the specified role and content and writes to file.

        Args:
            role (str): The role of the message sender.
            content (str): The content of the message.
        """
        if role != "system":
            self.messages.append(Message(role=role, content=content))
        write_to_file(path=OUTPUT_TRACE_PATH, content=f"{role}: {content}\n")

    def get_history(self) -> str:
        """
        Retrieves the conversation history.

        Returns:
            str: Formatted history of messages.
        """
        return "\n".join([f"{message.role}: {message.content}" for message in self.messages])

    def think(self) -> None:
        """
        Processes the current query, decides actions, and iterates until a solution or max iteration limit is reached.
        """
        self.current_iteration += 1
        logger.info(f"Starting iteration {self.current_iteration}")
        write_to_file(path=OUTPUT_TRACE_PATH, content=f"\n{'='*50}\nIteration {self.current_iteration}\n{'='*50}\n")

        if self.current_iteration > self.max_iterations:
            logger.warning("Reached maximum iterations. Stopping.")
            final_msg = "I'm sorry, but I couldn't find a satisfactory answer within the allowed number of iterations. Here's what I know so far: " + self.get_history()
            self.trace("assistant", final_msg)
            self.tracer.finalize(final_msg)
            return

        prompt = self.template.format(
            query=self.query, 
            history=self.get_history(),
            tools=', '.join([str(tool.name) for tool in self.tools.values()])
        )

        self.tracer.start_step("think", {"iteration": self.current_iteration, "prompt_preview": (prompt or "")[:400]})
        response_text, usage = self.ask_model(prompt)
        if usage:
            self.api_calls += 1
            self.token_in += usage.get("token_in", 0)
            self.token_out += usage.get("token_out", 0)
            self.tracer.incr_api(usage.get("token_in", 0), usage.get("token_out", 0))
        else:
            self.api_calls += 1
            self.tracer.incr_api(0, 0)
        self.tracer.end_step("think", {"model_response_preview": str(response_text)[:400]})
        logger.info(f"Thinking => {response_text}")
        self.trace("assistant", f"Thought: {response_text}")
        self.decide(response_text)

    def decide(self, response: str) -> None:
        """
        Processes the agent's response, deciding actions or final answers.

        Args:
            response (str): The response generated by the model.
        """
        try:
            cleaned_response = response.strip().strip('`').strip()
            if cleaned_response.startswith('json'):
                cleaned_response = cleaned_response[4:].strip()
            
            parsed_response = json.loads(cleaned_response)
            self.tracer.log("decide", {"raw": cleaned_response[:800]})
            
            if "action" in parsed_response:
                action = parsed_response["action"]
                tool_name = Name[action["name"].upper()]
                # Loop detection: last 4 signatures low diversity
                sig = f"{tool_name}-{action.get('input','')[:64]}".lower()
                self._recent_signatures.append(sig)
                self._recent_signatures = self._recent_signatures[-4:]
                if len(self._recent_signatures) >= 4 and len(set(self._recent_signatures)) <= 2:
                    self.trace("assistant", "Detected potential loop. Switching to NONE.")
                    self.tracer.log("error", {"kind": "loop_detected", "recent": self._recent_signatures})
                    tool_name = Name.NONE
                if tool_name == Name.NONE:
                    logger.info("No action needed. Proceeding to final answer.")
                    self.think()
                else:
                    self.trace("assistant", f"Action: Using {tool_name} tool")
                    self.tracer.start_step("act", {"tool": str(tool_name), "reason": action.get("reason", "")})
                    self.act(tool_name, action.get("input", self.query))
            elif "answer" in parsed_response:
                self.trace("assistant", f"Final Answer: {parsed_response['answer']}")
                self.tracer.finalize(parsed_response['answer'])
            else:
                raise ValueError("Invalid response format")
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse response: {response}. Error: {str(e)}")
            self.tracer.log("error", {"kind": "json_decode", "msg": str(e)})
            self.trace("assistant", "I encountered an error in processing. Let me try again.")
            self.think()
        except Exception as e:
            logger.error(f"Error processing response: {str(e)}")
            self.tracer.log("error", {"kind": "decide_exception", "msg": str(e)})
            self.trace("assistant", "I encountered an unexpected error. Let me try a different approach.")
            self.think()

    def act(self, tool_name: Name, query: str) -> None:
        """
        Executes the specified tool's function on the query and logs the result.

        Args:
            tool_name (Name): The tool to be used.
            query (str): The query for the tool.
        """
        tool = self.tools.get(tool_name)
        if tool:
            t0 = time.perf_counter()
            result = tool.use(query)
            duration_ms = int((time.perf_counter() - t0) * 1000)
            observation = f"Observation from {tool_name}: {result}"
            self.tracer.end_step("act", {"tool": str(tool_name), "duration_ms": duration_ms, "result_preview": str(result)[:400]})
            self.trace("system", observation)
            self.messages.append(Message(role="system", content=observation))  # Add observation to message history
            self.think()
        else:
            logger.error(f"No tool registered for choice: {tool_name}")
            self.tracer.log("error", {"kind": "tool_not_found", "tool": str(tool_name)})
            self.trace("system", f"Error: Tool {tool_name} not found")
            self.think()

    def execute(self, query: str) -> str:
        """
        Executes the agent's query-processing workflow.

        Args:
            query (str): The query to be processed.

        Returns:
            str: The final answer or last recorded message content.
        """
        self.query = query
        self.trace(role="user", content=query)
        self.think()
        final = self.messages[-1].content
        self.tracer.log("stats", {"api_calls": self.api_calls, "token_in": self.token_in, "token_out": self.token_out})
        return final

    def ask_gemini(self, prompt: str):
        """
        Queries the generative model with a prompt.

        Args:
            prompt (str): The prompt text for the model.

        Returns:
            str: The model's response as a string.
        """
        contents = [Part.from_text(prompt)]
        try:
            response = generate(self.model, contents, return_usage=True)  # type: ignore[arg-type]
            if isinstance(response, tuple):
                text, usage = response
                return (str(text) if text is not None else "No response from Gemini"), usage
            return (str(response) if response is not None else "No response from Gemini"), None
        except TypeError:
            # Fallback to old signature
            response = generate(self.model, contents)
            return (str(response) if response is not None else "No response from Gemini"), None

    def ask_model(self, prompt: str):
        provider = os.getenv("PROVIDER", "gemini").lower()
        if provider == "kimi":
            # Use Kimi client (OpenAI-compatible)
            client = KimiClient()
            text, usage = client.generate(prompt)
            return text or "", usage
        # default gemini
        return self.ask_gemini(prompt)
def run(query: str) -> str:
    """
    Sets up the agent, registers tools, and executes a query.

    Args:
        query (str): The query to execute.

    Returns:
        str: The agent's final answer.
    """
    gemini = GenerativeModel(config.MODEL_NAME)

    from src.tools.basic import calc, file_read, file_write
    agent = Agent(model=gemini)
    agent.register(Name.WIKIPEDIA, wiki_search)
    agent.register(Name.GOOGLE, google_search)
    agent.register(Name.CALC, calc)
    agent.register(Name.FILE_READ, file_read)
    agent.register(Name.FILE_WRITE, file_write)

    answer = agent.execute(query)
    return answer


if __name__ == "__main__":
    query = "What is the age of the oldest tree in the country that has won the most FIFA World Cup titles?"
    final_answer = run(query)
    logger.info(final_answer)
    