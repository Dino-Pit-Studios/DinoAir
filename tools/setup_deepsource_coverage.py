#!/usr/bin/env python3
"""
DeepSource Coverage Setup Script

Safely configure DeepSource code coverage reporting without exposing secrets.
"""

import os
import subprocess
import sys
from pathlib import Path


class DeepSourceCoverageSetup:
    """Setup DeepSource coverage reporting securely."""

    def __init__(self):
        self.deepsource_dsn = None
        self.project_root = Path.cwd()

    def check_environment(self):
        """Check if DEEPSOURCE_DSN environment variable is set."""
        self.deepsource_dsn = os.getenv("DEEPSOURCE_DSN")

        if not self.deepsource_dsn:
            print("❌ DEEPSOURCE_DSN environment variable not set")
            print("\n🔐 To set up DeepSource coverage:")
            print("1. Get your DSN from DeepSource dashboard")
            print("2. Set environment variable:")
            print("   PowerShell: $env:DEEPSOURCE_DSN='your_dsn_here'")
            print("   Bash: export DEEPSOURCE_DSN='your_dsn_here'")
            print("\n💡 Your DSN should look like:")
            print("   https://f86b5205816f43d5a274d22d6232be60@app.deepsource.com")
            return False
        print(f"✅ DEEPSOURCE_DSN found: {self.deepsource_dsn[:20]}...{self.deepsource_dsn[-10:]}")
        return True

    def install_deepsource_cli(self):
        """Install DeepSource CLI if not present."""
        try:
            # Check if DeepSource CLI is already installed
            result = subprocess.run(
                ["deepsource", "--version"], capture_output=True, text=True, check=False
            )
            if result.returncode == 0:
                print(f"✅ DeepSource CLI already installed: {result.stdout.strip()}")
                return True
        except FileNotFoundError:
            pass

        print("📦 Installing DeepSource CLI...")

        # Install via curl (cross-platform)
        try:
            if os.name == "nt":  # Windows
                print("🪟 Installing on Windows...")
                install_cmd = ["powershell", "-Command", "curl -sSL https://deepsource.io/cli | sh"]
            else:  # Linux/Mac
                install_cmd = ["curl", "-sSL", "https://deepsource.io/cli", "|", "sh"]

            result = subprocess.run(install_cmd, check=True)
            print("✅ DeepSource CLI installed successfully")
            return True

        except subprocess.CalledProcessError as e:
            print(f"❌ Failed to install DeepSource CLI: {e}")
            print("\n💡 Manual installation:")
            print("   Visit: https://deepsource.io/cli")
            return False

    def check_test_coverage_tools(self):
        """Check if coverage tools are available."""
        tools_status = {}

        # Check for Python coverage tools
        try:
            import coverage

            tools_status["coverage.py"] = True
            print("✅ coverage.py available")
        except ImportError:
            tools_status["coverage.py"] = False
            print("❌ coverage.py not installed")

        # Check for pytest-cov
        try:
            import pytest_cov

            tools_status["pytest-cov"] = True
            print("✅ pytest-cov available")
        except ImportError:
            tools_status["pytest-cov"] = False
            print("❌ pytest-cov not installed")

        return tools_status

    def install_coverage_tools(self):
        """Install missing coverage tools."""
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

    def create_coverage_config(self):
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

        config_file = self.project_root / ".coveragerc"
        with open(config_file, "w") as f:
            f.write(coverage_config)

        print(f"✅ Created coverage config: {config_file}")
        return config_file

    def create_coverage_script(self):
        """Create a script to run tests with coverage."""
        script_content = '''#!/usr/bin/env python3
"""
Run tests with coverage and report to DeepSource

This script runs your tests with coverage and sends the report to DeepSource.
"""

import os
import sys
import subprocess
from pathlib import Path


def run_tests_with_coverage():
    """Run tests with coverage."""
    print("🧪 Running tests with coverage...")

    # Change to project root
    project_root = Path(__file__).parent
    os.chdir(project_root)

    try:
        # Run tests with coverage
        cmd = [
            sys.executable, '-m', 'pytest',
            '--cov=.',
            '--cov-report=xml:coverage.xml',
            '--cov-report=html',
            '--cov-report=term-missing',
            '--cov-branch',
            'tests/'
        ]

        print(f"Running: {' '.join(cmd)}")
        result = subprocess.run(cmd, check=True)

        print("✅ Tests completed successfully")
        return True

    except subprocess.CalledProcessError as e:
        print(f"❌ Tests failed: {e}")
        return False
    except FileNotFoundError:
        print("❌ pytest not found. Installing...")
        subprocess.run([sys.executable, '-m', 'pip', 'install', 'pytest', 'pytest-cov'])
        return run_tests_with_coverage()


def report_to_deepsource():
    """Report coverage to DeepSource."""
    print("📊 Reporting coverage to DeepSource...")

    # Check for coverage.xml
    coverage_file = Path('coverage.xml')
    if not coverage_file.exists():
        print("❌ coverage.xml not found")
        return False

    # Check for DEEPSOURCE_DSN
    dsn = os.getenv('DEEPSOURCE_DSN')
    if not dsn:
        print("❌ DEEPSOURCE_DSN environment variable not set")
        print("💡 Set it with: $env:DEEPSOURCE_DSN='your_dsn_here'")
        return False

    try:
        # Report to DeepSource using CLI
        cmd = [
            'deepsource', 'report',
            '--analyzer', 'test-coverage',
            '--key', 'python',
            '--value-file', str(coverage_file)
        ]

        print(f"Reporting: {' '.join(cmd[:4])}...")  # Don't show full command with DSN
        result = subprocess.run(cmd, check=True)

        print("✅ Coverage reported to DeepSource")
        return True

    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to report to DeepSource: {e}")
        return False
    except FileNotFoundError:
        print("❌ DeepSource CLI not found")
        print("💡 Install with: curl -sSL https://deepsource.io/cli | sh")
        return False


def main():
    """Main function."""
    print("🔍 DeepSource Coverage Reporter")
    print("=" * 35)

    # Run tests with coverage
    if not run_tests_with_coverage():
        sys.exit(1)

    # Report to DeepSource
    if not report_to_deepsource():
        print("⚠️  Coverage generated but not reported to DeepSource")
        print("💡 Check your DEEPSOURCE_DSN and CLI installation")
        sys.exit(1)

    print("🎉 Coverage analysis complete!")


if __name__ == "__main__":
    main()
'''

        script_file = self.project_root / "run_coverage.py"
        with open(script_file, "w") as f:
            f.write(script_content)

        # Make executable on Unix systems with secure permissions
        if os.name != "nt":
            os.chmod(script_file, 0o700)  # Owner: read/write/execute, Group: none, Others: none

        print(f"✅ Created coverage script: {script_file}")
        return script_file

    def update_gitignore(self):
        """Update .gitignore to ensure coverage files are handled correctly."""
        gitignore_path = self.project_root / ".gitignore"

        # Coverage patterns to ensure are in .gitignore
        coverage_patterns = [
            "# Coverage reports and artifacts",
            "coverage.xml",
            "htmlcov/",
            ".coverage",
            ".coverage.*",
            "*.cover",
            ".nyc_output/",
            ".pytest_cache/",
            "",
        ]

        # Read existing .gitignore
        existing_content = ""
        if gitignore_path.exists():
            with open(gitignore_path) as f:
                existing_content = f.read()

        # Check which patterns are missing
        missing_patterns = []
        for pattern in coverage_patterns:
            if pattern and pattern not in existing_content:
                missing_patterns.append(pattern)

        if missing_patterns:
            with open(gitignore_path, "a") as f:
                f.write("\n" + "\n".join(missing_patterns))
            print(f"✅ Updated .gitignore with {len(missing_patterns)} coverage patterns")
        else:
            print("✅ .gitignore already contains coverage patterns")

    def create_github_workflow(self):
        """Create GitHub Actions workflow for coverage reporting."""
        workflow_dir = self.project_root / ".github" / "workflows"
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

    - name: Upload coverage to Codecov (optional)
      uses: codecov/codecov-action@v3
      with:
        file: ./coverage.xml
        fail_ci_if_error: false
"""

        workflow_file = workflow_dir / "coverage.yml"
        with open(workflow_file, "w") as f:
            f.write(workflow_content)

        print(f"✅ Created GitHub workflow: {workflow_file}")
        print("💡 Don't forget to add DEEPSOURCE_DSN to GitHub Secrets!")
        return workflow_file

    def run_setup(self):
        """Run the complete setup process."""
        print("🚀 DeepSource Coverage Setup")
        print("=" * 30)

        # Check environment
        if not self.check_environment():
            print("\n⚠️  Setup incomplete - DEEPSOURCE_DSN not set")
            return False

        # Install CLI
        if not self.install_deepsource_cli():
            print("\n⚠️  Setup incomplete - CLI installation failed")
            return False

        # Check coverage tools
        tools_status = self.check_test_coverage_tools()
        if not all(tools_status.values()) and not self.install_coverage_tools():
            print("\n⚠️  Setup incomplete - coverage tools installation failed")
            return False

        # Create configuration files
        self.create_coverage_config()
        self.create_coverage_script()
        self.update_gitignore()
        self.create_github_workflow()

        print("\n🎉 DeepSource coverage setup complete!")
        print("\n📋 Next steps:")
        print("1. Run tests with coverage: python run_coverage.py")
        print("2. Add DEEPSOURCE_DSN to GitHub Secrets")
        print("3. Commit and push your changes")

        return True


def main():
    """Main setup function."""
    setup = DeepSourceCoverageSetup()
    return setup.run_setup()


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
