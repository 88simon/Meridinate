#!/usr/bin/env python3
"""
Script to fix remaining ESLint warnings in Gun Del Sol Web
Handles:
- Removing console.log/console.error statements
- Fixing unused imports
- Fixing React Hook dependencies
"""

import re
from pathlib import Path

# Base directory
BASE_DIR = Path(__file__).parent / "src"

def remove_console_logs(file_path):
    """Remove console.log and console.error statements"""
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    original = content

    # Remove console.log statements (standalone lines)
    content = re.sub(r"^\s*console\.(log|error|warn|info)\([^)]*\);\s*$", "", content, flags=re.MULTILINE)

    # Remove console.log in conditionals (like in page.tsx)
    content = re.sub(r"\s*if\s*\(shouldLog\(\)\)\s*{\s*console\.log\([^)]*\);\s*}", "", content)

    # Remove inline console.logs in arrow functions
    content = re.sub(r"onClick=\{\(\)\s*=>\s*console\.log\([^)]*\)\}", "onClick={() => {}}", content)

    # Remove console in callbacks
    content = re.sub(r"\.then\(\([^)]*\)\s*=>\s*console\.log\([^)]*\)\)", "", content)
    content = re.sub(r"testNotif\.onshow\s*=\s*\(\)\s*=>\s*console\.log\([^)]*\);", "testNotif.onshow = () => {};", content)
    content = re.sub(r"testNotif\.onclick\s*=\s*\(\)\s*=>\s*{\s*console\.log\([^)]*\);", "testNotif.onclick = () => {", content)
    content = re.sub(r"testNotif\.onerror\s*=\s*\(e\)\s*=>\s*console\.error\([^)]*\);", "", content)

    # Clean up multiple blank lines
    content = re.sub(r"\n\n\n+", "\n\n", content)

    if content != original:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        return True
    return False

def fix_unused_imports(file_path):
    """Fix specific unused imports based on lint output"""
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    original = content

    # tokens-table.tsx - remove unused imports
    if 'tokens-table.tsx' in str(file_path):
        content = re.sub(r"import\s+{\s*Tags\s*}\s+from\s+'lucide-react';\s*\n?", "", content)
        content = re.sub(r",\s*Tags\s*(?=[,}])", "", content)
        content = re.sub(r"{\s*Tags,\s*", "{ ", content)

        # Remove Popover imports
        imports_to_remove = ['Popover', 'PopoverContent', 'PopoverTrigger', 'Checkbox', 'Label']
        for imp in imports_to_remove:
            content = re.sub(rf",\s*{imp}\s*(?=[,}}])", "", content)
            content = re.sub(rf"{imp},\s*", "", content)
            content = re.sub(rf"import\s+{{\s*{imp}\s*}}\s+from[^;]+;\s*\n?", "", content)

        # Remove unused variables
        content = re.sub(r"const\s+\[isDeleting,\s+setIsDeleting\]\s+=\s+useState\([^)]*\);\s*\n?", "", content)
        content = re.sub(r"const\s+\[isLoadingDetails,\s+setIsLoadingDetails\]\s+=\s+useState\([^)]*\);\s*\n?", "", content)

    # token-details-modal.tsx
    if 'token-details-modal.tsx' in str(file_path):
        content = re.sub(r",\s*X\s*(?=[,}])", "", content)
        content = re.sub(r"{\s*X,\s*", "{ ", content)

    # additional-tags.tsx
    if 'additional-tags.tsx' in str(file_path):
        # Remove unused onTagsChange
        content = re.sub(r",\s*onTagsChange\s*(?=[,}])", "", content)
        content = re.sub(r"onTagsChange,\s*", "", content)

        # Remove unused isLoading variable
        content = re.sub(r"const\s+\[isLoading,\s+setIsLoading\]\s+=\s+useState\([^)]*\);\s*\n?", "", content)

    if content != original:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        return True
    return False

def fix_hook_dependencies(file_path):
    """Fix React Hook dependency issues"""
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    original = content

    # tokens/page.tsx - fix pollsSinceLastActive dependency
    if 'tokens/page.tsx' in str(file_path):
        # Change setPollsSinceLastActive to use functional update
        content = re.sub(
            r"setPollsSinceLastActive\(pollsSinceLastActive \+ 1\)",
            "setPollsSinceLastActive((prev) => prev + 1)",
            content
        )

    # tokens-table.tsx - add handleDelete to dependencies
    if 'tokens-table.tsx' in str(file_path):
        content = re.sub(
            r"useMemo\(\(\)\s*=>\s*\{[^}]+return\s+columns;[\s\n]+},\s*\[(onDelete|sortedData)\]\)",
            r"useMemo(() => {\n    return columns;\n  }, [\1, handleDelete])",
            content,
            flags=re.DOTALL
        )

    # additional-tags.tsx - add checkBotTag to dependencies
    if 'additional-tags.tsx' in str(file_path):
        content = re.sub(
            r"useEffect\(\(\)\s*=>\s*\{[\s\n]+checkBotTag\(\);[\s\n]+},\s*\[\]\)",
            "useEffect(() => {\n    checkBotTag();\n  }, [checkBotTag])",
            content
        )

    # WalletTagsContext.tsx - fix fetchTags dependency
    if 'WalletTagsContext.tsx' in str(file_path):
        content = re.sub(
            r"useEffect\(\(\)\s*=>\s*\{[\s\n]+if\s*\([^)]+\)\s*\{[\s\n]+fetchTags\(\);[\s\n]+}[\s\n]+},\s*\[([^\]]+)\]\)",
            r"useEffect(() => {\n    if (\1) {\n      fetchTags();\n    }\n  }, [\1, fetchTags])",
            content,
            flags=re.DOTALL
        )

    if content != original:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        return True
    return False

# Files to process
files_to_process = [
    "app/dashboard/tokens/page.tsx",
    "app/dashboard/tokens/token-details-modal.tsx",
    "app/dashboard/tokens/tokens-table.tsx",
    "app/dashboard/trash/page.tsx",
    "components/additional-tags.tsx",
    "components/kbar/use-token-search.tsx",
    "contexts/ApiSettingsContext.tsx",
    "contexts/WalletTagsContext.tsx",
    "hooks/useAnalysisNotifications.ts",
]

print("Fixing lint issues...")
fixed_count = 0

for file_rel_path in files_to_process:
    file_path = BASE_DIR / file_rel_path
    if not file_path.exists():
        print(f"  Skipping {file_rel_path} (not found)")
        continue

    fixed = False
    fixed |= remove_console_logs(file_path)
    fixed |= fix_unused_imports(file_path)
    fixed |= fix_hook_dependencies(file_path)

    if fixed:
        print(f"  [OK] Fixed {file_rel_path}")
        fixed_count += 1
    else:
        print(f"  [SKIP] No changes needed for {file_rel_path}")

print(f"\nFixed {fixed_count} files")
print("Run 'pnpm lint:strict' to verify")
