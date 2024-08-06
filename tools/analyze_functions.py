import ast
import os
import yaml
import argparse
import sys

def has_type_hint(node):
    """Check if a node has type hints."""
    return any(isinstance(arg.annotation, ast.AST) for arg in node.args.args if arg.annotation)

def has_return_type_hint(node):
    """Check if a node has a return type hint."""
    return node.returns is not None

def has_docstring(node):
    """Check if a node has a docstring."""
    return isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and isinstance(node.body[0], ast.Expr) and isinstance(node.body[0].value, ast.Str)

def find_functions_info(directories):
    total_number_of_functions = 0
    """Find functions without type hints and functions without docstrings in multiple directories."""
    files_info = {}
    for directory in directories:
        for root, _, files in os.walk(directory):
            for file in files:
                if file.endswith('.py'):
                    file_path = os.path.join(root, file)
                    functions_without_type_hints = []
                    functions_without_docstrings = []
                    with open(file_path, 'r') as f:
                        try:
                            tree = ast.parse(f.read(), filename=file_path)
                            for node in ast.walk(tree):
                                if isinstance(node, ast.FunctionDef):
                                    total_number_of_functions += 1
                                    if not has_type_hint(node) or not has_return_type_hint(node):
                                        functions_without_type_hints.append(node.name)
                                    if not has_docstring(node):
                                        functions_without_docstrings.append(node.name)
                        except SyntaxError:
                            print(f"Error parsing {file_path}. Skipping...")
                    
                    files_info[os.path.relpath(file_path, directory)] = {
                        "functions_without_type_hints": functions_without_type_hints,
                        "functions_without_docstrings": functions_without_docstrings
                    }
    return files_info, total_number_of_functions

def save_to_yaml(data, output_file):
    """Save data to a YAML file."""
    with open(output_file, 'w') as f:
        yaml.dump(data, f)

def count_functions(info, key):
    """Count the number of functions based on the specified key."""
    return sum(len(file_info[key]) for file_info in info.values())

def analyze(directories, output_file):
    functions_info, total_number_of_functions = find_functions_info(directories)
    print(f"Total number of functions: {total_number_of_functions}")
    save_to_yaml(functions_info, output_file)
    print(f"Total functions without type hints: {count_functions(functions_info, 'functions_without_type_hints')}")
    print(f"Total functions without docstrings: {count_functions(functions_info, 'functions_without_docstrings')}")

def compare(source_file, target_file):
    print(f"Comparing {source_file} with {target_file}")
    source_info = yaml.safe_load(open(source_file))
    target_info = yaml.safe_load(open(target_file))

    source_type_hints = count_functions(source_info, 'functions_without_type_hints')
    target_type_hints = count_functions(target_info, 'functions_without_type_hints')

    source_docstrings = count_functions(source_info, 'functions_without_docstrings')
    target_docstrings = count_functions(target_info, 'functions_without_docstrings')

    print(f'Source branch - functions without type hints: {source_type_hints}, without docstrings: {source_docstrings}')
    print(f'Target branch - functions without type hints: {target_type_hints}, without docstrings: {target_docstrings}')
    
    errors = []
    new_functions_without_type_hints = []
    new_functions_without_docstrings = []

    for file, data in source_info.items():
        source_functions_without_type_hints = set(data['functions_without_type_hints'])
        target_functions_without_type_hints = set(target_info.get(file, {}).get('functions_without_type_hints', []))
        new_type_hints = source_functions_without_type_hints - target_functions_without_type_hints
        if new_type_hints:
            new_functions_without_type_hints.extend([f"{file}: {func}" for func in new_type_hints])

        source_functions_without_docstrings = set(data['functions_without_docstrings'])
        target_functions_without_docstrings = set(target_info.get(file, {}).get('functions_without_docstrings', []))
        new_docstrings = source_functions_without_docstrings - target_functions_without_docstrings
        if new_docstrings:
            new_functions_without_docstrings.extend([f"{file}: {func}" for func in new_docstrings])

    if new_functions_without_type_hints:
        errors.append('Error: Number of functions without type hints increased')
        print("New functions without type hints:")
        for func in new_functions_without_type_hints:
            print(f"  {func}")

    if new_functions_without_docstrings:
        errors.append('Error: Number of functions without docstrings increased')
        print("New functions without docstrings:")
        for func in new_functions_without_docstrings:
            print(f"  {func}")

    if errors:
        for error in errors:
            print(error)
        sys.exit(1)
    else:
        print("No new issues found.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Analyze Python functions in directories or compare results.')
    subparsers = parser.add_subparsers(dest='command')

    analyze_parser = subparsers.add_parser('analyze', help='Analyze the functions in directories.')
    analyze_parser.add_argument('output_file', type=str, help='Output YAML file')
    analyze_parser.add_argument('directories', type=str, nargs='+', help='Directories to analyze')

    compare_parser = subparsers.add_parser('compare', help='Compare the results of two analyses.')
    compare_parser.add_argument('source_file', type=str, help='Source analysis YAML file')
    compare_parser.add_argument('target_file', type=str, help='Target analysis YAML file')

    args = parser.parse_args()

    if args.command == 'analyze':
        analyze(args.directories, args.output_file)
    elif args.command == 'compare':
        compare(args.source_file, args.target_file)
    else:
        parser.print_help()
