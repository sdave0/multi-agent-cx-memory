import os
import yaml
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_anthropic import ChatAnthropic
from langchain_openai import ChatOpenAI
from dotenv import load_dotenv
from backend.logger import get_logger

logger = get_logger("llm.client_factory")

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config', '.env'))

# Ensure GOOGLE_API_KEY is set if GEMINI_API_KEY is present
if not os.environ.get("GOOGLE_API_KEY") and os.environ.get("GEMINI_API_KEY"):
    os.environ["GOOGLE_API_KEY"] = os.environ.get("GEMINI_API_KEY")
    logger.info("Mapped GEMINI_API_KEY to GOOGLE_API_KEY.")

class LLMClientFactory:
    def __init__(self):
        config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config', 'llm_config.yaml')
        try:
            with open(config_path, 'r') as f:
                self.config = yaml.safe_load(f)
            if not self.config:
                logger.warning(f"Config file {config_path} loaded but is empty. Using defaults.")
                self.config = {}
        except FileNotFoundError:
            logger.error(f"Configuration file not found: {config_path}")
            self.config = {}
        except yaml.YAMLError as e:
            logger.error(f"Error parsing YAML configuration file: {e}")
            self.config = {}
        except Exception as e:
            logger.error(f"Unexpected error loading configuration: {e}", exc_info=True)
            self.config = {}
            
        self.provider = self.config.get('provider', 'gemini')
        self._client_cache = {}
        
        # Pre-warm common clients
        if self.config.get('pre_warm', True):
            try:
                self.get_client("concierge")
                self.get_client("tech_specialist")
                logger.info("LLM clients pre-warmed (Concierge & Tech Specialist).")
            except Exception as e:
                logger.warning(f"Failed to pre-warm LLM clients: {e}")

    def get_client(self, agent_role: str):
        if agent_role in self._client_cache:
            return self._client_cache[agent_role]

        model_name = self.config.get('models', {}).get(agent_role)
        if not model_name:
            logger.error(f"No model configured for role: {agent_role}")
            raise ValueError(f"No model configured for role: {agent_role}")

        try:
            client = None
            # Standardizing streaming and tagging for all providers
            common_params = {"temperature": 0.0, "streaming": True, "tags": [agent_role]}
            
            if self.provider == 'gemini':
                client = ChatGoogleGenerativeAI(model=model_name, **common_params)
            elif self.provider == 'anthropic':
                # ChatAnthropic uses different param names sometimes, but streaming=True is standard
                client = ChatAnthropic(model_name=model_name, temperature=0.0, streaming=True, tags=[agent_role])
            elif self.provider == 'openai':
                client = ChatOpenAI(model=model_name, **common_params)
            else:
                logger.error(f"Unsupported provider: {self.provider}")
                raise ValueError(f"Unsupported provider: {self.provider}")
            
            self._client_cache[agent_role] = client
            return client
        except Exception as e:
            logger.error(f"Failed to initialize LLM client for role {agent_role} with provider {self.provider}: {e}", exc_info=True)
            raise

    def get_token_limits(self):
        return self.config.get('token_limits', {})

    def get_call_delay(self) -> float:
        return self.config.get('call_delay_seconds', 0.0)
