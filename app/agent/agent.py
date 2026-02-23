import json
from typing import Annotated, Optional, TypedDict, Sequence
from datetime import datetime

from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from sqlalchemy.orm import Session

from app.config import settings
from app.models.models import Memory


class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]
    conversation_id: str


class AgentTools:
    def __init__(self, db: Session, conversation_id: str):
        self.db = db
        self.conversation_id = conversation_id
    
    def create_tools(self):
        @tool
        def save_memory(memory_type: str, key: str, value: str, metadata: Optional[str] = None) -> str:
            """
            Save important information about the user to memory.
            Use this to store facts about the user, their preferences, or any important details.
            
            Args:
                memory_type: Type of memory (e.g., "user_info", "preference", "fact", "reminder")
                key: A descriptive key for the memory (e.g., "user_name", "favorite_color")
                value: The value to store
                metadata: Optional JSON string with additional context
            """
            memory = Memory(
                conversation_id=self.conversation_id,
                memory_type=memory_type,
                key=key,
                value=value,
                extra_data=json.loads(metadata) if metadata else None
            )
            self.db.add(memory)
            self.db.commit()
            return f"Successfully saved: {key} = {value}"
        
        @tool
        def recall_memories(query: Optional[str] = None, memory_type: Optional[str] = None) -> str:
            """
            Recall stored memories. Can filter by query or memory type.
            
            Args:
                query: Optional search term to filter memories
                memory_type: Optional type filter (e.g., "user_info", "preference")
            """
            query_obj = self.db.query(Memory).filter(Memory.is_active == True)
            
            if memory_type:
                query_obj = query_obj.filter(Memory.memory_type == memory_type)
            
            memories = query_obj.order_by(Memory.created_at.desc()).limit(20).all()
            
            if not memories:
                return "No memories found."
            
            result = "Recalled memories:\n"
            for m in memories:
                result += f"- [{m.memory_type}] {m.key}: {m.value}\n"
            
            return result
        
        @tool
        def update_memory(key: str, new_value: str) -> str:
            """
            Update an existing memory by key.
            
            Args:
                key: The key of the memory to update
                new_value: The new value to set
            """
            memory = self.db.query(Memory).filter(
                Memory.key == key,
                Memory.is_active == True
            ).first()
            
            if not memory:
                return f"No memory found with key: {key}"
            
            memory.value = new_value
            memory.updated_at = datetime.utcnow()
            self.db.commit()
            return f"Updated {key} to: {new_value}"
        
        @tool
        def delete_memory(key: str) -> str:
            """
            Delete a memory by key (soft delete).
            
            Args:
                key: The key of the memory to delete
            """
            memory = self.db.query(Memory).filter(
                Memory.key == key,
                Memory.is_active == True
            ).first()
            
            if not memory:
                return f"No memory found with key: {key}"
            
            memory.is_active = False
            self.db.commit()
            return f"Deleted memory: {key}"
        
        @tool
        def get_current_time() -> str:
            """Get the current date and time."""
            return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
        
        return [save_memory, recall_memories, update_memory, delete_memory, get_current_time]


class Agent:
    def __init__(self, db: Session, conversation_id: str):
        self.db = db
        self.conversation_id = conversation_id
        self.tools_handler = AgentTools(db, conversation_id)
        self.tools = self.tools_handler.create_tools()
        
        self.llm = ChatOpenAI(
            model=settings.OPENROUTER_MODEL,
            temperature=0.7,
            api_key=settings.OPENROUTER_API_KEY,
            base_url="https://openrouter.ai/api/v1",
            default_headers={
                "HTTP-Referer": "https://localhost:8000",
                "X-Title": "AI Agent"
            }
        ).bind_tools(self.tools)
        
        self.graph = self._build_graph()
    
    def _build_graph(self):
        def agent_node(state: AgentState):
            system_prompt = """You are a helpful AI assistant with memory capabilities.

You have access to tools that allow you to:
- save_memory: Store important information about the user
- recall_memories: Retrieve stored information
- update_memory: Update existing memories
- delete_memory: Remove memories
- get_current_time: Get the current date/time

Guidelines:
1. Proactively save important information about the user (name, preferences, goals, etc.)
2. Before responding, recall relevant memories to personalize your responses
3. Keep memories organized with appropriate memory_type values
4. Be helpful, friendly, and conversational
5. Use your tools when appropriate but don't overuse them

Memory types to use:
- "user_info": Personal information (name, age, location, etc.)
- "preference": User preferences and dislikes
- "fact": Important facts the user shares
- "goal": User goals and aspirations
- "reminder": Things to remember for future conversations"""
            
            messages = [SystemMessage(content=system_prompt)] + list(state["messages"])
            response = self.llm.invoke(messages)
            return {"messages": [response]}
        
        def should_continue(state: AgentState):
            messages = state["messages"]
            last_message = messages[-1]
            if hasattr(last_message, "tool_calls") and last_message.tool_calls:
                return "tools"
            return END
        
        workflow = StateGraph(AgentState)
        
        workflow.add_node("agent", agent_node)
        workflow.add_node("tools", ToolNode(self.tools))
        
        workflow.set_entry_point("agent")
        
        workflow.add_conditional_edges(
            "agent",
            should_continue,
            {"tools": "tools", END: END}
        )
        
        workflow.add_edge("tools", "agent")
        
        return workflow.compile()
    
    def invoke(self, messages: list) -> dict:
        return self.graph.invoke({"messages": messages, "conversation_id": self.conversation_id})
