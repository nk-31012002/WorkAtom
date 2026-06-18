# repo_crawler.py
import os
from typing import Dict

class RepositoryCrawler:
    def __init__(self, target_directory: str):
        self.target_directory = os.path.abspath(target_directory)
        # Folders we want to completely ignore during an enterprise code scan
        self.ignored_dirs = {
            ".git", "__pycache__", ".venv", "venv", "node_modules", 
            ".idea", ".vscode", "dist", "build"
        }
        # Extensions we want to read (We can easily add .js, .ts, .java here later!)
        # self.supported_extensions = {".py"}
        self.supported_extensions = {".py", ".js", ".jsx", ".ts", ".tsx"}

    def scan_repository(self) -> Dict[str, str]:
        """
        Crawls the target folder directory recursively.
        Returns a dictionary: { "relative/path/to/file.py": "raw contents string" }
        """
        codebase_matrix = {}
        print(f"\n🔍 [Crawler] Initializing deep filesystem scan of: {self.target_directory}")
        
        if not os.path.exists(self.target_directory):
            print(f"[!] Error: Target directory '{self.target_directory}' does not exist.")
            return codebase_matrix

        for root, dirs, files in os.walk(self.target_directory):
            # Modifying dirs in-place allows os.walk to efficiently skip ignored folders entirely
            dirs[:] = [d for d in dirs if d not in self.ignored_dirs]
            
            for file in files:
                ext = os.path.splitext(file)[1]
                if ext in self.supported_extensions:
                    full_path = os.path.join(root, file)
                    # Compute relative path so the LLM output is neat and readable
                    rel_path = os.path.relpath(full_path, self.target_directory)
                    
                    try:
                        with open(full_path, "r", encoding="utf-8") as f:
                            codebase_matrix[rel_path] = f.read()
                    except Exception as e:
                        print(f"  ⚠️ [Skipped] Could not read {rel_path} due to error: {e}")
                        
        print(f"✅ [Crawler] Scan complete. Found {len(codebase_matrix)} valid source modules.")
        return codebase_matrix

if __name__ == "__main__":
    # Quick self-test to verify crawler behavior in your active folder
    crawler = RepositoryCrawler(".")
    found_files = crawler.scan_repository()
    print("\nDiscovered Modules:")
    for path in found_files.keys():
        print(f" -> {path}")