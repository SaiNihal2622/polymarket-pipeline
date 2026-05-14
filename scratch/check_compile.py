import ast, sys
with open('web_dashboard.py', encoding='utf-8') as f:
    code = f.read()
try:
    ast.parse(code)
    result = 'OK: web_dashboard.py compiles cleanly'
    print(result)
    with open('scratch/check_compile.txt', 'w') as out:
        out.write(result)
except SyntaxError as e:
    msg = f'SYNTAX ERROR: {e}'
    print(msg)
    with open('scratch/check_compile.txt', 'w') as out:
        out.write(msg)
    sys.exit(1)