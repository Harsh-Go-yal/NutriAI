from abc import ABC, abstractmethod
from typing import Dict, Any

class BaseAgent(ABC):
    name: str
    model_id: str
    system_prompt: str

    @abstractmethod
    async def run(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute the agent's main logic.
        Must be implemented by all subclasses.
        """
        pass
