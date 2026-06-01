#!/usr/bin/env python3
"""Quick syntax check"""
import ast
import sys

files_to_check = [
    "core/openai_realtime_sales_bot.py",
    "core/bot_framework.py",
    "main.py"
]

all_ok = True
for filepath in files_to_check:
    try:
        with open(filepath, 'r') as f:
            code = f.read()
        ast.parse(code)
        print(f"✅ {filepath}: OK")
    except SyntaxError as e:
        print(f"❌ {filepath}: {e}")
        all_ok = False
    except Exception as e:
        print(f"⚠️  {filepath}: {e}")

sys.exit(0 if all_ok else 1)
