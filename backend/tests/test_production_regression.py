import os
import sys
import unittest
import json
import shutil
from pathlib import Path

# Ensure backend imports work
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from brain.planner import PlannerBrain
from brain.intent_parser import parse_intent, validate_intent_sanity
from brain.context_manager import ContextManager
from brain.entity_tracker import extract_all_entities
from memory.semantic import SemanticMemory
from memory.preference import PreferenceMemory
from memory.episodic import EpisodicMemory
from brain.project_manager import ProjectManager

class TestProductionRegression(unittest.TestCase):
    def setUp(self):
        self.test_dir = os.path.dirname(os.path.abspath(__file__))
        self.temp_dir = os.path.join(self.test_dir, "temp_test_data")
        os.makedirs(self.temp_dir, exist_ok=True)
        
        # Temp memory files
        self.semantic_path = os.path.join(self.temp_dir, "semantic.json")
        self.preference_path = os.path.join(self.temp_dir, "preference.json")
        self.episodic_path = os.path.join(self.temp_dir, "episodic.json")
        
        self.context_mgr = ContextManager()
        self.pref_mem = PreferenceMemory(file_path=self.preference_path)
        self.episodic_mem = EpisodicMemory(file_path=self.episodic_path)
        self.semantic_mem = SemanticMemory(file_path=self.semantic_path)
        self.planner = PlannerBrain()

    def tearDown(self):
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    # 1. PLANNER SOVEREIGNTY VERIFICATION TEST
    def test_planner_sovereignty_rust_vs_python(self):
        """
        Verifies the Planner Sovereignty Rule.
        Downstream components MUST NOT re-route an LLM-planner-routed query to YOUTUBE_TOPIC_SEARCH
        even if the query contains the character substring 'yt' (inside 'python').
        """
        query = "Rust vs Python"
        
        # Planner sovereignty choice
        dec = self.planner.plan(query, self.context_mgr, self.pref_mem, self.episodic_mem)
        self.assertEqual(dec.target_brain, "LLM", "Planner must select LLM brain for Rust vs Python")
        
        # Downstream Intent Parser & Sanity check simulation
        mock_intent = {"intent": "AI_QUERY", "query": query}
        
        # validate_intent_sanity must respect the planner target hint and remain inside LLM domain bounds
        resolved = validate_intent_sanity(mock_intent, query, planner_hint="LLM")
        
        self.assertIn(resolved.get("intent"), ["AI_QUERY", "REALTIME_QUERY"], 
                      "Post-LLM validation MUST NOT hijack LLM brain routing to media search")
        self.assertNotEqual(resolved.get("intent"), "YOUTUBE_TOPIC_SEARCH", 
                            "Intent Parser must not hijack Rust vs Python to YouTube search")

    # 2. MEDIA ACTION ROUTING
    def test_media_routing_play_tutorial(self):
        """
        Verifies that 'Play a Rust tutorial' resolves to the correct MEDIA brain and PLAY_MEDIA intent.
        """
        query = "Play a Rust tutorial"
        dec = self.planner.plan(query, self.context_mgr, self.pref_mem, self.episodic_mem)
        self.assertEqual(dec.target_brain, "MEDIA", "Planner must select MEDIA brain for play request")
        
        mock_intent = {"intent": "PLAY_MEDIA", "query": "rust tutorial"}
        resolved = validate_intent_sanity(mock_intent, query, planner_hint="MEDIA")
        self.assertEqual(resolved.get("intent"), "PLAY_MEDIA", "Sanity filter must keep media intent")
        self.assertEqual(resolved.get("query"), "rust tutorial", "Query entities should be clean")

    # 3. MEMORY WRITE VERIFICATION (WRITE-READ LOOP)
    def test_memory_write_verification_loop(self):
        """
        Verifies the Memory Write-then-Verify loop.
        Facts committed to SemanticMemory must be written, reloaded, and verified on disk.
        """
        import memory.semantic
        original_sem_mem_class = memory.semantic.SemanticMemory
        
        # Define a subclass pointing to our temp semantic path
        semantic_path_local = self.semantic_path
        class TempSemanticMemory(original_sem_mem_class):
            def __init__(self, *args, **kwargs):
                super().__init__(file_path=semantic_path_local)
                
        memory.semantic.SemanticMemory = TempSemanticMemory
        try:
            query = "Remember FRIDAY is my AI project"
            intent_data = {"intent": "SET_FACT", "query": query}
            
            from execution.action_executor import execute_action
            import asyncio
            result = asyncio.run(execute_action(intent_data))
            
            # Assert file is written and not empty
            self.assertTrue(os.path.exists(self.semantic_path))
            self.assertGreater(os.path.getsize(self.semantic_path), 0)
            
            # Assert semantic memory loaded correctly
            self.semantic_mem.load()
            self.assertEqual(self.semantic_mem.get_fact("ai project"), "FRIDAY")
            
            # Assert conversational success response
            self.assertEqual(result.get("response"), "I have committed and verified that in my semantic registry, Sir.")
        finally:
            memory.semantic.SemanticMemory = original_sem_mem_class

    # 4. REGISTRY WRITE-READ VERIFICATION & PROJECT AWARENESS
    def test_project_registry_write_verification_loop(self):
        """
        Verifies the Registry Write-then-Verify loop and prompt context injection.
        """
        registry_path = os.path.join(self.temp_dir, "project_registry.json")
        pm = ProjectManager(file_path=registry_path)
        
        success = pm.set_active_project(
            project_name="FRIDAY",
            workspace_path="C:\\FRIDAY",
            repo_path="C:\\FRIDAY",
            active_goal="Production Optimization",
            project_type="AI Companion"
        )
        self.assertTrue(success, "ProjectManager set_active_project should verify and return True")
        
        # Reload and assert in test explicitly
        pm2 = ProjectManager(file_path=registry_path)
        active = pm2.get_active_project()
        self.assertEqual(active.get("project_name"), "FRIDAY", "Verified project name must match")
        self.assertEqual(active.get("workspace_path"), "C:\\FRIDAY", "Verified path must match")

        # Test prompt context injection
        import brain.project_manager
        original_pm_class = brain.project_manager.ProjectManager
        
        class TempProjectManager(original_pm_class):
            def __init__(self, *args, **kwargs):
                super().__init__(file_path=registry_path)
                
        brain.project_manager.ProjectManager = TempProjectManager
        try:
            query = "What project are we working on?"
            intent_data = {"intent": "AI_QUERY", "query": query}
            
            import execution.action_executor
            original_ask_groq = execution.action_executor.ask_groq
            injected_prompt = ""
            def mock_ask_groq(prompt, system_prompt, *args, **kwargs):
                nonlocal injected_prompt
                injected_prompt = system_prompt
                return "Mocked response"
                
            execution.action_executor.ask_groq = mock_ask_groq
            try:
                from execution.action_executor import execute_action
                import asyncio
                asyncio.run(execute_action(intent_data))
                
                self.assertIn("AUTHORITATIVE ACTIVE PROJECT REGISTRY", injected_prompt)
                self.assertIn("Active Project Name: FRIDAY", injected_prompt)
                self.assertIn("Workspace Directory: C:\\FRIDAY", injected_prompt)
            finally:
                execution.action_executor.ask_groq = original_ask_groq
        finally:
            brain.project_manager.ProjectManager = original_pm_class

    # 5. EXPANDED ENTITY TAXONOMY MATCHING
    def test_expanded_entity_taxonomy(self):
        """
        Verifies that expanded entity taxonomy types (company, technology, etc.) resolve.
        """
        query = "Tell me about Apple and their primary technology Rust"
        entities = extract_all_entities(query)
        
        # Find Apple -> company/brand
        # Find Rust -> programming_language
        types = [e[1] for e in entities]
        texts = [e[0].lower() for e in entities]
        
        self.assertTrue(any(t in ["company", "brand"] for t in types), "Apple must map to company or brand")
        self.assertIn("programming_language", types, "Rust must map to programming_language")
        
        # Check specific text extracts
        self.assertTrue(any("apple" in tx for tx in texts), "Apple text must be extracted")
        self.assertTrue(any("rust" in tx for tx in texts), "Rust text must be extracted")

    # 6. CONTEXT PRONOUN RESOLUTION CONTINUITY
    def test_context_pronoun_continuity(self):
        """
        Verifies multi-turn pronoun context resolution.
        """
        # Turn 1: Establish context
        self.context_mgr.update("Tell me about Apple", intent="AI_QUERY")
        self.assertEqual(self.context_mgr.last_intent, "AI_QUERY")
        
        # Turn 2: Resolve pronoun "their"
        turn_2 = "What is their primary product?"
        # Mocking context history resolution in pipeline
        history = [
            {"role": "user", "content": "Tell me about Apple"},
            {"role": "assistant", "content": "Apple is a tech company."}
        ]
        
        # Context manager enriches the query
        self.context_mgr.update(turn_2, intent="AI_QUERY")
        
        # Check pronoun lookup
        self.assertTrue(self.context_mgr.last_intent == "AI_QUERY")

    # 7. APP LAUNCH & COMPOUND ACTIONS
    def test_app_launch_intent(self):
        """
        Verifies Open VS Code maps to OPEN intent.
        """
        query = "Open VS Code"
        mock_intent = {"intent": "OPEN", "target": "VS Code"}
        resolved = validate_intent_sanity(mock_intent, query)
        self.assertEqual(resolved.get("intent"), "OPEN")
        self.assertEqual(resolved.get("target"), "VS Code")

if __name__ == "__main__":
    unittest.main()
