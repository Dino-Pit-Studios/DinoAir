#!/usr/bin/env python3
"""
Alternative DeepSource Coverage Setup

Setup coverage reporting without requiring the CLI to be installed fi        else:
          echo "WARNING: No coverage.xml found"t.
"""

import os
import subprocess
import sys
from pathlib import Path


def create_coverage_config():
    """Create .coveragerc configuration file."""
    coverage_config = """# Coverage configuration for DeepSource
[run]
source = .
branch = True
omit =
    */tests/*
    */test_*
    */.venv/*
    */venv/*
    */env/*
    */__pycache__/*
    */migrations/*
    */node_modules/*
    setup.py
    manage.py
    conftest.py
    */settings/local.py
    */settings/development.py
    # Security scripts (these are tools, not application code)
    github_security_loader.py
    setup_github_security.py
    simple_github_security.py
    github_security_diagnostic.py
    check_token_scopes.py
    security_summary.py
    github_to_python_list.py
    setup_deepsource_coverage.py

[report]
exclude_lines =
    pragma: no cover
    def __repr__
    if self.debug:
    if settings.DEBUG
    raise AssertionError
    raise NotImplementedError
    if 0:
    if __name__ == .__main__.:
    class .*\\bProtocol\\):
    @(abc\\.)?abstractmethod

[html]
directory = htmlcov

[xml]
output = coverage.xml
"""

    config_file = Path(".coveragerc")
    with open(config_file, "w", encoding="utf-8") as f:
        f.write(coverage_config)

    print(f"✅ Created coverage config: {config_file}")
    return config_file


def install_coverage_tools():
    """Install coverage tools."""
    print("📦 Installing coverage tools...")

    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "coverage", "pytest-cov"], check=True
        )
        print("✅ Coverage tools installed")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to install coverage tools: {e}")
        return False


def create_github_workflow():
    """Create GitHub Actions workflow for coverage reporting."""
    workflow_dir = Path(".github/workflows")
    workflow_dir.mkdir(parents=True, exist_ok=True)

    workflow_content = """name: "Test Coverage Report"

on:
  push:
    branches: [ "main", "develop" ]
  pull_request:
    branches: [ "main" ]

jobs:
  coverage:
    name: Generate Coverage Report
    runs-on: ubuntu-latest

    steps:
    - name: Checkout repository
      uses: actions/checkout@v4

    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.11'

    - name: Install dependencies
      run: |
        python -m pip install --upgrade pip
        pip install coverage pytest pytest-cov
        if [ -f requirements.txt ]; then
          pip install -r requirements.txt
        fi
        if [ -f requirements-dev.txt ]; then
          pip install -r requirements-dev.txt
        fi

    - name: Run tests with coverage
      run: |
        python -m pytest --cov=. --cov-report=xml --cov-report=term-missing tests/ || true

    - name: Install DeepSource CLI
      run: |
        curl https://deepsource.io/cli | sh

    - name: Report coverage to DeepSource
      env:
        DEEPSOURCE_DSN: ${{ secrets.DEEPSOURCE_DSN }}
      run: |
        if [ -f coverage.xml ]; then
          ./bin/deepsource report --analyzer test-coverage --key python --value-file coverage.xml
        else
          echo "⚠️  No coverage.xml found"
        fi
"""

    workflow_file = workflow_dir / "coverage.yml"
    with open(workflow_file, "w", encoding="utf-8") as f:
        f.write(workflow_content)

    print(f"✅ Created GitHub workflow: {workflow_file}")
    return workflow_file


def update_gitignore_for_coverage():
    """Ensure .gitignore has proper coverage patterns."""
    gitignore_path = Path(".gitignore")

    # Coverage patterns to add if missing
    coverage_patterns = [
        "",
        "# DeepSource coverage artifacts",
        "coverage.xml",
        "htmlcov/",
        ".coverage",
        ".coverage.*",
        "*.lcov",
        ".nyc_output/",
        "",
    ]

    # Read existing content
    existing_content = ""
    if gitignore_path.exists():
        with open(gitignore_path, encoding="utf-8") as f:
            existing_content = f.read()

    # Add missing patterns
    missing_patterns = []
    for pattern in coverage_patterns:
        if pattern and pattern not in existing_content:
            missing_patterns.append(pattern)

    if missing_patterns:
        with open(gitignore_path, "a", encoding="utf-8") as f:
            f.write("\n" + "\n".join(missing_patterns))
        print(f"✅ Added {len(missing_patterns)} coverage patterns to .gitignore")
    else:
        print("✅ .gitignore already has coverage patterns")


def create_test_coverage_script():
    """Create a simple script to run coverage locally."""
    script_content = '''#!/usr/bin/env python3
"""
Local Coverage Runner

Run tests with coverage locally and generate reports.
"""

import subprocess
import sys
from pathlib import Path

def main():
    """Run coverage locally."""
    print("🧪 Running tests with coverage...")

    try:
        # Run tests with coverage
        cmd = [
            sys.executable, '-m', 'pytest',
            '--cov=.',
            '--cov-report=xml:coverage.xml',
            '--cov-report=html:htmlcov',
            '--cov-report=term-missing',
            '--cov-branch',
            'tests/'
        ]

        result = subprocess.run(cmd, check=False)

        if result.returncode == 0:
            print("✅ Tests completed successfully")
        else:
            print("⚠️  Some tests failed or no tests found")

        # Check if coverage file was created
        if Path('coverage.xml').exists():
            print("✅ Coverage report generated: coverage.xml")
            print("📊 HTML report available: htmlcov/index.html")
        else:
            print("❌ No coverage report generated")

    except FileNotFoundError:
        print("❌ pytest not found. Installing...")
        subprocess.run([sys.executable, '-m', 'pip', 'install', 'pytest', 'pytest-cov'])
        main()

if __name__ == "__main__":
    main()
'''

    script_file = Path("run_local_coverage.py")
    with open(script_file, "w", encoding="utf-8") as f:
        f.write(script_content)

    print(f"✅ Created local coverage script: {script_file}")
    return script_file


def main():
    """Main setup function."""
    print("🚀 DeepSource Coverage Setup (Alternative)")
    print("=" * 45)

    # Check for DEEPSOURCE_DSN
    dsn = os.getenv("DEEPSOURCE_DSN")
    if dsn:
        print(f"✅ DEEPSOURCE_DSN found: {dsn[:30]}...")
    else:
        print("⚠️  DEEPSOURCE_DSN not set")
        print("💡 Set with: $env:DEEPSOURCE_DSN='your_dsn_here'")

    # Install coverage tools
    install_coverage_tools()

    # Create configuration files
    create_coverage_config()
    create_github_workflow()
    update_gitignore_for_coverage()
    create_test_coverage_script()

    print("\n🎉 DeepSource coverage setup complete!")
    print("\n📋 Next steps:")
    print("1. Test locally: python run_local_coverage.py")
    print("2. Add DEEPSOURCE_DSN to GitHub Secrets:")
    print("   - Go to Repository Settings > Secrets and variables > Actions")
    print("   - Add new secret: DEEPSOURCE_DSN")
    print("   - Value: your DeepSource DSN")
    print("3. Commit and push changes")
    print("\n🔒 Security notes:")
    print("- DSN is stored as environment variable (not in code)")
    print("- .gitignore protects coverage artifacts")
    print("- GitHub Secrets protect DSN in CI/CD")


if __name__ == "__main__":
    main()
