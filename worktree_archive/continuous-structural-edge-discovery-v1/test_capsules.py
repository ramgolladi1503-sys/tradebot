import os
import json
import hashlib

base_path = "/Users/madhuram/.antigravity/worktrees/tradebot/continuous-structural-edge-discovery-v1/research/continuous_structural_edge_discovery_v1/context"

def sha256_file(filepath):
    sha256 = hashlib.sha256()
    with open(filepath, "rb") as f:
        while True:
            data = f.read(65536)
            if not data:
                break
            sha256.update(data)
    return sha256.hexdigest()

def test_capsule_manifests_valid():
    for agent_id in ["agent_A", "agent_B", "agent_C", "agent_D"]:
        agent_dir = os.path.join(base_path, "agents", agent_id)
        
        with open(os.path.join(agent_dir, "capsule_manifest.json"), "r") as f:
            manifest = json.load(f)
            
        assert manifest["assignment.md"] == sha256_file(os.path.join(agent_dir, "assignment.md"))
        assert manifest["allowed_inputs.json"] == sha256_file(os.path.join(agent_dir, "allowed_inputs.json"))
        assert manifest["prohibited_paths.json"] == sha256_file(os.path.join(agent_dir, "prohibited_paths.json"))

def test_capsule_circular_authority_removed():
    agent_A_assignment = os.path.join(base_path, "agents", "agent_A", "assignment.md")
    with open(agent_A_assignment, "r") as f:
        content = f.read()
        assert "missing approved source" not in content

def test_altered_capsule_fails():
    agent_A_assignment = os.path.join(base_path, "agents", "agent_A", "assignment.md")
    
    # Save original
    with open(agent_A_assignment, "r") as f:
        orig_content = f.read()
        
    try:
        # Alter
        with open(agent_A_assignment, "a") as f:
            f.write("altered")
            
        with open(os.path.join(base_path, "agents", "agent_A", "capsule_manifest.json"), "r") as f:
            manifest = json.load(f)
            
        assert manifest["assignment.md"] != sha256_file(agent_A_assignment)
    finally:
        # Restore
        with open(agent_A_assignment, "w") as f:
            f.write(orig_content)
