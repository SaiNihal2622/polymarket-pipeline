import ast, sys

files = ['run_both.py', 'web_dashboard.py', 'demo_runner.py', 'resolver.py', 'db_tables.py']
for f in files:
    try:
        ast.parse(open(f, encoding='utf-8').read())
        print(f'{f}: OK')
    except SyntaxError as e:
        print(f'{f}: SYNTAX ERROR at line {e.lineno}: {e.msg}')
        sys.exit(1)
print('All files OK')