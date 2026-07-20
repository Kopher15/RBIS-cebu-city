import sys
import os
import json
from datetime import datetime

# Add src to path
sys.path.append(os.path.join(os.path.dirname(os.path.dirname(__file__)), "src"))

from controllers import sync_orchestrator

def main():
    config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config", "sync.config.json")
    
    with open(config_path, 'r') as f:
        cfg = json.load(f)

    # Run the orchestrator
    result = sync_orchestrator.run(cfg)

    if result["status"] == "success":
        print("-" * 40)
        print("SYNC COMPLETED SUCCESSFULLY")
        print(f"Total Time: {result['elapsed']}s")
        print("-" * 40)
        
        for res in result["results"]:
            stats = res["stats"]
            print(f"Destination: {res['dest']}")
            print(f"  - Inserted:     {stats['inserted']}")
            print(f"  - Updated:      {stats['updated']}")
            print(f"  - Soft-Deleted: {stats['soft_deleted']}")
            print(f"  - Un-deleted:   {stats['un_deleted']}")
            print(f"  - Backup Table: {res['backup']}")
            print("-" * 20)
    else:
        print(f"ERROR: {result.get('error', 'Unknown error')}")
        sys.exit(1)

if __name__ == "__main__":
    main()
